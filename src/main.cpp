#include <Arduino.h>
#include <ArduinoBLE.h>

constexpr uint8_t PWM_PIN = 3;
constexpr char DEVICE_NAME[] = "PWM-UnoWiFiRev2";

constexpr char PWM_SERVICE_UUID[] = "19B10000-E8F2-537E-4F6C-D104768A1214";
constexpr char PWM_DUTY_CHAR_UUID[] = "19B10001-E8F2-537E-4F6C-D104768A1214";

BLEService pwmService(PWM_SERVICE_UUID);
BLEByteCharacteristic pwmDutyCharacteristic(PWM_DUTY_CHAR_UUID, BLEWrite);

void setup() {
    pinMode(PWM_PIN, OUTPUT);
    analogWrite(PWM_PIN, 0);

    if (!BLE.begin()) {
        while (true) {
            delay(1000);
        }
    }

    BLE.setLocalName(DEVICE_NAME);
    BLE.setAdvertisedService(pwmService);

    pwmService.addCharacteristic(pwmDutyCharacteristic);
    BLE.addService(pwmService);
    pwmDutyCharacteristic.writeValue((uint8_t)0);

    BLE.advertise();
}

void loop() {
    BLE.poll();

    if (pwmDutyCharacteristic.written()) {
        analogWrite(PWM_PIN, pwmDutyCharacteristic.value());
    }
}
