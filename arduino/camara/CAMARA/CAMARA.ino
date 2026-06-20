/*
  ============================================================
  LIMA SMART CORE CITY — Módulo Videovigilancia
  ESP32-CAM AI Thinker + KY-037 + MQTT + WiFiManager

  FUNCIONES:
    - Configura WiFi y MQTT desde portal WiFiManager.
    - Lee sonido digital del KY-037.
    - Envía estado de sonido por MQTT.
    - Toma una foto cada 10 segundos.
    - Envía la foto JPEG por MQTT.

  CONEXIÓN:
    KY-037 DO  -> GPIO13
    KY-037 VCC -> 3.3V o 5V
    KY-037 GND -> GND

  PLACA:
    AI Thinker ESP32-CAM
  ============================================================
*/

#include <WiFi.h>
#include <WiFiManager.h>
#include <Preferences.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include "esp_camera.h"

// ============================================================
// CONFIGURACIÓN GENERAL
// ============================================================

const char* DEVICE_ID = "ESP32_CAM_VIGILANCIA_01";

// Portal de configuración
const char* AP_NAME = "LSCC_VIGILANCIA_SETUP";
const char* AP_PASS = "lscc12345";

// MQTT
const int MQTT_PORT = 1883;

char MQTT_BROKER[40]   = "192.168.100.136";
char MQTT_USER[30]     = "lscc_user";
char MQTT_PASSWORD[30] = "lscc2025";

// Tópicos MQTT
const char* TOPIC_SONIDO      = "lscc/vigilancia/sonido";
const char* TOPIC_IMAGEN      = "lscc/vigilancia/imagen";
const char* TOPIC_IMAGEN_INFO = "lscc/vigilancia/imagen/info";
const char* TOPIC_STATUS      = "lscc/sistema/status";

// Sensor sonido KY-037 digital
#define SOUND_DO_PIN 13

// Intervalos
const unsigned long INTERVALO_SONIDO = 1000;
const unsigned long INTERVALO_IMAGEN = 10000;

// Buffer reducido para evitar reinicios
const size_t MQTT_BUFFER_SIZE = 12000;

// ============================================================
// PINES CÁMARA AI THINKER ESP32-CAM
// ============================================================

#define PWDN_GPIO_NUM     32
#define RESET_GPIO_NUM    -1
#define XCLK_GPIO_NUM      0
#define SIOD_GPIO_NUM     26
#define SIOC_GPIO_NUM     27

#define Y9_GPIO_NUM       35
#define Y8_GPIO_NUM       34
#define Y7_GPIO_NUM       39
#define Y6_GPIO_NUM       36
#define Y5_GPIO_NUM       21
#define Y4_GPIO_NUM       19
#define Y3_GPIO_NUM       18
#define Y2_GPIO_NUM        5

#define VSYNC_GPIO_NUM    25
#define HREF_GPIO_NUM     23
#define PCLK_GPIO_NUM     22

// ============================================================
// OBJETOS
// ============================================================

WiFiClient espClient;
PubSubClient mqttClient(espClient);
WiFiManager wm;
Preferences prefs;

bool camaraDisponible = false;

unsigned long ultimoEnvioSonido = 0;
unsigned long ultimoEnvioImagen = 0;

// ============================================================
// CARGAR CONFIGURACIÓN MQTT
// ============================================================

void cargarConfigMQTT() {
  prefs.begin("lscc_vig", true);

  String broker = prefs.getString("broker", MQTT_BROKER);
  String user   = prefs.getString("user", MQTT_USER);
  String pass   = prefs.getString("pass", MQTT_PASSWORD);

  broker.toCharArray(MQTT_BROKER, sizeof(MQTT_BROKER));
  user.toCharArray(MQTT_USER, sizeof(MQTT_USER));
  pass.toCharArray(MQTT_PASSWORD, sizeof(MQTT_PASSWORD));

  prefs.end();
}

// ============================================================
// GUARDAR CONFIGURACIÓN MQTT
// ============================================================

void guardarConfigMQTT() {
  prefs.begin("lscc_vig", false);

  prefs.putString("broker", MQTT_BROKER);
  prefs.putString("user", MQTT_USER);
  prefs.putString("pass", MQTT_PASSWORD);

  prefs.end();

  Serial.println("[CONFIG] MQTT guardado correctamente.");
}

// ============================================================
// WIFI MANAGER
// ============================================================

void conectarWiFiManager() {
  cargarConfigMQTT();

  WiFiManagerParameter custom_broker(
    "broker",
    "MQTT Broker IP",
    MQTT_BROKER,
    40
  );

  WiFiManagerParameter custom_user(
    "user",
    "MQTT User",
    MQTT_USER,
    30
  );

  WiFiManagerParameter custom_pass(
    "pass",
    "MQTT Password",
    MQTT_PASSWORD,
    30
  );

  wm.addParameter(&custom_broker);
  wm.addParameter(&custom_user);
  wm.addParameter(&custom_pass);

  // Sin timeout: espera hasta que configures
  wm.setConfigPortalTimeout(0);

  Serial.println();
  Serial.println("====================================");
  Serial.println("[WiFiManager] Buscando WiFi guardado...");
  Serial.println("[WiFiManager] Si no existe, abre portal:");
  Serial.println(AP_NAME);
  Serial.println("====================================");

  bool conectado = wm.autoConnect(AP_NAME, AP_PASS);

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

  Serial.println();
  Serial.println("[WiFi] Conectado correctamente");
  Serial.print("[WiFi] SSID: ");
  Serial.println(WiFi.SSID());
  Serial.print("[WiFi] IP ESP32-CAM: ");
  Serial.println(WiFi.localIP());

  Serial.print("[MQTT] Broker: ");
  Serial.println(MQTT_BROKER);
}

// ============================================================
// INICIALIZAR CÁMARA
// ============================================================

bool inicializarCamara() {
  camera_config_t config;

  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer   = LEDC_TIMER_0;

  config.pin_d0 = Y2_GPIO_NUM;
  config.pin_d1 = Y3_GPIO_NUM;
  config.pin_d2 = Y4_GPIO_NUM;
  config.pin_d3 = Y5_GPIO_NUM;
  config.pin_d4 = Y6_GPIO_NUM;
  config.pin_d5 = Y7_GPIO_NUM;
  config.pin_d6 = Y8_GPIO_NUM;
  config.pin_d7 = Y9_GPIO_NUM;

  config.pin_xclk = XCLK_GPIO_NUM;
  config.pin_pclk = PCLK_GPIO_NUM;
  config.pin_vsync = VSYNC_GPIO_NUM;
  config.pin_href = HREF_GPIO_NUM;

  config.pin_sccb_sda = SIOD_GPIO_NUM;
  config.pin_sccb_scl = SIOC_GPIO_NUM;

  config.pin_pwdn = PWDN_GPIO_NUM;
  config.pin_reset = RESET_GPIO_NUM;

  config.xclk_freq_hz = 20000000;
  config.pixel_format = PIXFORMAT_JPEG;

  // Imagen pequeña para evitar reinicios por memoria/MQTT
  config.frame_size = FRAMESIZE_QQVGA;   // 160x120
  config.jpeg_quality = 18;
  config.fb_count = 1;

  if (psramFound()) {
    Serial.println("[CAMARA] PSRAM detectada.");
    config.fb_location = CAMERA_FB_IN_PSRAM;
  } else {
    Serial.println("[CAMARA] PSRAM no detectada. Usando DRAM.");
    config.fb_location = CAMERA_FB_IN_DRAM;
  }

  esp_err_t err = esp_camera_init(&config);

  if (err != ESP_OK) {
    Serial.printf("[CAMARA] Error al iniciar cámara: 0x%x\n", err);
    return false;
  }

  Serial.println("[CAMARA] Inicializada correctamente.");
  return true;
}

// ============================================================
// CONECTAR MQTT
// ============================================================

void conectarMQTT() {
  while (!mqttClient.connected()) {
    Serial.print("[MQTT] Conectando a ");
    Serial.print(MQTT_BROKER);
    Serial.print(":");
    Serial.print(MQTT_PORT);
    Serial.print(" ... ");

    bool conectado = mqttClient.connect(
      DEVICE_ID,
      MQTT_USER,
      MQTT_PASSWORD
    );

    if (conectado) {
      Serial.println("OK");

      StaticJsonDocument<192> doc;
      doc["device_id"] = DEVICE_ID;
      doc["modulo"] = "videovigilancia";
      doc["status"] = "online";
      doc["camara"] = camaraDisponible ? "ok" : "error";
      doc["sonido"] = "ok";

      char payload[192];
      serializeJson(doc, payload);

      mqttClient.publish(TOPIC_STATUS, payload, true);
    } else {
      Serial.print("ERROR rc=");
      Serial.print(mqttClient.state());
      Serial.println(" | Reintentando en 3 segundos...");
      delay(3000);
    }
  }
}

// ============================================================
// PUBLICAR SONIDO
// ============================================================

void publicarSonido() {
  bool ruido = digitalRead(SOUND_DO_PIN) == HIGH;

  StaticJsonDocument<192> doc;

  doc["device_id"] = DEVICE_ID;
  doc["modulo"] = "videovigilancia";
  doc["sensor"] = "KY-037";
  doc["tipo"] = "digital";
  doc["ruido"] = ruido;
  doc["value"] = ruido ? 1 : 0;
  doc["estado"] = ruido ? "detectado" : "normal";
  doc["unit"] = "digital";

  char payload[192];
  serializeJson(doc, payload);

  bool enviado = mqttClient.publish(TOPIC_SONIDO, payload);

  Serial.print("[KY-037] ");
  Serial.print(ruido ? "RUIDO detectado" : "silencio");
  Serial.print(" | MQTT: ");
  Serial.println(enviado ? "OK" : "ERROR");
}

// ============================================================
// PUBLICAR IMAGEN
// ============================================================

void publicarImagen() {
  if (!camaraDisponible) {
    Serial.println("[CAMARA] No disponible. No se envía imagen.");
    return;
  }

  camera_fb_t* fb = esp_camera_fb_get();

  if (!fb) {
    Serial.println("[CAMARA] Error al capturar imagen.");
    return;
  }

  Serial.print("[CAMARA] Imagen capturada: ");
  Serial.print(fb->width);
  Serial.print("x");
  Serial.print(fb->height);
  Serial.print(" | ");
  Serial.print(fb->len);
  Serial.println(" bytes");

  if (fb->len > MQTT_BUFFER_SIZE) {
    Serial.println("[CAMARA] Imagen demasiado grande. No se envía.");
    esp_camera_fb_return(fb);
    return;
  }

  StaticJsonDocument<256> info;

  info["device_id"] = DEVICE_ID;
  info["modulo"] = "videovigilancia";
  info["formato"] = "jpg";
  info["width"] = fb->width;
  info["height"] = fb->height;
  info["bytes"] = fb->len;
  info["estado"] = "ok";

  char payloadInfo[256];
  serializeJson(info, payloadInfo);

  mqttClient.publish(TOPIC_IMAGEN_INFO, payloadInfo);

  bool enviado = mqttClient.publish(
    TOPIC_IMAGEN,
    fb->buf,
    fb->len
  );

  Serial.print("[MQTT] Imagen enviada: ");
  Serial.println(enviado ? "OK" : "ERROR");

  esp_camera_fb_return(fb);
}

// ============================================================
// SETUP
// ============================================================

void setup() {
  Serial.begin(115200);
  delay(1000);

  pinMode(SOUND_DO_PIN, INPUT);

  Serial.println();
  Serial.println("======================================");
  Serial.println(" LIMA SMART CORE CITY - VIDEOVIGILANCIA");
  Serial.println(" ESP32-CAM + KY-037 + MQTT");
  Serial.println(" Imagen cada 10 segundos");
  Serial.println("======================================");

  WiFi.mode(WIFI_STA);

  conectarWiFiManager();

  mqttClient.setServer(MQTT_BROKER, MQTT_PORT);
  mqttClient.setBufferSize(MQTT_BUFFER_SIZE);

  camaraDisponible = inicializarCamara();

  conectarMQTT();

  Serial.println();
  Serial.println("[SISTEMA] Módulo de videovigilancia listo.");
}

// ============================================================
// LOOP
// ============================================================

void loop() {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[WiFi] Conexión perdida. Reiniciando...");
    delay(2000);
    ESP.restart();
  }

  if (!mqttClient.connected()) {
    conectarMQTT();
  }

  mqttClient.loop();

  unsigned long ahora = millis();

  // Enviar sonido cada 1 segundo
  if (ahora - ultimoEnvioSonido >= INTERVALO_SONIDO) {
    ultimoEnvioSonido = ahora;
    publicarSonido();
  }

  // Tomar y enviar foto cada 10 segundos
  if (ahora - ultimoEnvioImagen >= INTERVALO_IMAGEN) {
    ultimoEnvioImagen = ahora;
    publicarImagen();
  }
}