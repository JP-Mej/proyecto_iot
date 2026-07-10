# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Lima Smart Core City (LSCC) — IoT academic platform aligned with the ITU-T Y.2060 four-layer reference model. Four ESP32 nodes publish sensor data via MQTT to a Flask/SQLite web dashboard, which also feeds a local Bronze/Silver/Gold data pipeline uploaded to Amazon S3/Athena for future Power BI analytics.

Current version: `0.2.0-consolidacion-fase1`. Safe rollback point: `git tag v0.1.0-pre-consolidacion` / commit `54ea5af`.

```
Sensores -> ESP32 -> Wi-Fi/TCP -> MQTT (Mosquitto) -> Flask -> SQLite -> Bronze/Silver/Gold -> S3/Athena -> Power BI
```

## Running the Stack (Windows, daily startup)

Stop any pre-existing Mosquitto service, then start the project broker from `dashboard/` (CMD as administrator):

```bat
net stop mosquitto
netstat -ano | findstr :1883
"C:\Program Files\mosquitto\mosquitto.exe" -c mosquitto.conf -v
```

Start Flask in a second window from `dashboard/`:

```bat
python app.py
```

Open only `http://127.0.0.1:5000/login` (no HTTPS, no `0.0.0.0`, no IDE proxy preview). Two simultaneous brokers is the most common failure mode — Flask connects to one while ESP32s publish to the other, producing a misleading "connected but no data" state.

## First-Time Setup

```bat
cd dashboard
python -m pip install -r requirements.txt
copy .env.example .env   REM then fill in real values
python crear_db.py        REM only if lscc.db does not exist yet
```

Never run `crear_db.py` over an existing database without a backup.

There is also a `db/` folder at the repo root with older, stale copies of `crear_db.py`/`ver_db.py` (no `.env` loading, hardcoded `DB_PATH`, missing the `usuarios` table). Always use the ones under `dashboard/`, not `db/`.

## Inspecting SQLite Data

```bat
cd dashboard
python ver_db.py
python ver_db.py residuos
python ver_db.py dispositivos
python ver_db.py alertas
```

## Testing MQTT

```bat
"C:\Program Files\mosquitto\mosquitto_sub.exe" -h 127.0.0.1 -p 1883 -u lscc_user -P "<CLAVE>" -t "lscc/#" -v
"C:\Program Files\mosquitto\mosquitto_pub.exe" -h 127.0.0.1 -p 1883 -u lscc_user -P "<CLAVE>" -t "lscc/prueba" -m "hola"
```

## Data Pipeline (Bronze/Silver/Gold -> S3 -> Athena)

Scripts live at the repo root (not in `dashboard/`), run manually rather than continuously to preserve AWS credits:

```powershell
python pipeline_medallon_local.py                 # SQLite -> datalake_local/{bronze,silver,gold}
python pipeline_medallon_local.py --db dashboard/lscc.db   # explicit DB path
python subir_gold_s3.py --bucket lscc-datalake-fisi-347011900597 --layout athena --execute
python ejecutar_athena_gold.py                     # only needed when Gold table *columns* change, not just data
```

`datalake_local/` layout: `bronze/` (raw SQLite export + `backups_sqlite/`), `silver/` (cleaned/typed, dedup'd, timestamp-normalized), `gold/` (Athena/Power BI-ready CSVs: `resumen_ambiental_diario`, `residuos_por_contenedor_diario`, `sonido_eventos_diario`, `reportes_por_estado_categoria`, `alertas_por_modulo_prioridad`, `manifest`). Recommended cadence: medallion pipeline every 15–60 min, Gold upload every 30–60 min, SQLite backup daily; don't upload every camera frame — only event-linked images.

## Architecture

### `dashboard/app.py`

Single-file Flask app (~1700 lines). Key sections in order:
- **Config** — reads `dashboard/.env` via `python-dotenv`. `FLASK_SECRET_KEY` is required at startup (raises if missing).
- **Auth** — login/logout/registro, single-session-per-user token stored in `usuarios.active_session_token` (a second login invalidates the first; the old session gets redirected with `sesion_reemplazada`), brute-force rate-limit in memory (`intentos_login`, keyed by IP + window), CSRF token via `session["csrf_token"]` validated on all POSTs.
- **DB helpers** — `get_db()` opens SQLite with `mode=rw` (prevents accidental file creation). Tables: `usuarios`, `reportes_ciudadanos`, `lecturas_ambientales`, `lecturas_residuos`, `lecturas_sonido`, `imagenes_meta`, `eventos_alerta`, `estado_dispositivos`, `dispositivos`, `rutas_recoleccion`. Table creation/migration happens defensively at import time (`crear_tablas_auth_si_no_existen`, `migrar_reportes_publicos_si_necesario`, `crear_tabla_rutas_recoleccion_si_no_existe`), so schema additions should stay additive rather than destructive.
- **`estado` dict** — shared in-memory state. Updated by the MQTT thread, read by `/api/data`. Protected by `threading.Lock()` (`lock`).
- **`ultima_vez_modulos`** — `dict[device_id → float]` tracking per-device Unix timestamps. Set to `time.time()` on normal messages; set to `0` on MQTT Last Will (`status: "offline"`) so the frontend detects disconnect immediately.
- **MQTT thread** (`on_connect`/`on_message`/`iniciar_mqtt`) — dispatches by topic prefix, updates `estado` and writes to SQLite. Runs in a daemon thread; never touches Flask routes directly.
- **Routes** — see below.

### Routing: public vs. authenticated split

`/` renders `inicio_publico.html` for anonymous visitors and only calls `index_autenticado()` (session-gated) once a valid `user_id`+`session_token` exist. This public/authenticated fork is the main structural pattern to preserve when adding pages:

- **Public (no login)**: `/` (`inicio_publico.html`), `/estado-urbano` (aggregated city-wide status via `resumen_urbano_publico()`, no raw device data), `/nuevo-reporte` when unauthenticated (renders `nuevo_reporte_publico.html`, rate-limited per IP via `limite_reporte_publico_superado`, issues a `codigo_seguimiento` like `LSCC-2026-XXXXXXXXXXXX` instead of requiring an account), `/consulta-reporte` (look up a public report by tracking code + email).
- **Role `usuario` (citizen account)**: `index.html`, `/nuevo-reporte` (authenticated variant), `/reportes` (own reports only).
- **Role `trabajador`/`admin` (staff)**: `dashboard_principal.html` plus the technical dashboards — `/vigilancia`, `/ambiente`, `/residuos`, `/sonido`, `/ruta-recoleccion`, `/registro-tecnico`, `/reportes` (all reports, can update status). These all funnel through `render_dashboard_tecnico(template)` to avoid duplicating the shared context (`username`, `rol`).
- **Role `admin` only**: `/usuarios` (create/list staff accounts; public self-registration via `/registro` only ever creates `usuario` accounts).

Templates use three base layouts: `base_public.html`, `base_citizen.html`, `base_dashboard.html` — match new pages to the base for their audience rather than starting from scratch.

### `/ruta-recoleccion` (collection route optimization)

A staff-only feature distinct from the raw sensor dashboards: `/api/ruta-recoleccion-datos` reads the latest `lecturas_residuos` row per sensor (1–4, labeled A–D) and flags each as `reciente` if updated within 120s. `/api/ruta-recoleccion-guardar` persists a computed route (`orden_tachos`, `incluidos`/`omitidos`, estimated distance, snapshotted fill levels) into `rutas_recoleccion` after strict server-side validation — every list must be a permutation/partition of exactly `{A,B,C,D}`, distance clamped 0–10000, percentages clamped 0–100. Treat this validation as load-bearing, not boilerplate, since the payload is client-computed. Frontend logic lives in `dashboard/static/mapa_maqueta.js`, `ruta_recoleccion.js`, `ruta_resumen.js`.

### `dashboard/static/app.js`

Polls `/api/data` every 2 seconds. Key patterns:
- **`nodoOnline(ultima_vez, deviceId, maxSeg)`** — returns `true` only if `Date.now()/1000 - ultima_vez[deviceId] < maxSeg`. Timeouts: Ambiental 60s, Residuos 60s, Sonido 30s, Camera 120s.
- Each `actualizarNodo*` function reads `data.ultima_vez_modulos` for its `deviceId` to decide online/offline before rendering values.
- When a node is offline: metrics show `--`, bars clear to 0%, chips go grey, node dot loses the `online` class.
- `data.ultima_actualizacion` is a global timestamp (any MQTT message). Use `data.ultima_vez_modulos["DEVICE_ID"]` for per-node "Última lectura" times.

### MQTT Topics

```
lscc/ambiental/temperatura   ESP32_AIRE_01
lscc/ambiental/humedad       ESP32_AIRE_01
lscc/ambiental/presion       ESP32_AIRE_01
lscc/ambiental/gas           ESP32_AIRE_01
lscc/residuos/nivel          ESP32_RESIDUOS_01  (sensor_id 1–3 active; N_SENS=3; tacho D used by ruta-recoleccion UI stays empty)
lscc/vigilancia/sonido       ESP32_KY037_01
lscc/vigilancia/imagen       ESP32_CAM_01       (binary JPEG)
lscc/vigilancia/imagen_meta  ESP32_CAM_01
lscc/sistema/status          all devices (heartbeat + MQTT Last Will)
```

The device-status payload contract (`lscc/sistema/status`) is formally defined in `schemas/estado-dispositivo.schema.json`: requires `schema_version` (const `"1.0"`), `device_id` (pattern `^ESP32_[A-Z0-9_]+$`), `modulo` (enum incl. `ambiental`, `calidad_aire`, `residuos`, `vigilancia`, `videovigilancia`), `status` (enum `online`/`offline`/`sin_datos`/`error`); optional `firmware_version`, `uptime_ms`, `rssi_dbm`, `ip`.

### ESP32 Firmware (`arduino/`)

Each sketch has a `secrets.h` (not in Git — copy from `secrets.h.example`). Credentials must match `dashboard/.env` and `mosquitto_passwd.txt`. All sketches register an MQTT Last Will to `lscc/sistema/status` with `status: "offline"`; when the broker delivers this will, `app.py` sets `ultima_vez_modulos[device_id] = 0`.

- **CAMARA** — AI Thinker ESP32-CAM; MJPEG stream on `http://<ip>/stream`; MQTT heartbeat every 30s.
- **MQ2_BMP280_DHT22** — Ambiental node; publishes all four variables every 5s.
- **HCR_04** — Residuos node; `N_SENS=3` (tachos 1–3 only). A `distancia_cm = -1` reading means the HC-SR04 got no echo — check power, common ground, Trig/Echo wiring, the Echo voltage divider, and sensor placement before assuming a software bug.
- **KY037** — Sound node; publishes every 3s.

Boards using WiFiManager can retain a stale broker address in memory; if a re-flashed board doesn't pick up a new broker IP, use the config-reset button and redo the portal (see `actualizar_broker_ip.ps1` for bulk IP updates).

### Roles

Three user roles enforced in Flask via decorators (`login_requerido`, `admin_requerido`, `trabajador_o_admin_requerido`, `usuario_requerido`):
- `usuario` — citizens; can submit and view only their own reports.
- `trabajador` — staff; can view all reports, update status, and use the technical dashboards + ruta de recolección.
- `admin` — all of the above plus user management (`/usuarios`).

Public self-registration (`/registro`) creates `usuario` accounts only. Admins create `trabajador`/`admin` accounts via `/usuarios`.

## Secrets & Config Files

| File | Purpose |
|------|---------|
| `dashboard/.env` | Flask secret, admin password, MQTT credentials/TLS options, DB path, rate-limit tuning |
| `arduino/*/secrets.h` | WiFi AP password, MQTT credentials per sketch |
| `dashboard/mosquitto_passwd.txt` | Broker user/password file (generate with `mosquitto_passwd`) |
| `dashboard/mosquitto-secure.conf.example` / `mosquitto.acl.example` | TLS/ACL profile — prepared but not yet activated |

All are git-ignored. Use the `.example` counterparts as templates.

## Diagnostics

If the dashboard doesn't update despite Mosquitto receiving messages:
1. `netstat -ano | findstr :1883` — confirm only one process is LISTENING.
2. Look for `Sending PUBLISH to dashboard_lscc_fase1` in Mosquitto output.
3. Subscribe manually to `lscc/#` to inspect raw JSON.
4. Two simultaneous brokers (Windows service + project) will split traffic and produce a misleading "connected but no data" state.

If ESP32 publishes but SQLite doesn't change: check the `device_id` is registered in the `dispositivos` table, the topic matches exactly what `app.py` expects, the JSON is valid, and watch the Flask console for `[DB] Error ...` lines.

## Known Pending Items

- Resolve the definitive tacho count (firmware has 3 HC-SR04, UI/route-planning has 4 slots).
- Activate MQTT/TLS with real certificates (profile exists as `.example` only).
- Per-device MQTT users/ACLs (currently shared credentials).
- Separate MQTT ingestion from the web process.
- Signed OTA, audit logging, monitoring.
- Automate S3/Athena upload cadence and finish Power BI dashboards (ODBC DSN `LSCC_Athena`, Import mode).

## Further Documentation

- `documentacion/ARQUITECTURA_Y2060.md` — Y.2060 layer mapping and cross-cutting capabilities.
- `documentacion/GUIA_OPERACION_LOCAL.md` — detailed startup/validation/troubleshooting sequence.
- `documentacion/PIPELINE_MEDALLON_LOCAL.md` — Bronze/Silver/Gold layer details and upload cadence.
- `documentacion/ATHENA_GOLD_POWERBI.md` — Athena setup and Power BI connection.
- `documentacion/SUBIDA_GOLD_AWS_S3.md` — S3 upload script usage.
