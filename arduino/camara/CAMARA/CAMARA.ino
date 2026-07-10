/*
  ============================================================
  LIMA SMART CORE CITY — Módulo Videovigilancia
  ESP32-CAM AI Thinker + WiFiManager + MJPEG Stream en tiempo real

  FUNCIONES:
    - Conecta WiFi y MQTT mediante portal WiFiManager.
    - Publica estado (online / IP / stream_url) por MQTT cada 30 s.
    - Sirve stream MJPEG en tiempo real en http://<ip>/stream
      (accesible desde el navegador del dashboard directamente).

  RESOLUCIÓN:
    - Con PSRAM : VGA  640x480 | calidad 10 | 2 buffers | ~15 FPS
    - Sin PSRAM : CIF  400x296 | calidad 12 | 1 buffer  | ~15 FPS

  PLACA: AI Thinker ESP32-CAM
  ============================================================
*/

#include <WiFi.h>
#include <ESPmDNS.h>
#include <WiFiManager.h>
#include <Preferences.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include "esp_camera.h"
#include "esp_http_server.h"
#include "secrets.h"

// ============================================================
// CONFIGURACIÓN GENERAL
// ============================================================
const char* DEVICE_ID         = "ESP32_CAM_01";
const char* FIRMWARE_VERSION  = "2.0.0";
const char* SCHEMA_VERSION    = "1.0";

const char* AP_NAME = "LSCC_VIGILANCIA_SETUP";
const char* AP_PASS = LSCC_CONFIG_AP_PASSWORD;

const int   MQTT_PORT = 1883;
const int   MQTT_MAX_FAILED_ATTEMPTS = 5;
char MQTT_BROKER[40]  = LSCC_MQTT_BROKER;
char MQTT_USER[30]    = LSCC_MQTT_USER;
char MQTT_PASSWORD[30]= LSCC_MQTT_PASSWORD;

const char* TOPIC_STATUS = "lscc/sistema/status";

// Heartbeat MQTT cada 30 s (el stream corre independiente en HTTP)
const unsigned long INTERVALO_STATUS = 30000;

// Delay entre frames: 66 ms ≈ 15 FPS — balance calidad/calor
const int FRAME_DELAY_MS = 66;

// ============================================================
// PINES CÁMARA — AI Thinker ESP32-CAM
// ============================================================
#define PWDN_GPIO_NUM   32
#define RESET_GPIO_NUM  -1
#define XCLK_GPIO_NUM    0
#define SIOD_GPIO_NUM   26
#define SIOC_GPIO_NUM   27
#define Y9_GPIO_NUM     35
#define Y8_GPIO_NUM     34
#define Y7_GPIO_NUM     39
#define Y6_GPIO_NUM     36
#define Y5_GPIO_NUM     21
#define Y4_GPIO_NUM     19
#define Y3_GPIO_NUM     18
#define Y2_GPIO_NUM      5
#define VSYNC_GPIO_NUM  25
#define HREF_GPIO_NUM   23
#define PCLK_GPIO_NUM   22

// ============================================================
// OBJETOS
// ============================================================
WiFiClient   espClient;
PubSubClient mqttClient(espClient);
WiFiManager  wm;
Preferences  prefs;

bool camaraDisponible = false;
unsigned long ultimoStatus = 0;
httpd_handle_t stream_httpd = NULL;

// ============================================================
// MJPEG HTTP STREAM
// ============================================================
#define STREAM_BOUNDARY     "mjpegstream"
static const char* STREAM_CT  = "multipart/x-mixed-replace;boundary=" STREAM_BOUNDARY;
static const char* STREAM_SEP = "\r\n--" STREAM_BOUNDARY "\r\n";
static const char* PART_FMT   = "Content-Type: image/jpeg\r\nContent-Length: %u\r\n\r\n";

esp_err_t stream_handler(httpd_req_t* req) {
    camera_fb_t* fb = nullptr;
    char part_hdr[64];

    httpd_resp_set_type(req, STREAM_CT);
    httpd_resp_set_hdr(req, "Access-Control-Allow-Origin", "*");
    httpd_resp_set_hdr(req, "Cache-Control", "no-cache, no-store");

    Serial.println("[STREAM] Cliente conectado");

    while (true) {
        fb = esp_camera_fb_get();
        if (!fb) {
            Serial.println("[STREAM] Error al capturar frame");
            delay(100);
            continue;
        }

        esp_err_t res = httpd_resp_send_chunk(req, STREAM_SEP, strlen(STREAM_SEP));

        if (res == ESP_OK) {
            size_t hlen = snprintf(part_hdr, sizeof(part_hdr), PART_FMT, fb->len);
            res = httpd_resp_send_chunk(req, part_hdr, hlen);
        }

        if (res == ESP_OK) {
            res = httpd_resp_send_chunk(req, (const char*)fb->buf, fb->len);
        }

        esp_camera_fb_return(fb);

        if (res != ESP_OK) {
            Serial.println("[STREAM] Cliente desconectado");
            break;
        }

        delay(FRAME_DELAY_MS);
    }

    return ESP_OK;
}

void iniciarStreamServer() {
    httpd_config_t config = HTTPD_DEFAULT_CONFIG();
    config.server_port    = 80;
    config.max_uri_handlers = 4;

    httpd_uri_t stream_uri = {
        .uri      = "/stream",
        .method   = HTTP_GET,
        .handler  = stream_handler,
        .user_ctx = nullptr
    };

    if (httpd_start(&stream_httpd, &config) == ESP_OK) {
        httpd_register_uri_handler(stream_httpd, &stream_uri);
        Serial.printf("[HTTP] Stream en http://%s/stream\n",
                      WiFi.localIP().toString().c_str());
    } else {
        Serial.println("[HTTP] Error al iniciar servidor");
    }
}

// ============================================================
// CÁMARA
// ============================================================
bool inicializarCamara() {
    camera_config_t config;
    config.ledc_channel  = LEDC_CHANNEL_0;
    config.ledc_timer    = LEDC_TIMER_0;
    config.pin_d0        = Y2_GPIO_NUM;
    config.pin_d1        = Y3_GPIO_NUM;
    config.pin_d2        = Y4_GPIO_NUM;
    config.pin_d3        = Y5_GPIO_NUM;
    config.pin_d4        = Y6_GPIO_NUM;
    config.pin_d5        = Y7_GPIO_NUM;
    config.pin_d6        = Y8_GPIO_NUM;
    config.pin_d7        = Y9_GPIO_NUM;
    config.pin_xclk      = XCLK_GPIO_NUM;
    config.pin_pclk      = PCLK_GPIO_NUM;
    config.pin_vsync     = VSYNC_GPIO_NUM;
    config.pin_href      = HREF_GPIO_NUM;
    config.pin_sccb_sda  = SIOD_GPIO_NUM;
    config.pin_sccb_scl  = SIOC_GPIO_NUM;
    config.pin_pwdn      = PWDN_GPIO_NUM;
    config.pin_reset     = RESET_GPIO_NUM;
    config.xclk_freq_hz  = 20000000;
    config.pixel_format  = PIXFORMAT_JPEG;

    if (psramFound()) {
        config.frame_size   = FRAMESIZE_VGA;   // 640×480
        config.jpeg_quality = 10;
        config.fb_count     = 2;
        config.fb_location  = CAMERA_FB_IN_PSRAM;
        Serial.println("[CAM] PSRAM OK → VGA 640x480 / calidad 10 / 2 buffers");
    } else {
        config.frame_size   = FRAMESIZE_CIF;   // 400×296
        config.jpeg_quality = 12;
        config.fb_count     = 1;
        config.fb_location  = CAMERA_FB_IN_DRAM;
        Serial.println("[CAM] Sin PSRAM → CIF 400x296 / calidad 12 / 1 buffer");
    }

    if (esp_camera_init(&config) != ESP_OK) {
        Serial.println("[CAM] Error al inicializar cámara");
        return false;
    }

    Serial.println("[CAM] Cámara inicializada correctamente");
    return true;
}

// ============================================================
// MQTT
// ============================================================
void cargarConfigMQTT() {
    prefs.begin("lscc_vig", true);
    String b = prefs.getString("broker", MQTT_BROKER);
    String u = prefs.getString("user",   MQTT_USER);
    String p = prefs.getString("pass",   MQTT_PASSWORD);
    b.toCharArray(MQTT_BROKER,   sizeof(MQTT_BROKER));
    u.toCharArray(MQTT_USER,     sizeof(MQTT_USER));
    p.toCharArray(MQTT_PASSWORD, sizeof(MQTT_PASSWORD));
    prefs.end();
}

void guardarConfigMQTT() {
    prefs.begin("lscc_vig", false);
    prefs.putString("broker", MQTT_BROKER);
    prefs.putString("user",   MQTT_USER);
    prefs.putString("pass",   MQTT_PASSWORD);
    prefs.end();
}

void abrirPortalConfigMQTT(const char* motivo) {
    Serial.println();
    Serial.print("[WiFiManager] Abriendo portal de configuracion: ");
    Serial.println(motivo);

    WiFiManager portal;
    WiFiManagerParameter p_broker("broker", "MQTT Broker IP/Host", MQTT_BROKER, 40);
    WiFiManagerParameter p_user("user", "MQTT User", MQTT_USER, 30);
    WiFiManagerParameter p_pass("pass", "MQTT Password", MQTT_PASSWORD, 30);

    portal.addParameter(&p_broker);
    portal.addParameter(&p_user);
    portal.addParameter(&p_pass);
    portal.setConfigPortalTimeout(0);

    if (!portal.startConfigPortal(AP_NAME, AP_PASS)) {
        Serial.println("[WiFiManager] Portal cerrado sin configurar. Reiniciando...");
        delay(1000);
        ESP.restart();
    }

    strncpy(MQTT_BROKER,   p_broker.getValue(), sizeof(MQTT_BROKER)   - 1);
    strncpy(MQTT_USER,     p_user.getValue(),   sizeof(MQTT_USER)     - 1);
    strncpy(MQTT_PASSWORD, p_pass.getValue(),   sizeof(MQTT_PASSWORD) - 1);
    MQTT_BROKER[sizeof(MQTT_BROKER) - 1] = '\0';
    MQTT_USER[sizeof(MQTT_USER) - 1] = '\0';
    MQTT_PASSWORD[sizeof(MQTT_PASSWORD) - 1] = '\0';

    guardarConfigMQTT();
    mqttClient.setServer(MQTT_BROKER, MQTT_PORT);

    Serial.print("[MQTT] Nuevo broker guardado: ");
    Serial.println(MQTT_BROKER);
}

void publicarStatus() {
    String ip  = WiFi.localIP().toString();
    String url = "http://" + ip + "/stream";

    StaticJsonDocument<384> doc;
    doc["device_id"]        = DEVICE_ID;
    doc["modulo"]           = "videovigilancia";
    doc["status"]           = "online";
    doc["camara"]           = camaraDisponible ? "ok" : "error";
    doc["stream_url"]       = url;
    doc["schema_version"]   = SCHEMA_VERSION;
    doc["firmware_version"] = FIRMWARE_VERSION;
    doc["uptime_ms"]        = millis();
    doc["rssi_dbm"]         = WiFi.RSSI();
    doc["ip"]               = ip;

    char buf[384];
    serializeJson(doc, buf);
    mqttClient.publish(TOPIC_STATUS, buf, true);
    Serial.printf("[MQTT] Status publicado | %s\n", url.c_str());
}

void conectarMQTT() {
    int intentosFallidos = 0;

    StaticJsonDocument<160> willDoc;
    willDoc["device_id"] = DEVICE_ID;
    willDoc["modulo"]    = "videovigilancia";
    willDoc["status"]    = "offline";
    char willPayload[160];
    serializeJson(willDoc, willPayload);

    while (!mqttClient.connected()) {
        if (strlen(MQTT_BROKER) == 0) {
            abrirPortalConfigMQTT("no hay broker MQTT configurado");
            intentosFallidos = 0;
        }

        Serial.printf("[MQTT] Conectando a %s:%d ... ", MQTT_BROKER, MQTT_PORT);
        const char* mqttUser = strlen(MQTT_USER) > 0 ? MQTT_USER : nullptr;
        const char* mqttPass = strlen(MQTT_USER) > 0 ? MQTT_PASSWORD : nullptr;

        if (mqttClient.connect(DEVICE_ID, mqttUser, mqttPass,
                               TOPIC_STATUS, 1, true, willPayload)) {
            Serial.println("OK");
            publicarStatus();
        } else {
            intentosFallidos++;
            Serial.printf("Fallo rc=%d | Reintentando en 5 s\n", mqttClient.state());

            if (intentosFallidos >= MQTT_MAX_FAILED_ATTEMPTS) {
                abrirPortalConfigMQTT("no se pudo conectar al broker MQTT");
                intentosFallidos = 0;
            }

            delay(5000);
        }
    }
}

// ============================================================
// WIFI MANAGER
// ============================================================
void conectarWiFiManager() {
    cargarConfigMQTT();

    WiFiManagerParameter p_broker("broker", "MQTT Broker IP", MQTT_BROKER, 40);
    WiFiManagerParameter p_user("user",     "MQTT User",      MQTT_USER,   30);
    WiFiManagerParameter p_pass("pass",     "MQTT Password",  MQTT_PASSWORD, 30);

    wm.addParameter(&p_broker);
    wm.addParameter(&p_user);
    wm.addParameter(&p_pass);
    wm.setConfigPortalTimeout(0);

    Serial.println("[WiFiManager] Buscando WiFi guardado...");

    if (!wm.autoConnect(AP_NAME, AP_PASS)) {
        Serial.println("[WiFi] No se pudo conectar. Reiniciando...");
        delay(3000);
        ESP.restart();
    }

    strncpy(MQTT_BROKER,   p_broker.getValue(), sizeof(MQTT_BROKER)   - 1);
    strncpy(MQTT_USER,     p_user.getValue(),   sizeof(MQTT_USER)     - 1);
    strncpy(MQTT_PASSWORD, p_pass.getValue(),   sizeof(MQTT_PASSWORD) - 1);
    MQTT_BROKER[sizeof(MQTT_BROKER) - 1] = '\0';
    MQTT_USER[sizeof(MQTT_USER) - 1] = '\0';
    MQTT_PASSWORD[sizeof(MQTT_PASSWORD) - 1] = '\0';
    guardarConfigMQTT();

    Serial.printf("[WiFi] Conectado | IP: %s\n", WiFi.localIP().toString().c_str());
}

// ============================================================
// SETUP
// ============================================================
void setup() {
    Serial.begin(115200);
    delay(1000);

    Serial.println("======================================");
    Serial.println(" LIMA SMART — Videovigilancia v2.0");
    Serial.println(" ESP32-CAM + MJPEG Stream");
    Serial.println("======================================");

    WiFi.mode(WIFI_STA);
    conectarWiFiManager();
    MDNS.begin("lscc-cam");

    mqttClient.setServer(MQTT_BROKER, MQTT_PORT);

    camaraDisponible = inicializarCamara();

    if (camaraDisponible) {
        iniciarStreamServer();
    } else {
        Serial.println("[AVISO] Cámara no disponible — stream HTTP no iniciado");
    }

    conectarMQTT();

    Serial.println("[SISTEMA] Módulo de videovigilancia listo.");
}

// ============================================================
// LOOP — solo mantiene WiFi + MQTT + heartbeat
// (el stream corre en la tarea del servidor HTTP de ESP-IDF)
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

    if (millis() - ultimoStatus >= INTERVALO_STATUS) {
        ultimoStatus = millis();
        publicarStatus();
    }

    delay(10);
}
