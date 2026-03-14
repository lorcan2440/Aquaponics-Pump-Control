import argparse
import asyncio
import sys
from collections import deque

import pyqtgraph as pg
from bleak import BleakClient, BleakScanner
from PyQt6 import QtCore, QtWidgets

from utils import get_logger


DEFAULT_DEVICE_NAME = "PIR-UnoWiFiRev2"
DEFAULT_SERVICE_UUID = "19B10000-E8F2-537E-4F6C-D104768A1214"
DEFAULT_CHARACTERISTIC_UUID = "19B10001-E8F2-537E-4F6C-D104768A1214"
DEFAULT_CONNECT_TIMEOUT = 45.0
DEFAULT_CONNECT_RETRIES = 3

LOGGER = get_logger("pir_ble")


class BleWorker(QtCore.QThread):
	value_received = QtCore.pyqtSignal(int)
	status_changed = QtCore.pyqtSignal(str)
	error_occurred = QtCore.pyqtSignal(str)

	def __init__(
		self,
		device_name: str,
		service_uuid: str,
		characteristic_uuid: str,
		connect_timeout: float,
		connect_retries: int,
	):
		super().__init__()
		self.device_name = device_name
		self.service_uuid = service_uuid.lower()
		self.characteristic_uuid = characteristic_uuid
		self.connect_timeout = connect_timeout
		self.connect_retries = max(1, connect_retries)
		self._stop_requested = False
		self._last_value = None

	def stop(self):
		self._stop_requested = True

	def run(self):
		try:
			asyncio.run(self._run_ble())
		except Exception as exc:
			LOGGER.exception("Unhandled BLE worker error")
			self.error_occurred.emit(str(exc))

	async def _find_device(self):
		for attempt in range(1, 6):
			self.status_changed.emit(f"Scanning for BLE device (attempt {attempt}/5)...")
			LOGGER.info("BLE scan attempt %s/5 started", attempt)
			devices_with_adv = await BleakScanner.discover(timeout=4.0, return_adv=True)

			if not devices_with_adv:
				LOGGER.info("BLE scan attempt %s: no devices detected", attempt)
				continue

			for _, (device, adv) in devices_with_adv.items():
				rssi = getattr(adv, "rssi", None)
				if rssi is None:
					rssi = getattr(device, "rssi", None)
				LOGGER.info(
					"BLE device detected: name='%s' local_name='%s' address='%s' rssi=%s uuids=%s",
					device.name or "",
					adv.local_name or "",
					device.address or "",
					rssi,
					list(adv.service_uuids or []),
				)

			for _, (device, adv) in devices_with_adv.items():
				if (adv.local_name or device.name or "") == self.device_name:
					LOGGER.info("Matched BLE device by name: %s", self.device_name)
					return device

			for _, (device, adv) in devices_with_adv.items():
				advertised_uuids = {u.lower() for u in (adv.service_uuids or [])}
				if self.service_uuid in advertised_uuids:
					LOGGER.info("Matched BLE device by service UUID: %s", self.service_uuid)
					return device

		return None

	async def _run_ble(self):
		last_error = None

		for connect_attempt in range(1, self.connect_retries + 1):
			device = await self._find_device()
			if device is None:
				last_error = RuntimeError(
					f"Could not find BLE device '{self.device_name}' or service '{self.service_uuid}'"
				)
				continue

			self.status_changed.emit(
				f"Connecting to {device.name or device.address} (attempt {connect_attempt}/{self.connect_retries})..."
			)
			LOGGER.info(
				"Connecting to BLE device: %s (%s), attempt %s/%s, timeout %.1fs",
				device.name,
				device.address,
				connect_attempt,
				self.connect_retries,
				self.connect_timeout,
			)

			try:
				async with BleakClient(device, timeout=self.connect_timeout) as client:
					self.status_changed.emit("Connected. Waiting for PIR data...")
					LOGGER.info("BLE connected")

					def notification_handler(_, data: bytearray):
						if not data:
							return
						value = 1 if data[0] else 0
						if value != self._last_value:
							LOGGER.info("PIR notification value=%s", value)
							self._last_value = value
						self.value_received.emit(value)

					await client.start_notify(self.characteristic_uuid, notification_handler)
					try:
						while not self._stop_requested:
							await asyncio.sleep(0.05)
					finally:
						await client.stop_notify(self.characteristic_uuid)
						LOGGER.info("BLE notifications stopped")

				self.status_changed.emit("Disconnected")
				LOGGER.info("BLE disconnected")
				return
			except TimeoutError as exc:
				last_error = exc
				LOGGER.warning(
					"BLE connection attempt %s/%s timed out",
					connect_attempt,
					self.connect_retries,
				)

		if last_error is not None:
			raise last_error

		raise RuntimeError("BLE connection failed")


class PirPlotWindow(QtWidgets.QMainWindow):
	def __init__(
		self,
		device_name: str,
		service_uuid: str,
		characteristic_uuid: str,
		connect_timeout: float,
		connect_retries: int,
		max_points: int = 400,
	):
		super().__init__()

		self.setWindowTitle("PIR Signal (BLE Real-Time)")
		self.resize(900, 500)

		self.sample_index = 0

		self.y_values = deque(maxlen=max_points)
		self.x_values = deque(maxlen=max_points)
		self.status_label = QtWidgets.QLabel("Starting BLE client...")

		self.plot_widget = pg.PlotWidget()
		self.plot_widget.setLabel("left", "PIR Output")
		self.plot_widget.setLabel("bottom", "Sample")
		self.plot_widget.setYRange(-0.1, 1.1)
		self.plot_widget.showGrid(x=True, y=True, alpha=0.25)
		self.curve = self.plot_widget.plot([], [], pen=pg.mkPen(width=2))

		container = QtWidgets.QWidget()
		layout = QtWidgets.QVBoxLayout(container)
		layout.addWidget(self.status_label)
		layout.addWidget(self.plot_widget)
		self.setCentralWidget(container)

		self.ble_worker = BleWorker(
			device_name=device_name,
			service_uuid=service_uuid,
			characteristic_uuid=characteristic_uuid,
			connect_timeout=connect_timeout,
			connect_retries=connect_retries,
		)
		self.ble_worker.value_received.connect(self.on_value_received)
		self.ble_worker.status_changed.connect(self.status_label.setText)
		self.ble_worker.error_occurred.connect(self.on_ble_error)
		self.ble_worker.start()

	def on_value_received(self, value: int):
		self.x_values.append(self.sample_index)
		self.y_values.append(value)
		self.sample_index += 1
		self.curve.setData(list(self.x_values), list(self.y_values))

	def on_ble_error(self, message: str):
		LOGGER.error("BLE error: %s", message)
		self.status_label.setText(f"BLE error: {message}")

	def closeEvent(self, event):
		self.ble_worker.stop()
		self.ble_worker.wait(3000)
		super().closeEvent(event)


def parse_args():
	parser = argparse.ArgumentParser(description="Plot PIR sensor BLE output in real time.")
	parser.add_argument(
		"--device-name",
		default=DEFAULT_DEVICE_NAME,
		help="BLE device name (default: PIR-UnoWiFiRev2)",
	)
	parser.add_argument(
		"--service-uuid",
		default=DEFAULT_SERVICE_UUID,
		help="BLE service UUID (default: PIR service)",
	)
	parser.add_argument(
		"--characteristic-uuid",
		default=DEFAULT_CHARACTERISTIC_UUID,
		help="BLE characteristic UUID (default: PIR characteristic)",
	)
	parser.add_argument(
		"--connect-timeout",
		type=float,
		default=DEFAULT_CONNECT_TIMEOUT,
		help="BLE connect timeout in seconds (default: 45)",
	)
	parser.add_argument(
		"--connect-retries",
		type=int,
		default=DEFAULT_CONNECT_RETRIES,
		help="Number of BLE connect attempts after discovery (default: 3)",
	)
	parser.add_argument(
		"--verbose",
		action="store_true",
		help="Enable verbose BLE logging to console",
	)
	return parser.parse_args()


def main():
	args = parse_args()
	LOGGER.setLevel("DEBUG" if args.verbose else "INFO")
	app = QtWidgets.QApplication(sys.argv)
	window = PirPlotWindow(
		device_name=args.device_name,
		service_uuid=args.service_uuid,
		characteristic_uuid=args.characteristic_uuid,
		connect_timeout=args.connect_timeout,
		connect_retries=args.connect_retries,
	)
	window.show()
	sys.exit(app.exec())


if __name__ == "__main__":
	main()
