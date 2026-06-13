# built-ins
import sys

# external modules
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QCloseEvent
from PyQt6.QtWidgets import QApplication, QGridLayout, QGroupBox, QLabel, QMainWindow, QSlider, QVBoxLayout, QWidget

# local modules
from bluetooth_comms import *
from utils import get_logger


LOGGER = get_logger("pump_pwm_ble")


class PumpControlWindow(QMainWindow):
    def __init__(
        self,
        device_name: str,
        service_uuid: str,
        characteristic_uuid: str,
        connect_timeout: float,
        connect_retries: int,
    ):
        '''
        Initialise the PumpControlWindow, which is a QMainWindow that provides a GUI for controlling the PWM duty cycle
        of a pump via Bluetooth Low Energy (BLE).

        ### Arguments
        #### Required
        - `device_name` (str): the name of the BLE device to connect to
        - `service_uuid` (str): the UUID of the BLE service to interact with
        - `characteristic_uuid` (str): the UUID of the BLE characteristic to control the PWM
        - `connect_timeout` (float): the timeout for BLE connection attempts
        - `connect_retries` (int): the number of times to retry BLE connection
        '''

        # init QMainWindow
        super().__init__()

        # setup main window
        self.setWindowTitle("Pump PWM Control (BLE)")
        self.resize(700, 220)
        self.status_label = QLabel("Starting BLE client...")
        self.status_label.setWordWrap(True)

        # setup duty cycle slider and label
        self.duty_slider = QSlider(Qt.Orientation.Horizontal)
        self.duty_slider.setRange(0, SLIDER_STEPS)
        self.duty_slider.setValue(int(DEFAULT_DUTY * SLIDER_STEPS))
        self.duty_value_label = QLabel(f"{DEFAULT_DUTY:.3f}")

        # setup a timer to send the current PWM duty cycle after a short delay
        self.send_timer = QTimer(self)
        self.send_timer.setSingleShot(True)
        self.send_timer.setInterval(120)
        self.send_timer.timeout.connect(self.send_current_pwm)

        # setup main container and layout
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.addWidget(self.status_label)

        # setup PWM controls group box and layout
        controls_group = QGroupBox("PWM Controls")
        controls_layout = QGridLayout(controls_group)
        controls_layout.addWidget(QLabel("Duty Cycle (0.0 to 1.0)"), 0, 0)
        controls_layout.addWidget(self.duty_slider, 0, 1)
        controls_layout.addWidget(self.duty_value_label, 0, 2)
        layout.addWidget(controls_group)
        self.setCentralWidget(container)

        # setup BLE worker thread
        self.ble_worker = BleWorker(
            device_name=device_name,
            service_uuid=service_uuid,
            characteristic_uuid=characteristic_uuid,
            connect_timeout=connect_timeout,
            connect_retries=connect_retries,
        )
        self.ble_worker.status_changed.connect(self.on_ble_status_changed)
        self.ble_worker.error_occurred.connect(self.on_ble_error)
        self.ble_worker.command_sent.connect(self.on_command_sent)
        self.ble_worker.start()

        # connect the slider's valueChanged signal to the on_slider_changed method
        self.duty_slider.valueChanged.connect(self.on_slider_changed)
        self.on_slider_changed()

    def _slider_to_duty(self) -> float:
        '''
        Convert the current slider value to a duty cycle between 0.0 and 1.0.
        '''
        return self.duty_slider.value() / float(SLIDER_STEPS)

    def on_slider_changed(self) -> None:
        '''
        Update the duty cycle label and start the timer to send the current PWM duty cycle.
        '''
        duty = self._slider_to_duty()
        self.duty_value_label.setText(f"{duty:.3f}")
        self.send_timer.start()

    def send_current_pwm(self) -> None:
        '''
        Send the current PWM duty cycle to the BLE device via the BleWorker.
        '''
        duty = self._slider_to_duty()
        self.ble_worker.set_pwm_command(duty)

    def on_command_sent(self, duty: float) -> None:
        '''
        Update the status label to indicate that the PWM duty cycle has been sent.
        '''
        self.status_label.setText(f"Connected. Sent PWM duty: {duty:.3f}")

    def on_ble_status_changed(self, message: str) -> None:
        '''
        Send the current PWM duty cycle, if connected, and update the status label text.
        '''
        self.status_label.setText(message)
        if message.startswith("Connected"):
            self.send_current_pwm()

    def on_ble_error(self, message: str) -> None:
        '''
        Log an error message and update the status label to indicate that a BLE error has occurred.
        '''
        LOGGER.error("BLE error: %s", message)
        self.status_label.setText(f"BLE error: {message}")

    def closeEvent(self, event: QCloseEvent) -> None:
        '''
        Handle the window close event by stopping the BLE worker thread and waiting for it to finish.
        '''
        self.ble_worker.stop()
        self.ble_worker.wait(3000)
        super().closeEvent(event)


def main():
    LOGGER.setLevel("INFO")
    app = QApplication(sys.argv)
    window = PumpControlWindow(
        device_name=DEFAULT_DEVICE_NAME,
        service_uuid=DEFAULT_SERVICE_UUID,
        characteristic_uuid=DEFAULT_CHARACTERISTIC_UUID,
        connect_timeout=DEFAULT_CONNECT_TIMEOUT,
        connect_retries=DEFAULT_CONNECT_RETRIES,
    )
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()