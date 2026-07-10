# Guía de operación local LSCC

Esta guía describe el arranque y diagnóstico del entorno local en Windows usando CMD.

## Componentes que deben ejecutarse

1. Un único broker Mosquitto.
2. El dashboard Flask.
3. Los ESP32 conectados a la misma red y al mismo broker.

## Secuencia de arranque

### 1. Detener el servicio Mosquitto predeterminado

Ejecutar CMD como administrador:

```bat
net stop mosquitto
netstat -ano | findstr :1883
```

No debe quedar otro proceso escuchando en `127.0.0.1:1883`. Las conexiones `TIME_WAIT` desaparecerán automáticamente y no representan un broker activo.

### 2. Iniciar el broker del proyecto

```bat
cd /d "RUTA_DEL_PROYECTO\dashboard"
"C:\Program Files\mosquitto\mosquitto.exe" -c mosquitto.conf -v
```

Debe escuchar en `0.0.0.0:1883`, permitiendo conexiones locales y desde la red Wi-Fi.

### 3. Iniciar Flask

En otra ventana:

```bat
cd /d "RUTA_DEL_PROYECTO\dashboard"
python app.py
```

Abrir `http://127.0.0.1:5000/login` en un navegador normal. No usar HTTPS, `0.0.0.0` ni la vista previa proxy del IDE.

### 4. Encender o reiniciar los ESP32

El broker debe mostrar conexiones con identificadores como:

```text
ESP32_AIRE_01
ESP32_RESIDUOS_01
ESP32_CAM_01
ESP32_KY037_01
```

## Validación extremo a extremo

```text
ESP32 publica
  -> Mosquitto muestra Received PUBLISH
  -> Mosquitto muestra Sending PUBLISH to dashboard_lscc_fase1
  -> Flask actualiza /api/data
  -> SQLite recibe una fila
  -> navegador actualiza la tarjeta
```

## Capturar un JSON real

```bat
"C:\Program Files\mosquitto\mosquitto_sub.exe" -h 127.0.0.1 -p 1883 -u lscc_user -P "TU_CLAVE" -t "lscc/#" -v
```

El estado de dispositivo debe incluir al menos:

```json
{
  "schema_version": "1.0",
  "device_id": "ESP32_RESIDUOS_01",
  "modulo": "residuos",
  "status": "online"
}
```

## Problema: MQTT conectado pero sin datos

Causa más frecuente: dos brokers simultáneos.

```bat
netstat -ano | findstr :1883
tasklist /FI "PID eq NUMERO_PID"
```

Debe existir un solo PID en estado `LISTENING`. Si Flask está conectado a un broker de localhost y los ESP32 a otro broker de red, ninguno de los mensajes llegará al dashboard.

## Problema: el ESP32 publica pero SQLite no cambia

Revisar:

- `device_id` registrado en la tabla `dispositivos`.
- tópico exacto esperado por `dashboard/app.py`.
- JSON válido.
- restricciones de la tabla SQLite.
- mensajes `[DB] Error ...` en la consola de Flask.

Comandos:

```bat
cd dashboard
python ver_db.py dispositivos
python ver_db.py residuos
```

## Problema: HC-SR04 devuelve -1

`-1` significa ausencia de eco, no error de JSON. Verificar:

- alimentación estable del HC-SR04;
- tierra común entre sensor y ESP32;
- conexión correcta de Trig y Echo;
- divisor de voltaje en Echo para no enviar 5 V al ESP32;
- distancia y orientación del sensor;
- que los sensores no se disparen simultáneamente.

El firmware actual usa tres sensores. La cuarta tarjeta del dashboard permanece pendiente de definición.

## Cierre ordenado

1. Detener Flask con `Ctrl+C`.
2. Detener Mosquitto con `Ctrl+C`.
3. No finalizar procesos mientras SQLite esté escribiendo.

## TLS

El perfil `mosquitto-secure.conf.example` está preparado, pero no debe activarse hasta generar CA, certificado y llave del servidor y adaptar los ESP32 a `WiFiClientSecure`.
