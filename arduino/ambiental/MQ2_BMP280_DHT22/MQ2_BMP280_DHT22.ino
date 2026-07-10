/*
  ============================================================
  LIMA SMART CORE CITY — Módulo Ambiental
  WiFiManager + MQTT + Reset por botón + Sensores
  Sensores : DHT22 · BMP280 · MQ-2
  Placa    : ESP32 WROOM / WROVER
  ============================================================
*/

#include <WiFi.h>
#include <ESPmDNS.h>
#include <WiFiManager.h>
#include <Preferences.h>
#include <PubSubClient.h>
#include <Wire.h>
#include <Adafruit_BMP280.h>
#include "DHT.h"
#include <ArduinoJson.h>
#include "secrets.h"

// ============================================================
// CONFIGURACIÓN
// ============================================================
#define RESET_CONFIG_PIN 27

char MQTT_BROKER[40]   = LSCC_MQTT_BROKER;
char MQTT_USER[30]     = LSCC_MQTT_USER;
char MQTT_PASSWORD[30] = LSCC_MQTT_PASSWORD;

const int MQTT_PORT = 1883;
const char* DEVICE_ID = "ESP32_AIRE_01";
const char* FIRMWARE_VERSION = "1.1.0";
const char* SCHEMA_VERSION = "1.0";
const char* CONFIG_AP_NAME = "LSCC_AIRE_CONFIG";
const int MQTT_MAX_FAILED_ATTEMPTS = 5;

// Pines sensores
#define DHT_PIN   4
#define DHT_TYPE  DHT22
#define MQ2_PIN   34
#define I2C_SDA   21
#define I2C_SCL   22

// Tiempos
const unsigned long SEND_INTERVAL = 5000;
const unsigned long MQ2_WARMUP_MS = 30000;

// Tópicos MQTT
const char* TOPIC_TEMPERATURA = "lscc/ambiental/temperatura";
const char* TOPIC_HUMEDAD     = "lscc/ambiental/humedad";
const char* TOPIC_PRESION     = "lscc/ambiental/presion";
const char* TOPIC_GAS         = "lscc/ambiental/gas";
const char* TOPIC_STATUS      = "lscc/sistema/status";

// ============================================================
// OBJETOS
// ============================================================
WiFiClient espClient;
PubSubClient mqttClient(espClient);
WiFiManager wm;
Preferences prefs;

DHT dht(DHT_PIN, DHT_TYPE);
Adafruit_BMP280 bmp;

bool bmpDisponible = false;
bool mq2Calentado  = false;

unsigned long lastSend = 0;

// ============================================================
// CONFIGURACIÓN MQTT GUARDADA
// ============================================================
void cargarConfigMQTT() {
  prefs.begin("lscc", true);

  String broker = prefs.getString("broker", MQTT_BROKER);
  String user   = prefs.getString("user", MQTT_USER);
  String pass   = prefs.getString("pass", MQTT_PASSWORD);

  broker.toCharArray(MQTT_BROKER, sizeof(MQTT_BROKER));
  user.toCharArray(MQTT_USER, sizeof(MQTT_USER));
  pass.toCharArray(MQTT_PASSWORD, sizeof(MQTT_PASSWORD));

  prefs.end();
}

void guardarConfigMQTT() {
  prefs.begin("lscc", false);

  prefs.putString("broker", MQTT_BROKER);
  prefs.putString("user", MQTT_USER);
  prefs.putString("pass", MQTT_PASSWORD);

  prefs.end();
}

void abrirPortalConfigMQTT(const char* motivo) {
  Serial.println();
  Serial.print("[WiFiManager] Abriendo portal de configuracion: ");
  Serial.println(motivo);

  WiFiManager portal;
  WiFiManagerParameter custom_broker("broker", "MQTT Broker IP/Host", MQTT_BROKER, 40);
  WiFiManagerParameter custom_user("user", "MQTT User", MQTT_USER, 30);
  WiFiManagerParameter custom_pass("pass", "MQTT Password", MQTT_PASSWORD, 30);

  portal.addParameter(&custom_broker);
  portal.addParameter(&custom_user);
  portal.addParameter(&custom_pass);
  portal.setConfigPortalTimeout(0);

  bool configurado = portal.startConfigPortal(CONFIG_AP_NAME, LSCC_CONFIG_AP_PASSWORD);

  if (!configurado) {
    Serial.println("[WiFiManager] Portal cerrado sin configurar. Reiniciando...");
    delay(1000);
    ESP.restart();
  }

  strncpy(MQTT_BROKER, custom_broker.getValue(), sizeof(MQTT_BROKER));
  strncpy(MQTT_USER, custom_user.getValue(), sizeof(MQTT_USER));
  strncpy(MQTT_PASSWORD, custom_pass.getValue(), sizeof(MQTT_PASSWORD));

  MQTT_BROKER[sizeof(MQTT_BROKER) - 1] = '\0';
  MQTT_USER[sizeof(MQTT_USER) - 1] = '\0';
  MQTT_PASSWORD[sizeof(MQTT_PASSWORD) - 1] = '\0';

  guardarConfigMQTT();
  mqttClient.setServer(MQTT_BROKER, MQTT_PORT);

  Serial.print("[MQTT] Nuevo broker guardado: ");
  Serial.println(MQTT_BROKER);
}

// ============================================================
// RESET CONFIG POR BOTÓN
// ============================================================
void revisarBotonResetConfig() {
  static unsigned long tiempoPresionado = 0;

  if (digitalRead(RESET_CONFIG_PIN) == LOW) {
    if (tiempoPresionado == 0) {
      tiempoPresionado = millis();
    }

    if (millis() - tiempoPresionado >= 3000) {
      Serial.println("[RESET] Botón presionado 3 segundos");
      Serial.println("[RESET] Borrando WiFi y configuración MQTT...");

      wm.resetSettings();

      prefs.begin("lscc", false);
      prefs.clear();
      prefs.end();

      delay(1000);
      ESP.restart();
    }
  } else {
    tiempoPresionado = 0;
  }
}

// ============================================================
// WIFI MANAGER
// ============================================================
void conectarWiFiManager() {
  cargarConfigMQTT();

  WiFiManagerParameter custom_broker("broker", "MQTT Broker IP", MQTT_BROKER, 40);
  WiFiManagerParameter custom_user("user", "MQTT User", MQTT_USER, 30);
  WiFiManagerParameter custom_pass("pass", "MQTT Password", MQTT_PASSWORD, 30);

  wm.addParameter(&custom_broker);
  wm.addParameter(&custom_user);
  wm.addParameter(&custom_pass);

  // Sin timeout: espera hasta que configures WiFi y MQTT
  wm.setConfigPortalTimeout(0);

  Serial.println("[WiFiManager] Buscando WiFi guardado...");
  Serial.println("[WiFiManager] Si no existe, abrirá portal: LSCC_AIRE_CONFIG");

  bool conectado = wm.autoConnect(CONFIG_AP_NAME, LSCC_CONFIG_AP_PASSWORD);

  if (!conectado) {
    Serial.println("[WiFiManager] No se pudo conectar. Reiniciando...");
    delay(3000);
    ESP.restart();
  }

  strncpy(MQTT_BROKER, custom_broker.getValue(), sizeof(MQTT_BROKER));
  strncpy(MQTT_USER, custom_user.getValue(), sizeof(MQTT_USER));
  strncpy(MQTT_PASSWORD, custom_pass.getValue(), sizeof(MQTT_PASSWORD));

  MQTT_BROKER[sizeof(MQTT_BROKER) - 1] = '\0';
  MQTT_USER[sizeof(MQTT_USER) - 1] = '\0';
  MQTT_PASSWORD[sizeof(MQTT_PASSWORD) - 1] = '\0';

  guardarConfigMQTT();

  Serial.println("[WiFi] Conectado correctamente");
  Serial.print("[WiFi] IP ESP32: ");
  Serial.println(WiFi.localIP());

  Serial.print("[MQTT] Broker guardado: ");
  Serial.println(MQTT_BROKER);
}

// ============================================================
// MQTT
// ============================================================
void conectarMQTT() {
  int intentosFallidos = 0;

  while (!mqttClient.connected()) {
    revisarBotonResetConfig();

    if (strlen(MQTT_BROKER) == 0) {
      abrirPortalConfigMQTT("no hay broker MQTT configurado");
      intentosFallidos = 0;
    }

    Serial.print("[MQTT] Conectando con autenticación... ");

    StaticJsonDocument<160> willDoc;
    willDoc["device_id"] = DEVICE_ID;
    willDoc["modulo"] = "ambiental";
    willDoc["status"] = "offline";
    willDoc["schema_version"] = SCHEMA_VERSION;
    char willPayload[160];
    serializeJson(willDoc, willPayload);

    const char* mqttUser = strlen(MQTT_USER) > 0 ? MQTT_USER : nullptr;
    const char* mqttPass = strlen(MQTT_USER) > 0 ? MQTT_PASSWORD : nullptr;

    if (mqttClient.connect(DEVICE_ID, mqttUser, mqttPass,
                           TOPIC_STATUS, 1, true, willPayload)) {
      Serial.println("OK");

      StaticJsonDocument<384> doc;
      doc["device_id"] = DEVICE_ID;
      doc["modulo"]    = "calidad_aire";
      doc["status"]    = "online";
      doc["mq2_listo"] = mq2Calentado;
      doc["schema_version"] = SCHEMA_VERSION;
      doc["firmware_version"] = FIRMWARE_VERSION;
      doc["uptime_ms"] = millis();
      doc["rssi_dbm"] = WiFi.RSSI();
      doc["ip"] = WiFi.localIP().toString();

      char buf[384];
      serializeJson(doc, buf);

      mqttClient.publish(TOPIC_STATUS, buf, true);
    } else {
      intentosFallidos++;
      Serial.print("Fallo rc=");
      Serial.print(mqttClient.state());
      Serial.println(" | Reintentando en 3 s...");

      if (intentosFallidos >= MQTT_MAX_FAILED_ATTEMPTS) {
        abrirPortalConfigMQTT("no se pudo conectar al broker MQTT");
        intentosFallidos = 0;
      }

      delay(3000);
    }
  }
}

// ============================================================
// PUBLICAR JSON
// ============================================================
void publicar(const char* topic, JsonDocument& doc) {
  doc["schema_version"] = SCHEMA_VERSION;
  doc["uptime_ms"] = millis();
  char buf[256];
  serializeJson(doc, buf);

  bool ok = mqttClient.publish(topic, buf);

  Serial.print("[MQTT] ");
  Serial.print(topic);
  Serial.print(" -> ");
  Serial.println(ok ? "OK" : "FALLO");
}

// ============================================================
// CLASIFICACIÓN MQ-2
// ============================================================
String clasificarGas(float voltage) {
  if (voltage < 1.0) return "normal";
  if (voltage < 2.0) return "preventivo";
  return "elevado";
}

// ============================================================
// INICIALIZAR SENSORES
// ============================================================
void inicializarSensores() {
  Serial.println("[SENSORES] Inicializando sensores...");

  dht.begin();
  Serial.println("[DHT22] Inicializado");

  Wire.begin(I2C_SDA, I2C_SCL);

  if (bmp.begin(0x76)) {
    bmpDisponible = true;
    Serial.println("[BMP280] Encontrado en 0x76");
  } else if (bmp.begin(0x77)) {
    bmpDisponible = true;
    Serial.println("[BMP280] Encontrado en 0x77");
  } else {
    bmpDisponible = false;
    Serial.println("[BMP280] No encontrado — se enviará -1");
  }

  analogReadResolution(12);
  analogSetPinAttenuation(MQ2_PIN, ADC_11db);
}

// ============================================================
// PRECALENTAR MQ-2
// ============================================================
void precalentarMQ2() {
  Serial.println("[MQ-2] Precalentando 30 segundos...");

  unsigned long inicio = millis();

  while (millis() - inicio < MQ2_WARMUP_MS) {
    revisarBotonResetConfig();

    int segundos = (millis() - inicio) / 1000;

    Serial.print("[MQ-2] Precalentamiento: ");
    Serial.print(segundos + 1);
    Serial.println(" / 30 s");

    delay(1000);
  }

  mq2Calentado = true;
  Serial.println("[MQ-2] Listo para lecturas");
}

// ============================================================
// SETUP
// ============================================================
void setup() {
  Serial.begin(115200);
  delay(1000);

  pinMode(RESET_CONFIG_PIN, INPUT_PULLUP);

  Serial.println("======================================");
  Serial.println(" Lima Smart — Módulo Ambiental");
  Serial.println("======================================");

  // 1. Primero WiFi + portal de configuración
  conectarWiFiManager();
  MDNS.begin("lscc-aire");

  // 2. Recién cuando hay WiFi, configurar MQTT
  mqttClient.setServer(MQTT_BROKER, MQTT_PORT);

  // 3. Luego inicializar sensores
  inicializarSensores();

  // 4. Luego precalentar MQ-2
  precalentarMQ2();
}

// ============================================================
// LOOP
// ============================================================
void loop() {
  revisarBotonResetConfig();

  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[WiFi] Conexión perdida. Reiniciando...");
    delay(2000);
    ESP.restart();
  }

  if (!mqttClient.connected()) {
    conectarMQTT();
  }

  mqttClient.loop();

  unsigned long now = millis();

  if (now - lastSend < SEND_INTERVAL) {
    return;
  }

  lastSend = now;

  Serial.println("\n========== Enviando datos ==========");

  // ==========================================================
  // DHT22
  // ==========================================================
  float temperatura = dht.readTemperature();
  float humedad = dht.readHumidity();

  bool dhtOk = !isnan(temperatura) && !isnan(humedad);

  {
    StaticJsonDocument<160> doc;
    doc["device_id"] = DEVICE_ID;
    doc["sensor"] = "DHT22";
    doc["value"] = dhtOk ? temperatura : (float)-1;
    doc["unit"] = "C";
    doc["estado"] = dhtOk ? "ok" : "sin_datos";

    publicar(TOPIC_TEMPERATURA, doc);
  }

  {
    StaticJsonDocument<160> doc;
    doc["device_id"] = DEVICE_ID;
    doc["sensor"] = "DHT22";
    doc["value"] = dhtOk ? humedad : (float)-1;
    doc["unit"] = "%HR";
    doc["estado"] = dhtOk ? "ok" : "sin_datos";

    publicar(TOPIC_HUMEDAD, doc);
  }

  if (dhtOk) {
    Serial.printf("[DHT22] %.1f°C | %.1f%%\n", temperatura, humedad);
  } else {
    Serial.println("[DHT22] Error de lectura");
  }

  // ==========================================================
  // BMP280
  // ==========================================================
  {
    StaticJsonDocument<160> doc;
    doc["device_id"] = DEVICE_ID;
    doc["sensor"] = "BMP280";

    if (bmpDisponible) {
      float presion = bmp.readPressure() / 100.0F;
      bool presOk = (presion > 300 && presion < 1200);

      doc["value"] = presOk ? presion : (float)-1;
      doc["unit"] = "hPa";
      doc["estado"] = presOk ? "ok" : "sin_datos";

      if (presOk) {
        Serial.printf("[BMP280] %.2f hPa\n", presion);
      }
    } else {
      doc["value"] = -1;
      doc["unit"] = "hPa";
      doc["estado"] = "sin_datos";
    }

    publicar(TOPIC_PRESION, doc);
  }

  // ==========================================================
  // MQ-2
  // ==========================================================
  {
    int raw = analogRead(MQ2_PIN);
    float voltage = raw * (3.3f / 4095.0f);
    String nivel = clasificarGas(voltage);

    StaticJsonDocument<192> doc;
    doc["device_id"] = DEVICE_ID;
    doc["sensor"] = "MQ-2";
    doc["value_raw"] = raw;
    doc["voltage"] = voltage;
    doc["nivel"] = nivel;
    doc["estado"] = mq2Calentado ? "ok" : "calentando";

    publicar(TOPIC_GAS, doc);

    Serial.printf("[MQ-2] RAW:%d | V:%.2f | %s\n", raw, voltage, nivel.c_str());
  }

  // ==========================================================
  // STATUS GENERAL
  // ==========================================================
  {
    StaticJsonDocument<256> doc;
    doc["device_id"] = DEVICE_ID;
    doc["modulo"] = "calidad_aire";
    doc["status"] = "online";
    doc["dht22"] = dhtOk ? "ok" : "sin_datos";
    doc["bmp280"] = bmpDisponible ? "ok" : "sin_datos";
    doc["mq2"] = mq2Calentado ? "ok" : "calentando";
    doc["schema_version"] = SCHEMA_VERSION;
    doc["firmware_version"] = FIRMWARE_VERSION;
    doc["uptime_ms"] = millis();
    doc["rssi_dbm"] = WiFi.RSSI();

    publicar(TOPIC_STATUS, doc);
  }

  Serial.println("=====================================");
}
