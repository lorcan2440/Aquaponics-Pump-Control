import asyncio
import os
import struct
from pathlib import Path
from threading import Lock

from bleak import BleakClient, BleakScanner
from dotenv import load_dotenv
from PyQt6 import QtCore

from utils import get_logger


PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")

DEFAULT_DEVICE_NAME = os.environ.get("BLE_DEVICE_NAME")
DEFAULT_SERVICE_UUID = os.environ.get("BLE_SERVICE_UUID")
DEFAULT_CHARACTERISTIC_UUID = os.environ.get("BLE_CHARACTERISTIC_UUID")

DEFAULT_CONNECT_TIMEOUT = float(os.environ.get("BLE_CONNECT_TIMEOUT", 30.0))
DEFAULT_CONNECT_RETRIES = int(os.environ.get("BLE_CONNECT_RETRIES", 3))
DEFAULT_DUTY = float(os.environ.get("PWM_DEFAULT_DUTY", 0.0))
SLIDER_STEPS = int(os.environ.get("PWM_SLIDER_STEPS", 1000))


LOGGER = get_logger("pump_pwm_ble")


class BleWorker(QtCore.QThread):
    status_changed = QtCore.pyqtSignal(str)
    error_occurred = QtCore.pyqtSignal(str)
    command_sent = QtCore.pyqtSignal(float)

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
        self._pending_command = None
        self._last_sent_command = None
        self._command_lock = Lock()

    def stop(self):
        self._stop_requested = True

    def set_pwm_command(self, duty: float):
        duty = max(0.0, min(1.0, float(duty)))
        with self._command_lock:
            self._pending_command = duty

    def _pop_pending_command(self):
        with self._command_lock:
            command = self._pending_command
            self._pending_command = None
            return command

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

            if not self.device_name:
                for _, (device, adv) in devices_with_adv.items():
                    advertised_uuids = {u.lower() for u in (adv.service_uuids or [])}
                    if self.service_uuid in advertised_uuids:
                        LOGGER.info("Matched BLE device by service UUID: %s", self.service_uuid)
                        return device

        return None

    async def _validate_writable_characteristic(self, client: BleakClient):
        characteristic = client.services.get_characteristic(self.characteristic_uuid)
        if characteristic is None:
            raise RuntimeError(
                f"Characteristic {self.characteristic_uuid} not found on connected device"
            )

        properties = {prop.lower() for prop in (characteristic.properties or [])}
        if "write" not in properties and "write-without-response" not in properties:
            raise RuntimeError(
                f"Characteristic {self.characteristic_uuid} is not writable. "
                f"Properties={sorted(properties)}"
            )

    async def _run_ble(self):
        last_error = None

        for connect_attempt in range(1, self.connect_retries + 1):
            device = await self._find_device()
            if device is None:
                if self.device_name:
                    last_error = RuntimeError(f"Could not find BLE device named '{self.device_name}'")
                else:
                    last_error = RuntimeError(
                        f"Could not find BLE device advertising service '{self.service_uuid}'"
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
                disconnect_event = asyncio.Event()

                def on_disconnected(_):
                    LOGGER.warning("BLE disconnected callback fired")
                    disconnect_event.set()

                async with BleakClient(
                    device,
                    timeout=self.connect_timeout,
                    disconnected_callback=on_disconnected,
                ) as client:
                    await self._validate_writable_characteristic(client)
                    self.status_changed.emit("Connected. Use sliders to send PWM commands.")
                    LOGGER.info("BLE connected")
                    while not self._stop_requested and client.is_connected and not disconnect_event.is_set():
                        command = self._pop_pending_command()
                        if command is not None and (
                            self._last_sent_command is None or abs(command - self._last_sent_command) > 1e-6
                        ):
                            duty_byte = max(0, min(255, int(round(command * 255.0))))
                            payload = struct.pack("<B", duty_byte)
                            await client.write_gatt_char(
                                self.characteristic_uuid,
                                payload,
                                response=True,
                            )
                            self._last_sent_command = command
                            LOGGER.info("PWM duty sent: %.3f", command)
                            self.command_sent.emit(command)

                        await asyncio.sleep(0.02)

                self.status_changed.emit("Disconnected")
                LOGGER.info("BLE disconnected")
                if self._stop_requested:
                    return

                last_error = RuntimeError("BLE disconnected before stop request")
            except TimeoutError as exc:
                last_error = exc
                LOGGER.warning(
                    "BLE connection attempt %s/%s timed out",
                    connect_attempt,
                    self.connect_retries,
                )
            except Exception as exc:
                last_error = exc
                LOGGER.warning(
                    "BLE connection attempt %s/%s failed: %s",
                    connect_attempt,
                    self.connect_retries,
                    exc,
                )

        if last_error is not None:
            raise last_error

        raise RuntimeError("BLE connection failed")