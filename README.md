# Lima Smart Core City — Fase 1

## Estructura de archivos

```
lima_smart_fase1/
│
├── arduino/
│   ├── ambiental/     MQ2_BMP280_DHT22.ino  ← ESP32 módulo ambiental
│   ├── residuos/      HCR_04.ino            ← ESP32 módulo residuos
│   ├── camara/        CAMARA.ino            ← ESP32-CAM módulo cámara
│   └── ky037/         KY037.ino             ← ESP32 módulo sonido
│
├── dashboard/
│   ├── app.py                ← Flask + MQTT + SQLite
│   ├── mosquitto.conf        ← Config broker con auth
│   ├── mosquitto_passwd.txt  ← Contraseñas broker (regenerar)
│   ├── requirements.txt
│   ├── iniciar_dashboard.bat
│   ├── templates/            (copiar de versión anterior)
│   └── static/               (copiar de versión anterior)
│
└── db/
    ├── crear_db.py   ← Crea lscc.db con todas las tablas
    └── ver_db.py     ← Diagnóstico de la base de datos
```

---

## Paso a paso de implementación

### PASO 1 — Instalar Mosquitto con autenticación

**Windows:**
1. Descargar Mosquitto desde https://mosquitto.org/download/
2. Instalar con la opción "Add to PATH"
3. Abrir PowerShell como administrador:

```powershell
# Generar archivo de contraseñas (ingresa "lscc2025" cuando pida)
mosquitto_passwd -c "C:\Program Files\mosquitto\mosquitto_passwd.txt" lscc_user

# Verificar que el servicio existe
Get-Service -Name mosquitto
```

4. Copiar `mosquitto.conf` de este proyecto a:
   `C:\Program Files\mosquitto\mosquitto.conf`

5. Editar el `mosquitto.conf` y cambiar la ruta del password_file:
   ```
   password_file C:\Program Files\mosquitto\mosquitto_passwd.txt
   ```

6. Reiniciar el servicio:
```powershell
Stop-Service mosquitto
Start-Service mosquitto

# Verificar que está corriendo
Get-Service mosquitto
```

7. Probar la autenticación:
```powershell
# En una terminal: suscribir
mosquitto_sub -h 127.0.0.1 -p 1883 -u lscc_user -P lscc2025 -t "lscc/#" -v

# En otra terminal: publicar
mosquitto_pub -h 127.0.0.1 -p 1883 -u lscc_user -P lscc2025 -t "lscc/prueba" -m "hola"
```
Si ves "lscc/prueba hola" en la primera terminal, ¡el broker funciona!

---

### PASO 2 — Crear el entorno Python y la base de datos

```bash
# Desde la carpeta dashboard/
cd lima_smart_fase1/dashboard

# Crear entorno virtual
python -m venv venv

# Activar (Windows)
venv\Scripts\activate

# Instalar dependencias
pip install -r requirements.txt

# Crear la base de datos (ejecutar DESDE la carpeta dashboard/)
python ..\db\crear_db.py
```

Verás el mensaje:
```
✅  Listo. Ahora puedes iniciar el dashboard con: python app.py
```

El archivo `lscc.db` debe quedar en la carpeta `dashboard/`.

---

### PASO 3 — Iniciar el dashboard

```bash
# Desde la carpeta dashboard/ con el venv activado:
python app.py

# O simplemente hacer doble clic en:
iniciar_dashboard.bat
```

Abrir en el navegador: http://localhost:5000

---

### PASO 4 — Instalar librería ArduinoJson en Arduino IDE

1. Abrir Arduino IDE
2. Ir a **Herramientas → Administrar bibliotecas...**
3. Buscar "ArduinoJson"
4. Instalar **ArduinoJson** de Benoit Blanchon (versión 6.x o 7.x)

---

### PASO 5 — Cargar el código a los ESP32

Para cada módulo:

1. Abrir el archivo `.ino` correspondiente en Arduino IDE
2. Verificar/cambiar estas constantes si tu red es diferente:
   ```cpp
   const char* WIFI_SSID     = "TU_RED_WIFI";
   const char* WIFI_PASS     = "TU_CONTRASEÑA";
   const char* MQTT_BROKER   = "IP_DE_TU_LAPTOP";
   const char* MQTT_USER     = "lscc_user";
   const char* MQTT_PASSWORD = "lscc2025";
   ```
3. Seleccionar la placa correcta:
   - Módulo ambiental, residuos, KY-037: `ESP32 Dev Module`
   - Cámara: `AI Thinker ESP32-CAM`
4. Subir el sketch

**Para el ESP32-CAM**: usar adaptador FTDI (USB-serial).
Conectar GPIO0 a GND antes de encender para entrar en modo flash.
Desconectar GPIO0 de GND después de cargar y resetear.

---

### PASO 6 — Verificar que los datos se guardan en la DB

Con el dashboard corriendo y los ESP32 encendidos, abrir otra terminal:

```bash
# Desde la carpeta db/ o pasando la ruta:
cd lima_smart_fase1

# Resumen general
python db/ver_db.py

# Ver lecturas de temperatura
python db/ver_db.py temperatura

# Ver estado de contenedores
python db/ver_db.py residuos

# Ver alertas activas
python db/ver_db.py alertas

# Ver estado de dispositivos
python db/ver_db.py dispositivos
```

También puedes consultar la API directamente:
- http://localhost:5000/api/data          → Estado actual en memoria
- http://localhost:5000/api/history/temperatura?limite=20  → Historial de DB
- http://localhost:5000/api/alertas       → Alertas activas desde DB
- http://localhost:5000/api/dispositivos  → Estado de dispositivos

---

### PASO 7 — Encontrar la IP de tu laptop para los ESP32

**Windows:**
```powershell
ipconfig
```
Buscar "Dirección IPv4" de la red Wi-Fi (ej: 192.168.100.99).
Esa IP va en `MQTT_BROKER` de los sketches Arduino.

---

## Credenciales del sistema (Fase 1)

| Parámetro    | Valor       |
|---|---|
| MQTT usuario | lscc_user   |
| MQTT clave   | lscc2025    |
| Broker IP    | IP de tu laptop |
| Broker puerto| 1883        |
| DB archivo   | lscc.db     |

---

## Notas importantes

- El KY-037 **NO** va en el ESP32-CAM (sin pines libres). Usa un ESP32 genérico.
- El MQ-2 tarda **30 segundos** en calentarse. El módulo ambiental espera antes de publicar.
- Si cambias la contraseña MQTT, actualízala en: `mosquitto.conf`, `mosquitto_passwd.txt`, los 4 `.ino` y el `iniciar_dashboard.bat`.
- El archivo `lscc.db` **no** debe subirse a GitHub (contiene datos del sistema).
- Los templates y archivos static (HTML, CSS, JS) son los mismos del dashboard anterior — cópialos a la carpeta `dashboard/`.
