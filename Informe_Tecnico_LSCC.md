

**UNIVERSIDAD NACIONAL MAYOR DE SAN MARCOS**

Facultad de Ingeniería de Sistemas e Informática

**INFORME TÉCNICO: LIMA SMART CORE CITY (LSCC)**

*Plataforma IoT de Monitoreo Urbano — Arquitectura, Tecnologías y Protocolos*

*Alineado con: Recomendación UIT-T Y.2060 (06/2012) — Internet de las Cosas*

Curso: Internet de las Cosas  
Ing. Armando Fermín Pérez

Lima, Perú — 2025

---

# **1. Introducción**

El presente informe describe de forma técnica y detallada el sistema **Lima Smart Core City (LSCC)**, una plataforma IoT académica de monitoreo urbano desarrollada e implementada como proyecto de integración del curso de Internet de las Cosas. El sistema recoge datos en tiempo real de cuatro módulos físicos de sensado, los transmite mediante el protocolo MQTT, los procesa en un servidor web Flask, los persiste en una base de datos SQLite y los presenta a usuarios autenticados a través de un dashboard interactivo.

La arquitectura del proyecto sigue el modelo de referencia de cuatro capas definido en la Recomendación UIT-T Y.2060 (Unión Internacional de Telecomunicaciones, 2012), con las capacidades transversales de gestión y seguridad aplicadas a cada nivel. Adicionalmente, el sistema incluye un pipeline de datos en la nube mediante Amazon S3, AWS Athena y Power BI, configurando así un esquema tipo medallón (Bronze, Silver, Gold) para análisis histórico.

La versión documentada en este informe es la `0.2.0-consolidacion-fase1`. El punto de retorno estable del código fuente corresponde al tag Git `v0.1.0-pre-consolidacion` (commit `54ea5af`).

---

# **2. Visión General del Sistema**

LSCC integra cuatro módulos físicos de sensado urbano, cada uno implementado sobre un microcontrolador ESP32, con un servidor central que centraliza la recepción, persistencia y visualización de los datos. Los módulos son:

| Módulo | Nodo | Sensores | Función |
| :---- | :---- | :---- | :---- |
| Ambiental | ESP32\_AIRE\_01 | DHT22, BMP280, MQ-2 | Temperatura, humedad, presión atmosférica y concentración de gas |
| Residuos | ESP32\_RESIDUOS\_01 | 3 × HC-SR04 | Nivel de llenado de contenedores de basura por ultrasonido |
| Videovigilancia | ESP32\_CAM\_01 | OV2640 (cámara) | Stream de video MJPEG en tiempo real + captura de imagen |
| Sonido | ESP32\_KY037\_01 | KY-037 | Nivel de ruido ambiental por voltaje analógico |

El flujo de datos de extremo a extremo sigue la secuencia:

```
ESP32 (sensor) → Wi-Fi / IPv4 / TCP → Mosquitto MQTT Broker
    → Python paho-mqtt (hilo daemon) → estado{} (RAM) + SQLite (disco)
    → Flask API (/api/data) → Navegador Web (polling cada 2 s)
    → Visualización en dashboard + reportes ciudadanos
```

Paralelamente, un pipeline fuera de línea exporta datos desde SQLite hacia Amazon S3 en capas Bronze, Silver y Gold, con consultas sobre Athena y visualización futura en Power BI.

---

# **3. Arquitectura por Capas (UIT-T Y.2060)**

La siguiente tabla relaciona cada capa del modelo de referencia con su implementación concreta en LSCC:

| Capa UIT-T Y.2060 | Implementación LSCC | Tecnologías empleadas |
| :---- | :---- | :---- |
| **Capa de Aplicación** | Dashboard web, portal de reportes ciudadanos, Power BI | Flask (Jinja2), HTML5, CSS3, JavaScript (Fetch API, Chart.js) |
| **Capa de Apoyo a Servicios y Aplicaciones** | Ingesta MQTT, reglas de negocio, persistencia, APIs REST, S3/Athena | Python 3, Flask, paho-mqtt, SQLite 3, Amazon S3, AWS Athena |
| **Capa de Red** | Transporte de datos entre sensores y servidor | Wi-Fi 802.11 b/g/n, IPv4, TCP, MQTT 3.1.1 |
| **Capa de Dispositivo** | Nodos ESP32 con sensores físicos y firmware | ESP32 (Xtensa LX6 dual-core), Arduino Framework (ESP-IDF), C++ |

De forma transversal:

- **Capacidades de Gestión**: heartbeat MQTT, MQTT Last Will, tabla de inventario de dispositivos (`dispositivos`), versionado de firmware y de contrato de mensajes.
- **Capacidades de Seguridad**: autenticación MQTT por usuario/contraseña, control de acceso por roles (RBAC), protección CSRF, sesión única por usuario, secretos fuera del repositorio Git.

---

# **4. Capa de Dispositivo**

## **4.1. Hardware de los Nodos**

Todos los módulos de campo están basados en el microcontrolador **Espressif ESP32** (procesador Xtensa LX6 dual-core a 240 MHz, 520 KB SRAM, Wi-Fi 802.11 b/g/n integrado). Las variantes utilizadas son:

| Nodo | Placa | RAM adicional | Observación |
| :---- | :---- | :---- | :---- |
| ESP32\_AIRE\_01 | ESP32 DevKit v1 | — | Alimentación por USB o batería |
| ESP32\_RESIDUOS\_01 | ESP32 DevKit v1 | — | Botón físico GPIO23 para reset de configuración |
| ESP32\_CAM\_01 | AI Thinker ESP32-CAM | PSRAM 4 MB | Módulo con cámara OV2640 integrada |
| ESP32\_KY037\_01 | ESP32 DevKit v1 | — | Lectura analógica ADC de 12 bits |

## **4.2. Sensores y Parámetros Medidos**

### Módulo Ambiental (ESP32\_AIRE\_01)

| Sensor | Variable medida | Rango / precisión | Protocolo de interfaz | Tópico MQTT |
| :---- | :---- | :---- | :---- | :---- |
| DHT22 | Temperatura | -40 a +80 °C / ±0.5 °C | 1-Wire (single bus) | `lscc/ambiental/temperatura` |
| DHT22 | Humedad relativa | 0–100 %HR / ±2 %HR | 1-Wire (single bus) | `lscc/ambiental/humedad` |
| BMP280 | Presión atmosférica | 300–1100 hPa / ±1 hPa | I²C | `lscc/ambiental/presion` |
| MQ-2 | Gas (humo / GLP / CO) | 300–10 000 ppm (indicativo) | ADC analógico (AO) | `lscc/ambiental/gas` |

El ESP32\_AIRE\_01 publica las cuatro variables de forma independiente cada **5 segundos**. El MQ-2 requiere un periodo de calentamiento de aproximadamente 2 minutos tras el encendido; durante ese tiempo el firmware reporta `"estado": "calentando"`.

### Módulo Residuos (ESP32\_RESIDUOS\_01)

| Sensor | Cantidad física | Pins (Trig / Echo) | Variable medida | Tópico MQTT |
| :---- | :---- | :---- | :---- | :---- |
| HC-SR04 #1 | Nivel contenedor 1 | GPIO5 / GPIO18 | Distancia en cm → % llenado | `lscc/residuos/nivel` |
| HC-SR04 #2 | Nivel contenedor 2 | GPIO17 / GPIO16 | Distancia en cm → % llenado | `lscc/residuos/nivel` |
| HC-SR04 #3 | Nivel contenedor 3 | GPIO4 / GPIO19 | Distancia en cm → % llenado | `lscc/residuos/nivel` |

El firmware define `N_SENS = 3`. La altura del tacho de referencia es 30 cm. El porcentaje de llenado se calcula como `((30 − distancia_cm) / 30) × 100`. Una lectura de `distancia_cm = −1` indica ausencia de eco (sensor sin respuesta). Se publica un mensaje por sensor en cada ciclo cada **5 segundos**; el campo `sensor_id` identifica cada contenedor (1, 2 o 3).

### Módulo Videovigilancia (ESP32\_CAM\_01)

| Componente | Descripción |
| :---- | :---- |
| Cámara | OV2640 integrada en módulo AI Thinker |
| Resolución (con PSRAM) | VGA 640 × 480 px, calidad JPEG 10, 2 frame buffers |
| Resolución (sin PSRAM) | CIF 400 × 296 px, calidad JPEG 12, 1 frame buffer |
| Servidor HTTP | ESP-IDF `esp_http_server`, ruta `/stream`, puerto 80 |
| Formato de streaming | MJPEG (multipart/x-mixed-replace), tasa objetivo: 15 FPS |
| Heartbeat MQTT | Cada 30 segundos, incluye `stream_url`, `rssi_dbm`, `ip`, `uptime_ms` |
| Tópico de imagen | `lscc/vigilancia/imagen` (payload binario JPEG) |
| Tópico de metadatos | `lscc/vigilancia/imagen_meta` (JSON con dimensiones y trigger) |

### Módulo Sonido (ESP32\_KY037\_01)

| Parámetro | Valor |
| :---- | :---- |
| Sensor | KY-037 (salida analógica AO) |
| Lectura | ADC 12 bits ESP32, rango 0–4095 (0–3.3 V) |
| Tópico MQTT | `lscc/vigilancia/sonido` |
| Intervalo de publicación | Cada 3 segundos |
| Campos JSON | `value` (raw ADC), `voltage`, `porcentaje`, `nivel` (bajo/medio/alto), `evento` |

## **4.3. Firmware — Funciones Comunes**

Todos los sketches comparten las siguientes funcionalidades implementadas en C++ sobre el Arduino Framework (ESP-IDF):

**Gestión de conectividad Wi-Fi con WiFiManager:** La primera vez que se enciende el nodo (o cuando no existe configuración guardada) el ESP32 levanta un punto de acceso (`AP`) con SSID propio (`LSCC_*_SETUP`) y abre un portal web cautivo en `192.168.4.1` donde el operador ingresa las credenciales Wi-Fi y los parámetros MQTT. Esos valores se guardan en la memoria no volátil (NVS / `Preferences`) y se reutilizan en arranques siguientes.

**Configuración MQTT persistente en NVS:** Broker IP, puerto, usuario y contraseña se almacenan en la partición NVS del ESP32 usando la librería `Preferences`. Esto permite cambiar el broker sin recompilar el firmware.

**Reconexión automática:** El `loop()` de cada sketch verifica el estado de Wi-Fi y MQTT; ante una desconexión llama a `WiFi.reconnect()` o vuelve a ejecutar `conectarMQTT()`.

**MQTT Last Will (Testamento):** En cada llamada a `mqttClient.connect()` se registra un mensaje de Last Will en el tópico `lscc/sistema/status` con payload `{"device_id":"…","status":"offline"}`. Cuando el broker detecta la desconexión inesperada del nodo, entrega este mensaje automáticamente a todos los suscriptores, permitiendo al dashboard detectar la caída de forma inmediata sin esperar el timeout del servidor.

**Heartbeat de estado:** Además de los datos de sensor, cada nodo publica periódicamente un mensaje de estado en `lscc/sistema/status` con campos de diagnóstico: `status`, `firmware_version`, `uptime_ms`, `rssi_dbm`, `ip`, `schema_version`.

**Secretos fuera del código fuente:** Las credenciales (contraseña del AP de configuración, usuario y contraseña MQTT) se almacenan en un archivo `secrets.h` que no se incluye en el repositorio Git. Cada sketch incluye un `secrets.h.example` como plantilla.

---

# **5. Capa de Red**

## **5.1. Tecnología de Acceso Inalámbrico**

Los cuatro nodos ESP32 se conectan mediante **Wi-Fi 802.11 b/g/n (2.4 GHz)** a la red local del entorno de operación. No se utiliza una red dedicada; los dispositivos y el servidor comparten la misma infraestructura de red doméstica/laboral. La dirección IP del servidor Flask (broker MQTT) se configura de forma estática en el firmware de cada nodo a través del portal WiFiManager.

## **5.2. Protocolo de Transporte — MQTT 3.1.1**

El protocolo de mensajería utilizado es **MQTT versión 3.1.1** (Message Queuing Telemetry Transport), un protocolo de publicación/suscripción ligero diseñado para dispositivos con recursos limitados y redes de baja ancho de banda.

| Parámetro MQTT | Valor en LSCC |
| :---- | :---- |
| Broker | Eclipse Mosquitto 2.1.2 |
| Puerto | 1883 (texto plano) / 8883 (TLS, preparado, no activo) |
| Autenticación | Usuario + contraseña (`mosquitto_passwd`) |
| Keep-alive | 60 segundos (configurable en `.env`) |
| QoS heartbeat / Last Will | 1 (at least once) |
| QoS datos de sensor | 0 (fire and forget) |
| Retención (retain) | `true` en mensajes de estado (`lscc/sistema/status`) |
| Patrón de suscripción del dashboard | `lscc/#` (wildcard multinivel) |

### Tópicos MQTT definidos

| Tópico | Publicado por | Suscrito por | Contenido |
| :---- | :---- | :---- | :---- |
| `lscc/ambiental/temperatura` | ESP32\_AIRE\_01 | Dashboard | JSON con `value`, `device_id`, `estado` |
| `lscc/ambiental/humedad` | ESP32\_AIRE\_01 | Dashboard | JSON con `value`, `device_id`, `estado` |
| `lscc/ambiental/presion` | ESP32\_AIRE\_01 | Dashboard | JSON con `value`, `device_id`, `estado` |
| `lscc/ambiental/gas` | ESP32\_AIRE\_01 | Dashboard | JSON con `value_raw`, `voltage`, `nivel`, `estado` |
| `lscc/residuos/nivel` | ESP32\_RESIDUOS\_01 | Dashboard | JSON con `sensor_id`, `distancia_cm`, `porcentaje_llenado`, `nivel` |
| `lscc/vigilancia/sonido` | ESP32\_KY037\_01 | Dashboard | JSON con `value`, `voltage`, `porcentaje`, `nivel`, `evento` |
| `lscc/vigilancia/imagen` | ESP32\_CAM\_01 | Dashboard | Payload binario JPEG (no JSON) |
| `lscc/vigilancia/imagen_meta` | ESP32\_CAM\_01 | Dashboard | JSON con `width`, `height`, `trigger` |
| `lscc/sistema/status` | Todos los nodos | Dashboard | JSON heartbeat / Last Will. Campos: `device_id`, `modulo`, `status`, `firmware_version`, `uptime_ms`, `rssi_dbm`, `ip` |

## **5.3. Broker MQTT — Mosquitto**

**Eclipse Mosquitto 2.1.2** es el broker MQTT del proyecto. Se ejecuta como proceso independiente en la misma máquina que el servidor Flask, escuchando en `0.0.0.0:1883`. La configuración (`dashboard/mosquitto.conf`) habilita:

- Autenticación obligatoria mediante archivo de contraseñas (`mosquitto_passwd.txt`).
- Listener en todas las interfaces para permitir conexiones desde la red Wi-Fi local.
- Logging en consola en modo detallado (`-v`) durante el desarrollo.

Existe además un archivo `mosquitto-secure.conf.example` que prepara el perfil TLS/mTLS pero que no se activa hasta completar la PKI local (ver sección de pendientes).

**Consideración operativa crítica:** Solo debe existir una instancia de Mosquitto activa. El servicio predeterminado de Windows (`mosquitto.exe` como servicio del sistema) debe detenerse antes de iniciar el broker del proyecto, ya que dos brokers simultáneos en el mismo puerto producen un estado engañoso donde Flask aparece conectado a uno y los ESP32 publican en el otro.

## **5.4. Protocolo de Servicio de Nombres — mDNS**

Cada ESP32 registra un nombre en la red local mediante **mDNS** (`ESPmDNS.h`):

| Nodo | Nombre mDNS |
| :---- | :---- |
| ESP32\_AIRE\_01 | `lscc-ambiental.local` |
| ESP32\_RESIDUOS\_01 | `lscc-residuos.local` |
| ESP32\_CAM\_01 | `lscc-cam.local` |
| ESP32\_KY037\_01 | — |

Esto permite acceder al stream de la cámara por nombre (`http://lscc-cam.local/stream`) en lugar de por IP dinámica.

---

# **6. Capa de Apoyo a Servicios y Aplicaciones (Middleware)**

## **6.1. Servidor de Aplicaciones — Flask**

El servidor central está implementado en **Python 3** usando el framework **Flask (≥ 3.0)**. El archivo principal es `dashboard/app.py`. Sus responsabilidades son:

1. **Suscripción MQTT**: Un hilo daemon ejecuta `paho-mqtt` con `loop_forever()`. El callback `on_message` procesa cada mensaje según su tópico, actualiza el estado en memoria y escribe en SQLite.
2. **Estado en memoria compartida**: El diccionario global `estado{}` actúa como caché en RAM del estado actual de todos los módulos. Está protegido por un `threading.Lock()` para acceso concurrente seguro entre el hilo MQTT y el hilo de Flask.
3. **API REST**: La ruta `/api/data` devuelve el `estado{}` completo como JSON en cada consulta del frontend (polling cada 2 segundos). La ruta `/api/history` permite consultar series históricas por variable.
4. **Autenticación y sesiones**: Login con contraseña hasheada (Werkzeug), sesión única por usuario invalidada al iniciar sesión en otro dispositivo.
5. **Gestión de reportes**: CRUD de reportes ciudadanos con validación, carga de imágenes y control de estados.
6. **Carga inicial desde base de datos**: Al arrancar, el servidor consulta SQLite para cargar el último valor conocido de cada variable ambiental y el historial de los últimos 30 puntos de cada serie, de modo que el dashboard muestre datos inmediatamente sin esperar nuevos mensajes MQTT.

### Detección de conectividad por nodo

El servidor mantiene un diccionario `estado["ultima_vez_modulos"]` que registra el timestamp Unix de la última vez que se recibió un mensaje de cada `device_id`. El mecanismo sigue esta lógica:

- **Mensaje normal** → `ultima_vez_modulos[device_id] = time.time()`
- **Last Will (status: offline)** → `ultima_vez_modulos[device_id] = 0`

El frontend lee estos timestamps y aplica un timeout por nodo para determinar si está en línea o fuera de línea, sin que el servidor necesite un proceso de watchdog adicional.

### Librerías Python utilizadas

| Librería | Versión mínima | Función |
| :---- | :---- | :---- |
| Flask | ≥ 3.0 | Framework web, rutas, templates Jinja2, sesiones |
| paho-mqtt | ≥ 2.0 | Cliente MQTT, suscripción, callbacks |
| Werkzeug | ≥ 3.0 | Hashing de contraseñas, utilidades de seguridad HTTP |
| python-dotenv | ≥ 1.0 | Carga de variables de entorno desde `.env` |
| Pillow | ≥ 10.0 | Validación de contenido real de imágenes subidas |

## **6.2. Persistencia — SQLite**

La base de datos es **SQLite 3** con WAL (Write-Ahead Logging) habilitado para mejor concurrencia. El archivo `lscc.db` reside en el directorio `dashboard/`. Las conexiones se abren en modo `rw` (lectura/escritura) para evitar la creación accidental de una base vacía en caso de ruta incorrecta.

### Modelo de datos

El esquema consta de **9 tablas** con **11 índices** de rendimiento:

#### Tabla: `dispositivos`
Inventario maestro de los nodos IoT del proyecto.

| Columna | Tipo | Descripción |
| :---- | :---- | :---- |
| `device_id` | TEXT PK | Identificador único del nodo (ej. `ESP32_AIRE_01`) |
| `modulo` | TEXT | Módulo funcional: `ambiental`, `residuos`, `vigilancia`, `sistema` |
| `descripcion` | TEXT | Descripción legible del nodo |
| `activo` | INTEGER | `1` = activo, `0` = inactivo |
| `creado_en` | TEXT | Timestamp de registro |
| `ultima_vez` | TEXT | Última vez que publicó (actualizado por heartbeat) |

Solo los `device_id` registrados en esta tabla y marcados como `activo=1` son aceptados por el dashboard; cualquier otro es rechazado en `on_message`.

#### Tabla: `lecturas_ambientales`
Serie temporal de las cuatro variables del módulo ambiental.

| Columna | Tipo | Descripción |
| :---- | :---- | :---- |
| `id` | INTEGER PK | Autoincremental |
| `device_id` | TEXT FK | Referencia a `dispositivos` |
| `sensor` | TEXT | `DHT22`, `BMP280`, `MQ-2` |
| `variable` | TEXT | `temperatura`, `humedad`, `presion`, `gas` |
| `valor` | REAL | Valor principal medido |
| `valor_raw` | INTEGER | Valor ADC crudo (solo MQ-2) |
| `voltaje` | REAL | Voltaje calculado (solo MQ-2) |
| `unidad` | TEXT | `C`, `%HR`, `hPa`, `V` |
| `nivel` | TEXT | `normal`, `preventivo`, `elevado` (solo gas) |
| `estado` | TEXT | `ok`, `sin_datos`, `calentando`, `error` |
| `timestamp` | TEXT | Fecha y hora local de la lectura |

#### Tabla: `lecturas_residuos`
Nivel de llenado por contenedor.

| Columna | Tipo | Descripción |
| :---- | :---- | :---- |
| `id` | INTEGER PK | Autoincremental |
| `device_id` | TEXT FK | Referencia a `dispositivos` |
| `sensor_id` | INTEGER | Número de contenedor (1 a 4) |
| `distancia_cm` | REAL | Distancia medida por ultrasonido; `-1` = sin eco |
| `porcentaje_llenado` | INTEGER | 0–100 % |
| `nivel` | TEXT | `bajo`, `medio`, `alto`, `sin_datos` |
| `timestamp` | TEXT | Fecha y hora local |

#### Tabla: `lecturas_sonido`
Lecturas del sensor de nivel de ruido.

| Columna | Tipo | Descripción |
| :---- | :---- | :---- |
| `id` | INTEGER PK | Autoincremental |
| `device_id` | TEXT FK | Referencia a `dispositivos` |
| `valor_raw` | INTEGER | Valor ADC 12 bits (0–4095) |
| `voltaje` | REAL | Voltaje calculado (0–3.3 V) |
| `porcentaje` | INTEGER | Nivel normalizado 0–100 % |
| `nivel` | TEXT | `bajo`, `medio`, `alto` |
| `evento` | TEXT | `sonido_detectado`, `sin_sonido_relevante` |
| `timestamp` | TEXT | Fecha y hora local |

#### Tabla: `imagenes_meta`
Registro de cada imagen capturada por la cámara.

| Columna | Tipo | Descripción |
| :---- | :---- | :---- |
| `id` | INTEGER PK | Autoincremental |
| `device_id` | TEXT FK | Referencia a `dispositivos` |
| `width` | INTEGER | Ancho en píxeles |
| `height` | INTEGER | Alto en píxeles |
| `size_bytes` | INTEGER | Tamaño del archivo JPEG |
| `trigger_tipo` | TEXT | Tipo de captura (ej. `captura_imagen`) |
| `ruta_archivo` | TEXT | Ruta local del JPEG almacenado |
| `timestamp` | TEXT | Fecha y hora local |

Los archivos JPEG se almacenan en `dashboard/imagenes/`. El último frame siempre se sobreescribe en `dashboard/imagenes/ultima_imagen.jpg` para acceso rápido desde la ruta `/imagen`.

#### Tabla: `eventos_alerta`
Registro de alertas automáticas generadas por el sistema.

| Columna | Tipo | Descripción |
| :---- | :---- | :---- |
| `id` | INTEGER PK | Autoincremental |
| `device_id` | TEXT FK | Dispositivo que generó la alerta |
| `modulo` | TEXT | Módulo funcional |
| `tipo_alerta` | TEXT | `gas_elevado`, `gas_preventivo`, `contenedor_alto`, etc. |
| `descripcion` | TEXT | Descripción legible de la alerta |
| `prioridad` | TEXT | `alta`, `media`, `baja` |
| `estado` | TEXT | `activa`, `resuelta` |
| `timestamp` | TEXT | Fecha y hora de la alerta |
| `resuelto_en` | TEXT | Fecha y hora de resolución (si aplica) |

Las alertas tienen un mecanismo de antirrebote de **60 segundos**: no se inserta una segunda alerta del mismo tipo si la anterior tiene menos de 60 s de antigüedad.

#### Tabla: `estado_dispositivos`
Historial de heartbeats y cambios de estado de cada nodo.

| Columna | Tipo | Descripción |
| :---- | :---- | :---- |
| `id` | INTEGER PK | Autoincremental |
| `device_id` | TEXT FK | Referencia a `dispositivos` |
| `modulo` | TEXT | Módulo funcional |
| `status` | TEXT | `online`, `offline`, `sin_datos`, `error` |
| `detalle` | TEXT | JSON completo del mensaje de status |
| `timestamp` | TEXT | Fecha y hora local |

#### Tabla: `usuarios`
Cuentas de acceso al dashboard.

| Columna | Tipo | Descripción |
| :---- | :---- | :---- |
| `id` | INTEGER PK | Autoincremental |
| `username` | TEXT UNIQUE | Nombre de usuario |
| `password_hash` | TEXT | Hash Werkzeug (pbkdf2:sha256) |
| `rol` | TEXT | `usuario`, `trabajador`, `admin` |
| `active_session_token` | TEXT | Token de sesión activa (1 por usuario) |
| `ultimo_login` | TEXT | Fecha y hora del último acceso |
| `creado_en` | TEXT | Fecha de creación de la cuenta |

#### Tabla: `reportes_ciudadanos`
Incidencias reportadas por ciudadanos.

| Columna | Tipo | Descripción |
| :---- | :---- | :---- |
| `id` | INTEGER PK | Autoincremental |
| `usuario_id` | INTEGER FK | Referencia a `usuarios` |
| `categoria` | TEXT | `ambiental`, `residuos`, `vigilancia` |
| `titulo` | TEXT | Título del reporte |
| `ubicacion` | TEXT | Descripción de ubicación |
| `descripcion` | TEXT | Descripción detallada |
| `urgencia` | TEXT | `baja`, `media`, `alta` |
| `estado` | TEXT | `pendiente`, `en_revision`, `atendido`, `rechazado` |
| `observacion_admin` | TEXT | Nota del personal al atender el caso |
| `imagen` | TEXT | Nombre del archivo de imagen adjunto |
| `creado_en` | TEXT | Fecha de creación |
| `actualizado_en` | TEXT | Fecha de última actualización |

### Índices de rendimiento

La base de datos incluye 11 índices para optimizar las consultas frecuentes por tiempo y dispositivo:

| Índice | Tabla | Columnas indexadas |
| :---- | :---- | :---- |
| `idx_amb_ts` | `lecturas_ambientales` | `timestamp DESC` |
| `idx_amb_dev` | `lecturas_ambientales` | `device_id, variable, timestamp DESC` |
| `idx_res_ts` | `lecturas_residuos` | `timestamp DESC` |
| `idx_res_sid` | `lecturas_residuos` | `sensor_id, timestamp DESC` |
| `idx_son_ts` | `lecturas_sonido` | `timestamp DESC` |
| `idx_img_ts` | `imagenes_meta` | `timestamp DESC` |
| `idx_alt_est` | `eventos_alerta` | `estado, timestamp DESC` |
| `idx_alt_mod` | `eventos_alerta` | `modulo, tipo_alerta, timestamp DESC` |
| `idx_est_dev` | `estado_dispositivos` | `device_id, timestamp DESC` |
| `idx_reportes_estado` | `reportes_ciudadanos` | `estado, creado_en DESC` |

## **6.3. Pipeline de Datos en la Nube — Modelo Medallón**

Complementariamente al entorno local, el proyecto implementa un pipeline de exportación hacia la nube en tres capas:

| Capa | Almacenamiento | Descripción |
| :---- | :---- | :---- |
| **Bronze** | Amazon S3 (formato Parquet) | Exportación directa desde SQLite. Dato crudo sin transformar. |
| **Silver** | Amazon S3 (Parquet filtrado) | Datos limpios: sin nulos, estados `ok`, duplicados eliminados. |
| **Gold** | Amazon S3 / AWS Athena | Tablas analíticas agrupadas por hora/día, listas para Power BI. |

Los scripts de exportación (`subir_gold_s3.py`, `ejecutar_athena_gold.py`) se ejecutan manualmente en esta fase. La automatización mediante AWS Lambda o tareas programadas es un pendiente del proyecto.

**AWS Athena** permite ejecutar consultas SQL estándar sobre los archivos Parquet almacenados en S3 sin necesidad de un motor de base de datos relacional dedicado en la nube, reduciendo el costo operativo.

**Amazon S3** almacena los datos con cifrado en reposo (SSE-S3) y políticas de acceso mínimo. La configuración de cifrado está documentada en `aws_s3_encryption_config.json`.

---

# **7. Capa de Aplicación**

## **7.1. Dashboard Web**

El dashboard es la interfaz principal de visualización. Está servido por Flask en `http://127.0.0.1:5000` y renderizado en el navegador del operador. Utiliza las siguientes tecnologías de frontend:

| Tecnología | Versión | Uso |
| :---- | :---- | :---- |
| HTML5 | — | Estructura semántica de la interfaz |
| CSS3 | — | Estilos, layout responsivo, sistema de colores por módulo, animaciones de estado |
| JavaScript (vanilla) | ES2020+ | Polling de API, actualización dinámica del DOM, gestión de gráficas |
| Chart.js | Última estable (CDN) | Gráficas de series temporales para ambiental, residuos y sonido |
| Fetch API | Nativa | Consumo de `/api/data` cada 2 segundos |

### Componentes visuales del dashboard

| Sección | Elementos |
| :---- | :---- |
| **Topbar** | Nombre de usuario, rol, estado MQTT, hora de última actualización, navegación por rol, botón de cierre de sesión |
| **Quick Stats** | Contadores de reportes: total, pendientes, en revisión, atendidos |
| **Panel de acciones** | Acciones rápidas contextuales según el rol del usuario |
| **Módulo Cámara** | Stream MJPEG embebido (`<img src="…/stream">`), indicador de señal en vivo / sin señal |
| **Módulo Ambiental** | Dot de estado del nodo, badges de calidad de aire, chips de sensor activo, cuatro tarjetas métricas con barras de nivel, historial gráfico |
| **Módulo Residuos** | Dot de estado del nodo, resumen de contenedores (activos, promedio, en alerta), cuatro tarjetas de tacho con barra de llenado visual, historial gráfico |
| **Módulo Sonido** | Dot de estado del nodo, tarjetas de nivel RAW, voltaje, porcentaje, clasificación, historial gráfico |
| **Log MQTT** | Últimas 25 entradas de mensajes recibidos con timestamp |

### Detección de estado en línea/fuera de línea (frontend)

El archivo `dashboard/static/app.js` implementa la función `nodoOnline(ultima_vez, deviceId, maxSeg)` que compara el timestamp del servidor con el reloj local del navegador:

```
nodoOnline = (Date.now()/1000 − ultima_vez_modulos[deviceId]) < maxSeg
```

Los umbrales de timeout por nodo son:

| Nodo | Timeout | Justificación |
| :---- | :---- | :---- |
| ESP32\_AIRE\_01 | 60 segundos | Publica cada 5 s; 12 ciclos de margen |
| ESP32\_RESIDUOS\_01 | 60 segundos | Publica cada 5 s; 12 ciclos de margen |
| ESP32\_KY037\_01 | 30 segundos | Publica cada 3 s; 10 ciclos de margen |
| ESP32\_CAM\_01 | 120 segundos | Heartbeat cada 30 s; 4 ciclos de margen |

Cuando un nodo está fuera de línea, el dashboard aplica los siguientes cambios visuales:
- El punto de estado (`node-dot`) pierde la clase `online` y queda gris sin animación.
- Los valores de las métricas muestran `--` en lugar del último dato conocido.
- Las barras de nivel se vacían al 0%.
- Los chips de sensor cambian a estado `offline` (gris).
- El campo "Última lectura" muestra la hora exacta del último mensaje del nodo específico (no la hora del sistema).

## **7.2. Sistema de Reportes Ciudadanos**

El portal de reportes permite a los ciudadanos registrar incidencias urbanas relacionadas con los módulos de monitoreo del sistema. Incluye:

- Formulario de nuevo reporte con campos: categoría (ambiental / residuos / vigilancia), título, ubicación, descripción, urgencia e imagen adjunta opcional.
- Validación de imágenes: extensión permitida (`png`, `jpg`, `jpeg`, `webp`), tamaño máximo configurable (por defecto 5 MB), verificación del contenido real del archivo mediante Pillow (protección contra archivos renombrados).
- Listado de reportes con filtros por estado, categoría y ordenamiento.
- Cambio de estado y registro de observaciones por parte del personal.

## **7.3. Modelo de Roles (RBAC)**

El sistema implementa control de acceso basado en roles con tres niveles:

| Rol | Puede hacer |
| :---- | :---- |
| `usuario` | Ver el dashboard, enviar reportes, ver sus propios reportes |
| `trabajador` | Ver el dashboard, ver todos los reportes, cambiar estados y registrar observaciones |
| `admin` | Todo lo anterior, gestionar usuarios (crear trabajadores, activar/desactivar cuentas) |

El registro público (`/registro`) crea únicamente cuentas de rol `usuario`. Las cuentas de `trabajador` y `admin` las crea exclusivamente un administrador desde el panel `/usuarios`.

---

# **8. Capacidades Transversales de Gestión**

## **8.1. Gestión de Identidad de Dispositivos**

Cada nodo tiene un identificador único de formato `ESP32_<MODULO>_<NUMERO>` (ej. `ESP32_AIRE_01`). Este `device_id` está codificado en el firmware de cada sketch y es inmutable. Es el campo clave de la tabla `dispositivos` y aparece en todos los mensajes MQTT publicados por el nodo, permitiendo su trazabilidad en toda la plataforma.

## **8.2. Versionado de Firmware y Contrato de Mensajes**

El firmware de cada nodo publica dos campos de versión en sus mensajes de heartbeat:

- `firmware_version`: versión semántica del código Arduino (ej. `1.1.0`).
- `schema_version`: versión del contrato de mensajes JSON (actualmente `1.0`).

El contrato formal del mensaje de estado está definido como JSON Schema en `schemas/estado-dispositivo.schema.json`, que valida los campos mínimos requeridos (`schema_version`, `device_id`, `modulo`, `status`) y los tipos de datos de los campos opcionales (`rssi_dbm`, `uptime_ms`, `ip`).

## **8.3. Monitoreo de Disponibilidad**

El servidor registra la disponibilidad de cada nodo mediante:

1. **MQTT Last Will**: detección inmediata de desconexión inesperada.
2. **Timeout en el frontend**: detección de nodos silenciosos (sin Last Will, ej. pérdida de alimentación sin desconexión TCP).
3. **Tabla `estado_dispositivos`**: historial completo de todos los cambios de estado (online/offline/error) con timestamp y payload completo del mensaje.
4. **Tabla `dispositivos.ultima_vez`**: campo actualizado en cada heartbeat, permite consultar la última vez que se comunicó cada nodo.

## **8.4. Log del Sistema**

El dashboard mantiene en memoria un log circular de los últimos 25 mensajes MQTT recibidos, con timestamp y tópico de origen. Este log se muestra en la sección "Log de recepción MQTT" del dashboard y se sirve como parte del JSON de `/api/data`.

---

# **9. Capacidades Transversales de Seguridad**

## **9.1. Seguridad en la Capa de Dispositivo**

| Medida | Implementación |
| :---- | :---- |
| Secretos fuera del código | Credenciales en `secrets.h` (git-ignorado); plantilla en `secrets.h.example` |
| Autenticación de red | Contraseña del AP de configuración en `secrets.h` |
| Autenticación MQTT | Usuario y contraseña por dispositivo (todos los nodos) |

## **9.2. Seguridad en la Capa de Red**

| Medida | Implementación |
| :---- | :---- |
| Autenticación MQTT | Mosquitto con `password_file`, `allow_anonymous false` |
| ACL preparada | `mosquitto.acl.example` define permisos mínimos por dispositivo (pendiente de activar) |
| TLS preparado | `mosquitto-secure.conf.example` + perfil `WiFiClientSecure` en firmware (pendiente de activar) |

## **9.3. Seguridad en la Capa de Aplicación**

| Medida | Implementación |
| :---- | :---- |
| Hash de contraseñas | Werkzeug `generate_password_hash` (pbkdf2:sha256, iteraciones adaptativas) |
| Sesión única por usuario | Token aleatorio (`secrets.token_urlsafe(32)`) en `active_session_token`; login nuevo invalida sesión anterior |
| Protección CSRF | Token de sesión en formularios POST; validado en `before_request` con `secrets.compare_digest` |
| Rate limiting de login | Máximo 5 intentos por IP+usuario en ventana de 15 minutos |
| Cabeceras HTTP de seguridad | `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Content-Security-Policy` |
| CSP restrictiva | `default-src 'self'`; solo se permite Chart.js desde CDN jsdelivr.net |
| Validación de imágenes | Verificación con Pillow del contenido real (no solo extensión) |
| Tamaño máximo de carga | 5 MB por defecto, configurable en `.env` |
| Variables de entorno | Secretos en `dashboard/.env` (git-ignorado); no en el código fuente |

## **9.4. Pendientes de Seguridad**

1. **Activar MQTT/TLS**: generar PKI local (CA, certificado del broker, llaves de cliente), configurar `mosquitto-secure.conf` y adaptar los ESP32 a `WiFiClientSecure`.
2. **ACL individuales por dispositivo**: asignar credenciales y permisos de publicación/suscripción únicos a cada nodo ESP32.
3. **OTA firmada**: implementar actualización de firmware Over-the-Air con verificación de firma digital.
4. **Auditoría de accesos**: persistir en base de datos el registro de acciones de usuarios (login, cambio de estado de reportes, gestión de usuarios).

---

# **10. Resumen de Tecnologías Empleadas**

| Categoría | Tecnología | Versión | Rol en el sistema |
| :---- | :---- | :---- | :---- |
| **Microcontrolador** | Espressif ESP32 (Xtensa LX6) | — | Nodo de campo para captura de datos |
| **Framework firmware** | Arduino Framework (ESP-IDF) | — | Desarrollo de firmware en C++ |
| **Sensor temperatura/humedad** | DHT22 | — | Módulo ambiental |
| **Sensor presión** | BMP280 | — | Módulo ambiental |
| **Sensor gas** | MQ-2 | — | Módulo ambiental |
| **Sensor ultrasonido** | HC-SR04 | — | Módulo residuos (×3) |
| **Sensor sonido** | KY-037 | — | Módulo sonido |
| **Cámara** | OV2640 (en ESP32-CAM) | — | Módulo videovigilancia |
| **Conectividad inalámbrica** | Wi-Fi 802.11 b/g/n (2.4 GHz) | — | Transporte entre sensores y servidor |
| **Protocolo de mensajería** | MQTT 3.1.1 | — | Protocolo IoT de pub/sub ligero |
| **Broker MQTT** | Eclipse Mosquitto | 2.1.2 | Intermediario de mensajes |
| **Formato de datos** | JSON (RFC 8259) | — | Intercambio de datos entre nodos y servidor |
| **Protocolo de streaming** | MJPEG (multipart HTTP) | — | Stream de video de la cámara |
| **Resolución de nombres local** | mDNS / Bonjour | — | Acceso por nombre en red local |
| **Lenguaje backend** | Python | 3.x | Servidor web y procesamiento |
| **Framework web** | Flask | ≥ 3.0 | API REST, templates, sesiones |
| **Cliente MQTT Python** | paho-mqtt | ≥ 2.0 | Suscripción y recepción de mensajes |
| **Hash de contraseñas** | Werkzeug (pbkdf2:sha256) | ≥ 3.0 | Seguridad de autenticación |
| **Variables de entorno** | python-dotenv | ≥ 1.0 | Gestión de configuración |
| **Procesamiento de imágenes** | Pillow | ≥ 10.0 | Validación de archivos subidos |
| **Base de datos** | SQLite 3 (modo WAL) | 3.x | Persistencia local de series de tiempo |
| **Frontend** | HTML5, CSS3, JavaScript (ES2020) | — | Interfaz de usuario del dashboard |
| **Gráficas** | Chart.js | Última estable | Visualización de series temporales |
| **Control de versiones** | Git | — | Gestión del código fuente |
| **Almacenamiento en nube** | Amazon S3 | — | Data lake: capas Bronze, Silver, Gold |
| **Motor de consultas nube** | AWS Athena | — | SQL sobre Parquet en S3 |
| **Visualización analítica** | Microsoft Power BI | — | Dashboards históricos (fase futura) |
| **Esquema de contrato** | JSON Schema (Draft 2020-12) | — | Validación formal del mensaje de estado |

---

# **11. Flujo de Datos Detallado**

## **11.1. Flujo de datos de sensor ambiental (ejemplo)**

```
1. ESP32_AIRE_01 lee DHT22 (I²C)
2. Construye JSON: {"device_id":"ESP32_AIRE_01","value":23.5,"estado":"ok",...}
3. Publica en MQTT tópico "lscc/ambiental/temperatura" (QoS 0)
4. Mosquitto broker recibe y enruta al suscriptor "dashboard_lscc_fase1"
5. app.py on_message() recibe el payload
6. Verifica device_id en tabla dispositivos (activo=1)
7. Actualiza estado["ambiental"]["temperatura"] = 23.5
8. Actualiza estado["ultima_vez_modulos"]["ESP32_AIRE_01"] = time.time()
9. Agrega punto al historial en memoria (deque circular 30 puntos)
10. Inserta fila en lecturas_ambientales (SQLite)
11. Frontend consulta /api/data (cada 2 s)
12. JavaScript recibe JSON, evalúa nodoOnline() → true
13. Actualiza <strong id="temperatura"> con "23.5°"
14. Actualiza barra de temperatura (23.5/50 * 100 = 47%)
15. Actualiza gráfica Chart.js con nuevo punto
```

## **11.2. Flujo de detección de nodo offline (Last Will)**

```
1. ESP32_AIRE_01 pierde alimentación (desconexión inesperada)
2. Mosquitto detecta keepalive timeout o cierre TCP abrupto
3. Mosquitto entrega el Last Will a "lscc/sistema/status":
   {"device_id":"ESP32_AIRE_01","status":"offline",...}
4. app.py on_message() recibe el Last Will
5. Detecta: topic == "lscc/sistema/status" AND status == "offline"
6. Establece estado["ultima_vez_modulos"]["ESP32_AIRE_01"] = 0
7. Frontend en próxima consulta: Date.now()/1000 - 0 = muy grande > 60
8. nodoOnline() → false
9. Dashboard muestra: dot gris, valores "--", barras a 0%
10. "Última lectura" muestra la hora del último mensaje real recibido
```

---

# **12. Contrato de Mensaje de Estado (Schema v1.0)**

El mensaje de heartbeat publicado por cada nodo en `lscc/sistema/status` cumple el siguiente contrato formal:

```json
{
  "schema_version": "1.0",
  "device_id": "ESP32_AIRE_01",
  "modulo": "ambiental",
  "status": "online",
  "firmware_version": "1.1.0",
  "uptime_ms": 3600000,
  "rssi_dbm": -62,
  "ip": "192.168.1.45"
}
```

El esquema JSON Schema (Draft 2020-12) en `schemas/estado-dispositivo.schema.json` define:
- Campos obligatorios: `schema_version`, `device_id`, `modulo`, `status`.
- `device_id` debe seguir el patrón `^ESP32_[A-Z0-9_]+$`.
- `modulo` es un enum: `ambiental`, `calidad_aire`, `residuos`, `vigilancia`, `videovigilancia`.
- `status` es un enum: `online`, `offline`, `sin_datos`, `error`.
- El campo `rssi_dbm` debe estar en el rango [−120, 0].

---

# **13. Estructura de Archivos del Proyecto**

```
lima_smart_fase1_login/
├── dashboard/                      Servidor Flask + assets web
│   ├── app.py                      Servidor principal (MQTT + Flask + SQLite)
│   ├── crear_db.py                 Inicialización de la base de datos
│   ├── ver_db.py                   Consulta rápida de la base de datos
│   ├── requirements.txt            Dependencias Python
│   ├── mosquitto.conf              Configuración del broker MQTT
│   ├── mosquitto_passwd.txt        Contraseñas MQTT (no en Git en producción)
│   ├── mosquitto-secure.conf.example  Perfil TLS (pendiente)
│   ├── mosquitto.acl.example       ACL por dispositivo (pendiente)
│   ├── .env.example                Plantilla de configuración
│   ├── static/
│   │   ├── app.js                  Lógica frontend (polling, gráficas, DOM)
│   │   └── style.css               Estilos del dashboard
│   └── templates/
│       ├── index.html              Dashboard principal
│       ├── login.html              Pantalla de inicio de sesión
│       ├── registro.html           Registro de ciudadanos
│       ├── reportes.html           Listado de reportes
│       ├── nuevo_reporte.html      Formulario de nuevo reporte
│       └── usuarios.html           Gestión de usuarios (admin)
├── arduino/
│   ├── ambiental/MQ2_BMP280_DHT22/ Firmware módulo ambiental
│   ├── camara/CAMARA/              Firmware módulo cámara
│   ├── residuos/HCR_04/            Firmware módulo residuos
│   └── ky037/                      Firmware módulo sonido
├── schemas/
│   └── estado-dispositivo.schema.json  JSON Schema del heartbeat
├── documentacion/                  Documentación técnica complementaria
├── CLAUDE.md                       Guía de desarrollo para Claude Code
└── README.md                       Guía de inicio rápido
```

---

# **14. Pendientes Principales**

| Ítem | Descripción | Prioridad |
| :---- | :---- | :---- |
| Activar MQTT/TLS | Generar PKI local y habilitar cifrado en broker y dispositivos | Alta |
| ACL por dispositivo | Credenciales y permisos individuales por nodo ESP32 | Alta |
| Separar ingesta MQTT del proceso web | El hilo MQTT y Flask comparten proceso; separar en servicios independientes mejora la robustez | Media |
| OTA firmada | Actualización de firmware Over-the-Air con verificación criptográfica | Media |
| Resolver cantidad de tachos | Definir si se instala un cuarto HC-SR04 o se elimina la tarjeta del dashboard | Media |
| Automatizar pipeline S3/Athena | Ejecutar exportación a la nube de forma periódica y automática | Media |
| Auditoría de accesos | Persistir en DB las acciones de usuarios del dashboard | Baja |
| Dashboards Power BI | Conectar Athena con Power BI y publicar visualizaciones históricas | Baja |
| Monitoreo de salud del servidor | Health-check, alertas de caída del broker o Flask, métricas de rendimiento | Baja |

---

# **15. Conclusiones**

El sistema Lima Smart Core City implementa de forma integral el modelo de referencia IoT de la Recomendación UIT-T Y.2060, mapeando cada componente real del proyecto a la capa arquitectónica que le corresponde:

- **Capa de dispositivo**: cuatro nodos ESP32 con sensores especializados, firmware robusto con reconexión automática, gestión de configuración en NVS, MQTT Last Will y versionado de contrato de mensajes.

- **Capa de red**: Wi-Fi 802.11 b/g/n como medio de acceso, MQTT 3.1.1 como protocolo de mensajería pub/sub ligero y Eclipse Mosquitto 2.1.2 como broker con autenticación habilitada.

- **Capa de apoyo a servicios y aplicaciones**: Flask como servidor con hilo MQTT daemon, SQLite con WAL para persistencia concurrente, pipeline medallón hacia Amazon S3 y AWS Athena para análisis histórico.

- **Capa de aplicación**: dashboard web con actualización en tiempo real, sistema de reportes ciudadanos con flujo de atención por roles y capacidad de visualización analítica futura en Power BI.

- **Capacidades de gestión**: inventario de dispositivos, heartbeat periódico, detección de desconexión por Last Will y timeout, historial de estados y versionado de firmware y esquema.

- **Capacidades de seguridad**: autenticación MQTT, hash de contraseñas, sesión única, protección CSRF, rate limiting, cabeceras HTTP de seguridad y secretos fuera del repositorio. Los perfiles TLS y ACL están preparados y constituyen el paso inmediato siguiente para alcanzar un nivel de seguridad apropiado para despliegue en entornos no controlados.

El proyecto demuestra la viabilidad de construir una plataforma IoT urbana académica funcional, escalable y alineada con estándares internacionales utilizando exclusivamente hardware de bajo costo (ESP32) y software de código abierto (Mosquitto, Flask, SQLite, Python).

---

# **Referencias**

Unión Internacional de Telecomunicaciones. (2012). *Recomendación UIT-T Y.2060 (06/2012): Descripción general de Internet de los objetos*. UIT-T.

Fermín Pérez, A. (2025). *Sesión 01: Introducción a Internet de las Cosas* \[Diapositivas\]. Universidad Nacional Mayor de San Marcos, Facultad de Ingeniería de Sistemas e Informática.

Fermín Pérez, A. (2025). *Sesión 02: Arquitectura de Internet de las Cosas* \[Diapositivas\]. Universidad Nacional Mayor de San Marcos, Facultad de Ingeniería de Sistemas e Informática.

Al-Fuqaha, A., Guizani, M., Mohammadi, M., Aledhari, M., & Ayyash, M. (2015). Internet of Things: A survey on enabling technologies, protocols, and applications. *IEEE Communications Surveys & Tutorials*, 17(4), 2347–2376.

Peralta, G., Iglesias-Urkia, M., Barcelo, M., Gomez, R., Morán, A., & Bilbao, J. (2022). Fog computing based efficient IoT scheme for the Industry 4.0. *Electronics*, 11(11), 1677.

Eclipse Foundation. (2023). *Eclipse Mosquitto – An open source MQTT broker*. https://mosquitto.org/

Espressif Systems. (2024). *ESP32 Technical Reference Manual*. https://www.espressif.com/

Flask Project. (2024). *Flask Documentation (3.x)*. https://flask.palletsprojects.com/
