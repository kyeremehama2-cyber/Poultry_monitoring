#include "sensor_node_new.h"

/* 
   Setup
    */
void setup() {
  Serial.begin(115200);

  analogReadResolution(12);
  analogSetAttenuation(ADC_11db);
  analogSetPinAttenuation(GAS, ADC_11db);

  dht.begin();
  lcd.init();
  lcd.backlight();

  /* WiFi */
  WiFi.begin(ssid, password);

  Serial.print("Connecting to WiFi");

  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\n✅ WiFi connected");
  Serial.println(WiFi.localIP());

  /* MQTT */
  mqttClient.setServer(mqtt_server, mqtt_port);
}

/* 
   Main Loop
    */
void loop() {
  unsigned long now = millis();

  ammoniaRead(now);
  readHumidity(now);
  readTemperature(now);
  lcdDisplay(now);
  THI(now);

  if (!mqttClient.connected()) {
    reconnectMQTT();
  }
  mqttClient.loop();

  if (now - lastPublish >= Publish_space) {
    lastPublish = now;
    publishSensorData();
  }
}

