# Lima Smart Core City (LSCC)

Plataforma IoT académica alineada con el modelo de referencia de cuatro capas de ITU-T Y.2060. Integra sensores ESP32, MQTT, Flask, SQLite, un data lake en Amazon S3, Athena y una futura capa analítica en Power BI.

Versión de trabajo: `0.2.0-consolidacion-fase1`.

Punto de retorno estable:

- Tag Git: `v0.1.0-pre-consolidacion`
- Commit: `54ea5af`
- Respaldo: `versiones/LSCC_v0.1.0-pre-consolidacion.zip`

## Arquitectura actual

```text
Sensores
  -> ESP32
  -> Wi-Fi / IPv4 / TCP
  -> MQTT / Mosquitto
  -> Flask
  -> SQLite
  -> Bronze / Silver / Gold
  -> Amazon S3 / Athena
  -> Power BI
```

Módulos físicos:

- Ambiental: DHT22, BMP280 y MQ-2.
- Residuos: tres HC-SR04 configurados actualmente.
- Videovigilancia: ESP32-CAM.
- Sonido: KY-037 en un ESP32 independiente.

## Configuración privada

Los secretos no deben escribirse en los archivos `.ino` ni publicarse en Git.

- Dashboard: copiar `dashboard/.env.example` como `dashboard/.env`.
- Cada sketch: copiar `secrets.h.example` como `secrets.h`.
- Broker: generar `dashboard/mosquitto_passwd.txt` con `mosquitto_passwd`.

Los archivos `.env`, `secrets.h`, la base SQLite, imágenes y adjuntos están ignorados por Git.

## Preparación inicial en Windows (CMD)

Instalar Mosquitto:

```bat
winget install --id EclipseFoundation.Mosquitto --exact --accept-package-agreements --accept-source-agreements
```

Instalar las dependencias Python:

```bat
cd dashboard
python -m pip install -r requirements.txt
```

Si todavía no existe la base:

```bat
python crear_db.py
```

No ejecutes `crear_db.py` sobre una base con información sin realizar antes un respaldo.

## Arranque diario

Debe existir una sola instancia de Mosquitto. Para evitar que el servicio predeterminado compita con la configuración del proyecto, abre CMD como administrador y ejecuta:

```bat
net stop mosquitto
netstat -ano | findstr :1883
```

Desde `dashboard`, inicia el broker del proyecto:

```bat
"C:\Program Files\mosquitto\mosquitto.exe" -c mosquitto.conf -v
```

El resultado esperado es:

```text
Opening ipv4 listen socket on port 1883
mosquitto version 2.1.2 running
```

En otra ventana CMD, inicia Flask:

```bat
cd dashboard
python app.py
```

Abrir únicamente:

```text
http://127.0.0.1:5000/login
```

Las credenciales administrativas se encuentran en el `.env` local.

## Prueba MQTT

Suscripción:

```bat
"C:\Program Files\mosquitto\mosquitto_sub.exe" -h 127.0.0.1 -p 1883 -u lscc_user -P "TU_CLAVE" -t "lscc/#" -v
```

Publicación de prueba:

```bat
"C:\Program Files\mosquitto\mosquitto_pub.exe" -h 127.0.0.1 -p 1883 -u lscc_user -P "TU_CLAVE" -t "lscc/prueba" -m "hola"
```

## Firmware ESP32

Antes de compilar:

1. Verificar el `secrets.h` de cada sketch.
2. Usar como broker la IPv4 actual de la PC obtenida con `ipconfig`.
3. Confirmar que la contraseña coincide con `dashboard/.env` y `mosquitto_passwd.txt`.
4. Cargar nuevamente los cuatro sketches después de modificar el firmware.

Los equipos con WiFiManager pueden conservar una configuración anterior en memoria. Si no toman el nuevo broker, usar el botón de reset de configuración y completar nuevamente el portal.

## Tópicos principales

```text
lscc/ambiental/temperatura
lscc/ambiental/humedad
lscc/ambiental/presion
lscc/ambiental/gas
lscc/residuos/nivel
lscc/vigilancia/sonido
lscc/vigilancia/imagen
lscc/vigilancia/imagen_meta
lscc/sistema/status
```

## Diagnóstico rápido

Si Mosquitto recibe datos pero el dashboard no cambia:

1. Ejecutar `netstat -ano | findstr :1883`.
2. Comprobar que exista un solo proceso `LISTENING`.
3. Confirmar que Flask y los ESP32 usan ese mismo broker.
4. Buscar en Mosquitto `Sending PUBLISH to dashboard_lscc_fase1`.
5. Suscribirse manualmente a `lscc/#` para inspeccionar el JSON.

Dos brokers simultáneos pueden producir un estado engañoso: Flask aparece conectado a uno mientras los ESP32 publican en otro.

Para consultar SQLite:

```bat
cd dashboard
python ver_db.py
python ver_db.py residuos
python ver_db.py dispositivos
python ver_db.py alertas
```

## Estado de los tachos

El firmware de residuos está configurado actualmente con `N_SENS = 3`, mientras que el dashboard conserva cuatro tarjetas. Esto no afecta el JSON de los tres sensores activos, pero el cuarto permanecerá vacío hasta decidir entre:

- instalar un cuarto HC-SR04 y ampliar pines; o
- adaptar dashboard y esquema para mostrar solo tres tachos.

Una lectura `distancia_cm = -1` significa que el HC-SR04 no recibió eco. Deben revisarse alimentación, tierra común, pines Trig/Echo, divisor de voltaje del Echo y posición física del sensor.

## Documentación

- `documentacion/ARQUITECTURA_Y2060.md`: correspondencia con Y.2060.
- `documentacion/GUIA_OPERACION_LOCAL.md`: arranque, verificación y solución de problemas.
- `documentacion/PIPELINE_MEDALLON_LOCAL.md`: capas Bronze, Silver y Gold.
- `documentacion/ATHENA_GOLD_POWERBI.md`: Athena y conexión futura con Power BI.
- `schemas/estado-dispositivo.schema.json`: contrato formal del heartbeat.

## Pendientes principales

- Resolver la cantidad definitiva de tachos.
- Activar MQTT/TLS con certificados.
- Crear usuarios y ACL MQTT únicos por dispositivo.
- Separar la ingesta MQTT del proceso web.
- Incorporar OTA firmada, auditoría y monitoreo.
- Automatizar S3/Athena y completar los dashboards de Power BI.
