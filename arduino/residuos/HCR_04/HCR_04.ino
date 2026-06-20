/*
  ============================================================
  LIMA SMART CORE CITY — Módulo Residuos
  WiFiManager + MQTT + Reset por botón + 3 HC-SR04

  Pines usados:
    HC-SR04 #1  Trig GPIO5  · Echo GPIO18
    HC-SR04 #2  Trig GPIO17 · Echo GPIO16
    HC-SR04 #3  Trig GPIO4  · Echo GPIO19
    Botón reset GPIO23 a GND

  FUNCIONAMIENTO:
    - Primera vez: abre automáticamente la red LSCC_RESIDUOS_SETUP.
    - Uso normal: se conecta con WiFi/MQTT guardados.
    - Cambio de red/broker: mantener botón GPIO23 presionado 5 segundos.
  ============================================================
*/

#include <WiFi.h>
#include <WiFiManager.h>
#include <Preferences.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>

// ============================================================
// CONFIGURACIÓN GENERAL
// ============================================================

const char* DEVICE_ID = "ESP32_RESIDUOS_01";
const char* TOPIC_RESIDUOS = "lscc/residuos/nivel";

// Portal de configuración WiFiManager
const char* AP_NAME = "LSCC_RESIDUOS_SETUP";
const char* AP_PASS = "lscc12345";

// Botón para borrar configuración
#define RESET_BUTTON_PIN 23
const unsigned long RESET_HOLD_TIME = 5000;

// Cantidad de sensores usados
#define N_SENS 3

// Pines HC-SR04
const int trigPins[N_SENS] = {5, 17, 4};
const int echoPins[N_SENS] = {18, 16, 19};

// Altura del tacho en cm
const float ALTURA_TACHO_CM = 30.0;

// Tiempo entre envíos MQTT
const unsigned long INTERVALO_ENVIO = 5000;

// ============================================================
// OBJETOS GLOBALES
// ============================================================

Preferences preferences;
WiFiClient espClient;
PubSubClient client(espClient);

String mqttBroker = "";
String mqttPort = "1883";
String mqttUser = "";
String mqttPassword = "";

// ============================================================
// BORRAR CONFIGURACIÓN
// ============================================================

void borrarConfiguracion() {
  Serial.println();
  Serial.println("====================================");
  Serial.println("[RESET] Borrando configuración WiFi y MQTT...");
  Serial.println("====================================");

  preferences.begin("lscc_residuos", false);
  preferences.clear();
  preferences.end();

  WiFiManager wm;
  wm.resetSettings();

  delay(1000);

  Serial.println("[RESET] Configuración borrada.");
  Serial.println("[RESET] Reiniciando ESP32...");
  ESP.restart();
}

// ============================================================
// VERIFICAR BOTÓN RESET
// ============================================================

void verificarBotonReset() {
  static bool botonEnProceso = false;

  if (digitalRead(RESET_BUTTON_PIN) == LOW && !botonEnProceso) {
    botonEnProceso = true;

    unsigned long tiempoInicio = millis();

    while (digitalRead(RESET_BUTTON_PIN) == LOW) {
      if (millis() - tiempoInicio >= RESET_HOLD_TIME) {
        borrarConfiguracion();
      }

      delay(100);
    }

    botonEnProceso = false;
  }
}

// ============================================================
// CARGAR CONFIGURACIÓN MQTT
// ============================================================

void cargarConfiguracionMQTT() {
  preferences.begin("lscc_residuos", true);

  mqttBroker = preferences.getString("broker", "");
  mqttPort = preferences.getString("port", "1883");
  mqttUser = preferences.getString("user", "");
  mqttPassword = preferences.getString("pass", "");

  preferences.end();

  Serial.println();
  Serial.println("========== CONFIGURACIÓN MQTT ==========");

  if (mqttBroker.length() > 0) {
    Serial.print("[MQTT] Broker guardado: ");
    Serial.println(mqttBroker);
  } else {
    Serial.println("[MQTT] No hay broker guardado todavía.");
  }

  Serial.print("[MQTT] Puerto: ");
  Serial.println(mqttPort);

  if (mqttUser.length() > 0) {
    Serial.print("[MQTT] Usuario: ");
    Serial.println(mqttUser);
  } else {
    Serial.println("[MQTT] Sin usuario guardado.");
  }

  Serial.println("========================================");
}

// ============================================================
// GUARDAR CONFIGURACIÓN MQTT
// ============================================================

void guardarConfiguracionMQTT(String broker, String port, String user, String pass) {
  preferences.begin("lscc_residuos", false);

  preferences.putString("broker", broker);
  preferences.putString("port", port);
  preferences.putString("user", user);
  preferences.putString("pass", pass);

  preferences.end();

  mqttBroker = broker;
  mqttPort = port;
  mqttUser = user;
  mqttPassword = pass;

  Serial.println("[CONFIG] Configuración MQTT guardada correctamente.");
}

// ============================================================
// CONFIGURAR WIFI Y MQTT CON WIFIMANAGER
// ============================================================

void configurarWiFiYMqtt() {
  cargarConfiguracionMQTT();

  WiFiManager wm;

  WiFiManagerParameter customBroker(
    "broker",
    "MQTT Broker IP",
    mqttBroker.c_str(),
    40
  );

  WiFiManagerParameter customPort(
    "port",
    "MQTT Port",
    mqttPort.c_str(),
    6
  );

  WiFiManagerParameter customUser(
    "user",
    "MQTT User",
    mqttUser.c_str(),
    30
  );

  WiFiManagerParameter customPass(
    "pass",
    "MQTT Password",
    mqttPassword.c_str(),
    30
  );

  wm.addParameter(&customBroker);
  wm.addParameter(&customPort);
  wm.addParameter(&customUser);
  wm.addParameter(&customPass);

  wm.setConfigPortalTimeout(180);

  Serial.println();
  Serial.println("====================================");
  Serial.println("[WiFiManager] Buscando WiFi guardado...");
  Serial.println("[WiFiManager] Si no existe, abrirá portal.");
  Serial.println("====================================");

  bool conectado = wm.autoConnect(AP_NAME, AP_PASS);

  if (!conectado) {
    Serial.println("[WiFiManager] No se pudo conectar.");
    Serial.println("[WiFiManager] Reiniciando para intentar otra vez...");
    delay(2000);
    ESP.restart();
  }

  Serial.println();
  Serial.println("[WiFi] Conectado correctamente");
  Serial.print("[WiFi] SSID: ");
  Serial.println(WiFi.SSID());
  Serial.print("[WiFi] IP del ESP32: ");
  Serial.println(WiFi.localIP());

  String nuevoBroker = customBroker.getValue();
  String nuevoPort = customPort.getValue();
  String nuevoUser = customUser.getValue();
  String nuevoPass = customPass.getValue();

  if (nuevoBroker.length() == 0) {
    Serial.println("[ERROR] No se ingresó broker MQTT.");
    Serial.println("[ERROR] Debes configurar la IP de la laptop donde corre Mosquitto.");
    Serial.println("[ERROR] Reiniciando...");
    delay(3000);
    ESP.restart();
  }

  if (nuevoPort.length() == 0) {
    nuevoPort = "1883";
  }

  guardarConfiguracionMQTT(nuevoBroker, nuevoPort, nuevoUser, nuevoPass);
}

// ============================================================
// CONECTAR MQTT
// ============================================================

void conectarMQTT() {
  int puerto = mqttPort.toInt();

  if (puerto <= 0) {
    puerto = 1883;
  }

  client.setServer(mqttBroker.c_str(), puerto);

  while (!client.connected()) {
    verificarBotonReset();

    Serial.print("[MQTT] Conectando a ");
    Serial.print(mqttBroker);
    Serial.print(":");
    Serial.print(puerto);
    Serial.print(" ... ");

    bool conectadoMQTT = false;

    if (mqttUser.length() > 0) {
      conectadoMQTT = client.connect(
        DEVICE_ID,
        mqttUser.c_str(),
        mqttPassword.c_str()
      );
    } else {
      conectadoMQTT = client.connect(DEVICE_ID);
    }

    if (conectadoMQTT) {
      Serial.println("OK");
    } else {
      Serial.print("ERROR, rc=");
      Serial.print(client.state());
      Serial.println(" | Reintentando en 3 segundos...");
      delay(3000);
    }
  }
}

// ============================================================
// MEDIR DISTANCIA HC-SR04
// ============================================================

float medirDistanciaCM(int trigPin, int echoPin) {
  digitalWrite(trigPin, LOW);
  delayMicroseconds(2);

  digitalWrite(trigPin, HIGH);
  delayMicroseconds(10);
  digitalWrite(trigPin, LOW);

  unsigned long duracion = pulseIn(echoPin, HIGH, 25000UL);

  if (duracion == 0) {
    return -1.0;
  }

  float distancia = duracion * 0.0343 / 2.0;
  return distancia;
}

// ============================================================
// CALCULAR PORCENTAJE DE LLENADO
// ============================================================

int calcularPorcentajeLlenado(float distancia) {
  if (distancia < 0) {
    return 0;
  }

  if (distancia > ALTURA_TACHO_CM) {
    distancia = ALTURA_TACHO_CM;
  }

  if (distancia < 0) {
    distancia = 0;
  }

  int porcentaje = (int)(((ALTURA_TACHO_CM - distancia) / ALTURA_TACHO_CM) * 100.0);

  if (porcentaje < 0) porcentaje = 0;
  if (porcentaje > 100) porcentaje = 100;

  return porcentaje;
}

// ============================================================
// CLASIFICAR NIVEL
// ============================================================

String clasificarNivel(int porcentaje) {
  if (porcentaje >= 80) {
    return "alto";
  } else if (porcentaje >= 50) {
    return "medio";
  } else {
    return "bajo";
  }
}

// ============================================================
// PUBLICAR SENSOR
// ============================================================

void publicarSensor(int numSensor, float distancia) {
  int porcentaje = calcularPorcentajeLlenado(distancia);
  String nivel = clasificarNivel(porcentaje);

  StaticJsonDocument<256> doc;

  doc["device_id"] = DEVICE_ID;
  doc["modulo"] = "residuos";
  doc["sensor"] = "HC-SR04";
  doc["sensor_id"] = numSensor;
  doc["distancia_cm"] = distancia >= 0 ? distancia : -1;
  doc["porcentaje_llenado"] = porcentaje;
  doc["nivel"] = nivel;
  doc["estado"] = distancia >= 0 ? "ok" : "error";
  doc["unit"] = "cm";

  char payload[256];
  serializeJson(doc, payload);

  bool enviado = client.publish(TOPIC_RESIDUOS, payload);

  Serial.print("[HC-SR04 ");
  Serial.print(numSensor);
  Serial.print("] Distancia: ");

  if (distancia < 0) {
    Serial.print("sin eco");
  } else {
    Serial.print(distancia);
    Serial.print(" cm");
  }

  Serial.print(" | Llenado: ");
  Serial.print(porcentaje);
  Serial.print("% | Nivel: ");
  Serial.print(nivel);
  Serial.print(" | MQTT: ");
  Serial.println(enviado ? "OK" : "ERROR");

  Serial.print("[MQTT] Tópico: ");
  Serial.println(TOPIC_RESIDUOS);

  Serial.print("[MQTT] Payload: ");
  Serial.println(payload);
}

// ============================================================
// CONFIGURAR PINES
// ============================================================

void configurarPines() {
  pinMode(RESET_BUTTON_PIN, INPUT_PULLUP);

  for (int i = 0; i < N_SENS; i++) {
    pinMode(trigPins[i], OUTPUT);
    pinMode(echoPins[i], INPUT);
    digitalWrite(trigPins[i], LOW);
  }
}

// ============================================================
// SETUP
// ============================================================

void setup() {
  Serial.begin(115200);
  delay(1000);

  configurarPines();

  Serial.println();
  Serial.println("====================================");
  Serial.println(" LIMA SMART CORE CITY - RESIDUOS");
  Serial.println(" ESP32 + 3 HC-SR04 + WiFiManager");
  Serial.println(" MQTT + Reset por botón");
  Serial.println("====================================");

  WiFi.mode(WIFI_STA);

  configurarWiFiYMqtt();

  conectarMQTT();

  Serial.println();
  Serial.println("[SISTEMA] Módulo de residuos listo.");
}

// ============================================================
// LOOP
// ============================================================

void loop() {
  verificarBotonReset();

  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[WiFi] Desconectado. Reintentando...");
    WiFi.reconnect();

    unsigned long inicio = millis();

    while (WiFi.status() != WL_CONNECTED && millis() - inicio < 10000) {
      verificarBotonReset();
      delay(500);
      Serial.print(".");
    }

    Serial.println();

    if (WiFi.status() != WL_CONNECTED) {
      Serial.println("[WiFi] No se pudo reconectar. Reiniciando...");
      delay(2000);
      ESP.restart();
    }

    Serial.println("[WiFi] Reconectado.");
  }

  if (!client.connected()) {
    conectarMQTT();
  }

  client.loop();

  for (int i = 0; i < N_SENS; i++) {
    float distancia = medirDistanciaCM(trigPins[i], echoPins[i]);
    publicarSensor(i + 1, distancia);
    delay(100);
  }

  Serial.println("------------------------------------------");
  delay(INTERVALO_ENVIO);
}