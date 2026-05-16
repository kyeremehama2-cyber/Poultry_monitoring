#ifndef SENSOR_NODE_H
#define SENSOR_NODE_H

#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <DHT.h>
#include <LiquidCrystal_I2C.h>

#define DHT_PIN 27
#define DHT_TYPE DHT22
#define GAS 32

/* Timing intervals - const can stay in .h */
const unsigned long Gas_space = 6000;
const unsigned long Humidity_space = 8000;
const unsigned long Temp_space = 10000;
const unsigned long LCD_space = 10000;
const unsigned long Publish_space = 15000;

/* WiFi */
extern const char* ssid;
extern const char* password;

/* MQTT */
extern const char* mqtt_server;
extern const int mqtt_port;
extern const char* mqtt_topic;

/* Objects - declare with extern, define in .cpp */
extern DHT dht;
extern LiquidCrystal_I2C lcd;
extern WiFiClient espClient;
extern PubSubClient mqttClient;

/* Timing variables */
extern unsigned long lastGas;
extern unsigned long lastHumidity;
extern unsigned long lastTemp;
extern unsigned long lastLCD;
extern unsigned long lastPublish;
extern unsigned long lastTHI;
/* Sensor values */
extern float gas_ppm;
extern float Humidity_value;
extern float Temp_value;
extern float THI_value;

/* Function declarations */
void ammoniaRead(unsigned long now);
void readHumidity(unsigned long now);
void readTemperature(unsigned long now);
void lcdDisplay(unsigned long now);
void THI(unsigned long now);
void reconnectMQTT();
void publishSensorData();

#endif