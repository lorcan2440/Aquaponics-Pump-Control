#include <Arduino.h>
#include <ArduinoBLE.h>

constexpr uint8_t PIR_PIN = 2;
constexpr unsigned long SAMPLE_INTERVAL_MS = 50;
constexpr unsigned long DEBUG_INTERVAL_MS = 2000;

BLEService pirService("19B10000-E8F2-537E-4F6C-D104768A1214");
BLEByteCharacteristic pirStateCharacteristic(
    "19B10001-E8F2-537E-4F6C-D104768A1214",
    BLERead | BLENotify
);

void setup() {
  pinMode(PIR_PIN, INPUT);
  Serial.begin(115200);
  const unsigned long serialWaitStartMs = millis();
  while (!Serial && millis() - serialWaitStartMs < 3000) {
    delay(10);
  }

  Serial.println(F("[BOOT] UNO WiFi Rev2 PIR BLE firmware starting"));
  Serial.print(F("[BOOT] Service UUID: "));
  Serial.println(F("19B10000-E8F2-537E-4F6C-D104768A1214"));
  Serial.print(F("[BOOT] Characteristic UUID: "));
  Serial.println(F("19B10001-E8F2-537E-4F6C-D104768A1214"));

  if (!BLE.begin()) {
    Serial.println(F("[ERROR] BLE.begin() failed"));
    while (true) {
      delay(1000);
    }
  }

  BLE.setLocalName("PIR-UnoWiFiRev2");
  BLE.setDeviceName("PIR-UnoWiFiRev2");
  BLE.setAdvertisedService(pirService);

  pirService.addCharacteristic(pirStateCharacteristic);
  BLE.addService(pirService);
  pirStateCharacteristic.writeValue((uint8_t)0);

  BLE.advertise();
  Serial.println(F("[BLE] Advertising started with name PIR-UnoWiFiRev2"));
}

void loop() {
  static unsigned long lastSampleMs = 0;
  static unsigned long lastDebugMs = 0;
  static uint8_t lastPirState = 255;
  static bool wasConnected = false;

  const unsigned long now = millis();

  BLE.poll();
  BLEDevice central = BLE.central();
  const bool isConnected = static_cast<bool>(central);

  if (isConnected && !wasConnected) {
    Serial.print(F("[BLE] Central connected: "));
    Serial.println(central.address());
  }

  if (!isConnected && wasConnected) {
    Serial.println(F("[BLE] Central disconnected"));
  }

  wasConnected = isConnected;

  if (now - lastSampleMs >= SAMPLE_INTERVAL_MS) {
    lastSampleMs = now;
    const uint8_t pirState = digitalRead(PIR_PIN) == HIGH ? 1 : 0;
    pirStateCharacteristic.writeValue(pirState);

    if (pirState != lastPirState) {
      Serial.print(F("[PIR] State changed to "));
      Serial.println(pirState);
      lastPirState = pirState;
    }
  }

  if (now - lastDebugMs >= DEBUG_INTERVAL_MS) {
    lastDebugMs = now;
    Serial.print(F("[DBG] Advertising=1 Connected="));
    Serial.print(isConnected ? 1 : 0);
    Serial.print(F(" PIR="));
    if (lastPirState == 255) {
      Serial.println(F("N/A"));
    } else {
      Serial.println(lastPirState);
    }
  }
}