/*
  ============================================================
  LIMA SMART CORE CITY — Módulo Vigilancia / Sonido KY-037
  FASE 1: Device ID FIJO (corrección crítica), ArduinoJson, auth MQTT
  Sensor   : KY-037 (salida analógica AO)
  Placa    : ESP32 (WROOM / WROVER) — separado del ESP32-CAM
  ============================================================

  NOTA IMPORTANTE (Fase 1):
    El KY-037 corre en un ESP32 genérico INDEPENDIENTE del ESP32-CAM.
    El ESP32-CAM no tiene pines GPIO libres suficientes para ambos.
    Este módulo publica en lscc/vigilancia/sonido con DEVICE_ID fijo.

  LIBRERÍAS REQUERIDAS:
    - PubSubClient  (Nick O'Leary)
    - ArduinoJson   (Benoit Blanchon)

  CONEXIÓN:
    KY-037 AO  → GPIO 34  (ADC1, compatible con WiFi activo)
    KY-037 VCC → 3.3V
    KY-037 GND → GND
    KY-037 DO  → No usado (usamos AO para más resolución)
*/

#include <WiFi.h>
#include <ESPmDNS.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include "secrets.h"

// ============================================================
// CONFIGURACIÓN
// ============================================================
const char* WIFI_SSID     = LSCC_WIFI_SSID;
const char* WIFI_PASS     = LSCC_WIFI_PASSWORD;

const char* MQTT_BROKER   = LSCC_MQTT_BROKER;
const int   MQTT_PORT     = 1883;
const char* MQTT_USER     = LSCC_MQTT_USER;
const char* MQTT_PASSWORD = LSCC_MQTT_PASSWORD;

// FASE 1 — CORRECCIÓN CRÍTICA: Device ID fijo, nunca aleatorio
const char* DEVICE_ID     = "ESP32_KY037_01";
const char* FIRMWARE_VERSION = "1.1.0";
const char* SCHEMA_VERSION = "1.0";

// Tópicos
const char* TOPIC_SONIDO  = "lscc/vigilancia/sonido";
const char* TOPIC_STATUS  = "lscc/sistema/status";

// Sensor
#define PIN_SONIDO        34
#define UMBRAL_SONIDO     100          // RAW mínimo para evento relevante
const unsigned long INTERVALO_ENVIO = 3000;   // cada 3 s

// ============================================================
// OBJETOS
// ============================================================
WiFiClient   espClient;
PubSubClient client(espClient);
unsigned long ultimoEnvio = 0;

// ============================================================
// WiFi
// ============================================================
void conectarWiFi() {
  Serial.print("[WiFi] Conectando a ");
  Serial.println(WIFI_SSID);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println();
  Serial.print("[WiFi] IP: ");
  Serial.println(WiFi.localIP());
}

// ============================================================
// MQTT — ID fijo, con auth
// ============================================================
void conectarMQTT() {
  while (!client.connected()) {
    Serial.print("[MQTT] Conectando con auth... ");

    // FASE 1: ID fijo — nunca usar random()
    StaticJsonDocument<160> willDoc;
    willDoc["device_id"] = DEVICE_ID;
    willDoc["modulo"] = "vigilancia";
    willDoc["status"] = "offline";
    willDoc["schema_version"] = SCHEMA_VERSION;
    char willPayload[160];
    serializeJson(willDoc, willPayload);

    if (client.connect(DEVICE_ID, MQTT_USER, MQTT_PASSWORD,
                       TOPIC_STATUS, 1, true, willPayload)) {
      Serial.println("OK");

      StaticJsonDocument<384> doc;
      doc["device_id"] = DEVICE_ID;
      doc["status"]    = "online";
      doc["modulo"]    = "vigilancia";
      doc["sensor"]    = "KY-037";
      doc["modo"]      = "analogico";
      doc["pin"]       = "GPIO34";
      doc["schema_version"] = SCHEMA_VERSION;
      doc["firmware_version"] = FIRMWARE_VERSION;
      doc["uptime_ms"] = millis();
      doc["rssi_dbm"] = WiFi.RSSI();
      doc["ip"] = WiFi.localIP().toString();
      char buf[384];
      serializeJson(doc, buf);
      client.publish(TOPIC_STATUS, buf, true);
      Serial.println("[MQTT] Status enviado");

    } else {
      Serial.print("Fallo rc=");
      Serial.print(client.state());
      Serial.println(" | Reintentando en 3 s...");
      delay(3000);
    }
  }
}

// ============================================================
// CLASIFICAR NIVEL DE SONIDO
// ============================================================
const char* clasificarSonido(int raw) {
  if (raw < 100)  return "bajo";
  if (raw < 1000) return "medio";
  return "alto";
}

// ============================================================
// SETUP
// ============================================================
void setup() {
  Serial.begin(115200);
  delay(1000);
  Serial.println("=============================================");
  Serial.println(" Lima Smart — Módulo Sonido KY-037 Fase 1");
  Serial.println(" Device ID: ESP32_KY037_01 (FIJO)");
  Serial.println("=============================================");

  analogReadResolution(12);
  analogSetPinAttenuation(PIN_SONIDO, ADC_11db);
  Serial.println("[KY-037] ADC configurado en GPIO34");

  conectarWiFi();
  MDNS.begin("lscc-ky037");
  client.setServer(MQTT_BROKER, MQTT_PORT);
}

// ============================================================
// LOOP
// ============================================================
void loop() {
  if (WiFi.status() != WL_CONNECTED) conectarWiFi();
  if (!client.connected())            conectarMQTT();
  client.loop();

  // Lectura continua para el Serial Monitor (rápida)
  int   rawSonido  = analogRead(PIN_SONIDO);
  float voltaje    = rawSonido * (3.3f / 4095.0f);
  int   porcentaje = map(rawSonido, 0, 4095, 0, 100);
  const char* nivel = clasificarSonido(rawSonido);

  Serial.printf("[KY-037] RAW:%d | V:%.2f | %d%% | %s\n",
    rawSonido, voltaje, porcentaje, nivel);

  // Publicar por MQTT cada INTERVALO_ENVIO ms
  unsigned long ahora = millis();
  if (ahora - ultimoEnvio < INTERVALO_ENVIO) {
    delay(300);
    return;
  }
  ultimoEnvio = ahora;

  const char* evento = (rawSonido >= UMBRAL_SONIDO)
    ? "sonido_detectado"
    : "sin_sonido_relevante";

  StaticJsonDocument<256> doc;
  doc["device_id"]  = DEVICE_ID;
  doc["modulo"]     = "vigilancia";
  doc["sensor"]     = "KY-037";
  doc["modo"]       = "analogico";
  doc["evento"]     = evento;
  doc["value"]      = rawSonido;
  doc["voltage"]    = serialized(String(voltaje, 2));
  doc["porcentaje"] = porcentaje;
  doc["nivel"]      = nivel;
  doc["unit"]       = "raw_adc";
  doc["schema_version"] = SCHEMA_VERSION;
  doc["uptime_ms"] = millis();

  char buf[256];
  serializeJson(doc, buf);
  bool ok = client.publish(TOPIC_SONIDO, buf);
  Serial.printf("[MQTT] sonido -> %s\n", ok ? "OK" : "FALLO");
}
