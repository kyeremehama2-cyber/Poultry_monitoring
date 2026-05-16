#include "sensor_node_new.h"


/* Object definitions */
DHT dht(DHT_PIN, DHT_TYPE);
LiquidCrystal_I2C lcd(0x27, 16, 2);
WiFiClient espClient;
PubSubClient mqttClient(espClient);

/* WiFi */
const char* ssid = "Mind your manners";
const char* password = "amakumione1";

/* MQTT */
const char* mqtt_server = "10.238.177.214";
const int mqtt_port = 1883;
const char* mqtt_topic = "CapstoneTopic/node1";

/* Timing variables */
unsigned long lastGas = 0;
unsigned long lastHumidity = 0;
unsigned long lastTemp = 0;
unsigned long lastLCD = 0;
unsigned long lastPublish = 0;
unsigned long lastTHI=0;

/* Sensor values */
float gas_ppm = 0;
float Humidity_value = 0;
float Temp_value = 0;
float THI_value=0;


void ammoniaRead(unsigned long now) {
  if (now - lastGas >= Gas_space) {
    lastGas = now;

    float Gas_value = analogRead(GAS);
    float adc_v = (Gas_value / 4095.0) * 3.3;

    float Rs = ((3.3 / adc_v) - 1) * 20000;
    float Ro = 177780;

    float m = -0.243;
    float c = 0.323;
    float ratio = Rs / Ro;

    gas_ppm = pow(10, (log10(ratio) - c) / m);
    gas_ppm = round(gas_ppm*100)/100;
    Serial.print("NH3 ppm: ");
    Serial.println(gas_ppm);
    Serial.print("Gas_value: ");
    Serial.println(Gas_value);
    Serial.print("ratio: ");
    Serial.println(ratio);
  }
}

void readHumidity(unsigned long now) {
  if (now - lastHumidity >= Humidity_space) {
    lastHumidity = now;
    Humidity_value = dht.readHumidity();
    Serial.print("Humidity: ");
    Serial.println(Humidity_value);
  }
}

void readTemperature(unsigned long now) {
  if (now - lastTemp >= Temp_space) {
    lastTemp = now;
    Temp_value = dht.readTemperature();
    Serial.print("Temperature: ");
    Serial.println(Temp_value);
  }
}

void lcdDisplay(unsigned long now) {
  if (now - lastLCD >= LCD_space) {
    lastLCD = now;

    lcd.setCursor(0, 0);
    lcd.print("Gas ");
    lcd.print(gas_ppm, 1);

    lcd.setCursor(9, 0);
    lcd.print("T:");
    lcd.print(Temp_value);

    lcd.setCursor(0, 1);
    lcd.print("Hum: ");
    lcd.print(Humidity_value);
  }
}

/* 
   MQTT Functions
   */
void reconnectMQTT() {
  while (!mqttClient.connected()) {
    Serial.print("Connecting to MQTT...");
    if (mqttClient.connect("ESP32_Node1")) {
      Serial.println("connected");
    } else {
      Serial.print("failed, rc=");
      Serial.println(mqttClient.state());
      delay(2000);
    }
  }
}
void THI(unsigned long now){
  if (now - lastTHI >= 6000){
    lastTHI=now;
    THI_value= Temp_value - ((0.31-(0.0031*Humidity_value))*(Temp_value-14.4));
    Serial.print("THI");
    Serial.print(THI_value);
  }
}
void publishSensorData() {
  StaticJsonDocument<200> doc;
  doc["NodeID"]= 1;
  doc["temperature"] = Temp_value;
  doc["humidity"] = Humidity_value;
  doc["gas"] = gas_ppm;
  doc["THI"]=THI_value;

  char buffer[256];
  serializeJson(doc, buffer);

  mqttClient.publish(mqtt_topic, buffer);

  Serial.println("📤 Published MQTT data:");
  Serial.println(buffer);
}
