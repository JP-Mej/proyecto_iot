"""
============================================================
LIMA SMART CORE CITY — Dashboard Fase 1
Flask + paho-mqtt + SQLite

Cambios respecto a la versión anterior:
 Autenticación MQTT (usuario + contraseña)
  Persistencia en SQLite (lscc.db)
  Historial cargado desde la DB al iniciar
  Antirrebote de alertas (no duplica cada 5 s)
   API /api/history para consultar histórico
   Registro de imágenes con metadata en DB
  Estado de dispositivos persistido
============================================================
"""

from flask import Flask, render_template, jsonify, send_file, request, redirect, url_for, session
from datetime import datetime
from collections import defaultdict, deque
import paho.mqtt.client as mqtt
import json
import time
import os
import threading
import sqlite3
import secrets
import ssl
import re
from functools import wraps
from pathlib import Path
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
from PIL import Image, UnidentifiedImageError

# ============================================================
# CONFIGURACIÓN
# ============================================================
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

MQTT_BROKER   = os.environ.get("MQTT_BROKER",   "127.0.0.1")
MQTT_PORT     = int(os.environ.get("MQTT_PORT", "1883"))
MQTT_USER     = os.environ.get("MQTT_USER", "")
MQTT_PASSWORD = os.environ.get("MQTT_PASSWORD", "")
MQTT_TLS      = os.environ.get("MQTT_TLS", "false").lower() == "true"
MQTT_CA_CERT  = os.environ.get("MQTT_CA_CERT", "")
MQTT_CERTFILE = os.environ.get("MQTT_CERTFILE", "")
MQTT_KEYFILE  = os.environ.get("MQTT_KEYFILE", "")
MQTT_KEEPALIVE = int(os.environ.get("MQTT_KEEPALIVE", "60"))
DEVICE_OFFLINE_SECONDS = int(os.environ.get("DEVICE_OFFLINE_SECONDS", "30"))

DB_PATH_CONFIG = Path(os.environ.get("LSCC_DB", "lscc.db"))
DB_PATH = DB_PATH_CONFIG if DB_PATH_CONFIG.is_absolute() else BASE_DIR / DB_PATH_CONFIG

IMG_DIR       = BASE_DIR / "imagenes"
IMG_DIR.mkdir(exist_ok=True)
LAST_IMAGE    = IMG_DIR / "ultima_imagen.jpg"

REPORTES_DIR = BASE_DIR / "reportes_adjuntos"
REPORTES_DIR.mkdir(exist_ok=True)
EXTENSIONES_PERMITIDAS = {"png", "jpg", "jpeg", "webp"}
MAX_UPLOAD_BYTES = int(os.environ.get("MAX_UPLOAD_BYTES", str(5 * 1024 * 1024)))

# Tiempo mínimo entre dos alertas del mismo tipo (segundos) — antirrebote
ALERTA_COOLDOWN = 60

# ============================================================
# APP FLASK
# ============================================================
app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY")
if not app.secret_key:
    raise RuntimeError("Falta FLASK_SECRET_KEY. Configúrala en dashboard/.env")
app.config.update(
    MAX_CONTENT_LENGTH=MAX_UPLOAD_BYTES,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("SESSION_COOKIE_SECURE", "false").lower() == "true",
)

ADMIN_INITIAL_PASSWORD = os.environ.get("ADMIN_INITIAL_PASSWORD")
LOGIN_MAX_INTENTOS = int(os.environ.get("LOGIN_MAX_INTENTOS", "5"))
LOGIN_VENTANA_SEGUNDOS = int(os.environ.get("LOGIN_VENTANA_SEGUNDOS", "900"))
intentos_login = defaultdict(deque)
intentos_login_lock = threading.Lock()
REPORTES_PUBLICOS_MAX = int(os.environ.get("REPORTES_PUBLICOS_MAX", "5"))
REPORTES_PUBLICOS_VENTANA = int(os.environ.get("REPORTES_PUBLICOS_VENTANA", "1800"))
reportes_publicos_ip = defaultdict(deque)
reportes_publicos_lock = threading.Lock()
CODIGO_SEGUIMIENTO_RE = re.compile(r"^LSCC-\d{4}-[A-F0-9]{12}$")
CORREO_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def csrf_token():
    token = session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    return token


app.jinja_env.globals["csrf_token"] = csrf_token


@app.before_request
def validar_csrf():
    if request.method == "POST":
        recibido = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
        esperado = session.get("csrf_token")
        if not esperado or not recibido or not secrets.compare_digest(esperado, recibido):
            return "Solicitud inválida o expirada. Recarga la página e inténtalo nuevamente.", 400


@app.errorhandler(413)
def archivo_demasiado_grande(_error):
    return "La imagen supera el tamaño máximo permitido.", 413


@app.after_request
def agregar_cabeceras_seguridad(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; script-src 'self' https://cdn.jsdelivr.net; "
        "style-src 'self'; img-src 'self' data: http:; connect-src 'self'"
    )
    return response



# ============================================================
# AUTENTICACIÓN — Login + sesión única por usuario
# ============================================================
def crear_tablas_auth_si_no_existen():
    """Crea la tabla de usuarios si no existe y registra un admin inicial."""
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS usuarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                rol TEXT NOT NULL DEFAULT 'usuario',
                active_session_token TEXT,
                ultimo_login TEXT,
                creado_en TEXT NOT NULL DEFAULT (datetime('now','localtime'))
            );
        """)

        existe = conn.execute(
            "SELECT id, password_hash FROM usuarios WHERE username = ?", ("admin",)
        ).fetchone()

        if not existe:
            if not ADMIN_INITIAL_PASSWORD:
                raise RuntimeError("Falta ADMIN_INITIAL_PASSWORD para crear el administrador inicial")
            conn.execute("""
                INSERT INTO usuarios (username, password_hash, rol)
                VALUES (?, ?, ?)
            """, ("admin", generate_password_hash(ADMIN_INITIAL_PASSWORD), "admin"))
        elif (ADMIN_INITIAL_PASSWORD
              and ADMIN_INITIAL_PASSWORD != "admin123"
              and check_password_hash(existe["password_hash"], "admin123")):
            conn.execute("""
                UPDATE usuarios
                SET password_hash = ?, active_session_token = NULL
                WHERE id = ?
            """, (generate_password_hash(ADMIN_INITIAL_PASSWORD), existe["id"]))
            app.logger.warning("Se reemplazó la contraseña inicial insegura del administrador")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS reportes_ciudadanos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                usuario_id INTEGER,
                categoria TEXT NOT NULL CHECK(categoria IN ('ambiental','residuos','vigilancia')),
                titulo TEXT NOT NULL,
                ubicacion TEXT NOT NULL,
                descripcion TEXT NOT NULL,
                urgencia TEXT NOT NULL DEFAULT 'media' CHECK(urgencia IN ('baja','media','alta')),
                estado TEXT NOT NULL DEFAULT 'pendiente' CHECK(estado IN ('pendiente','en_revision','atendido','rechazado')),
                observacion_admin TEXT,
                imagen TEXT,
                creado_en TEXT NOT NULL DEFAULT (datetime('now','localtime')),
                actualizado_en TEXT,
                codigo_seguimiento TEXT,
                correo_contacto TEXT,
                origen_reporte TEXT NOT NULL DEFAULT 'cuenta',
                permite_consulta_publica INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY(usuario_id) REFERENCES usuarios(id)
            );
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_reportes_estado
            ON reportes_ciudadanos(estado, creado_en DESC);
        """)

    migrar_reportes_publicos_si_necesario()
    crear_tabla_rutas_recoleccion_si_no_existe()


def migrar_reportes_publicos_si_necesario():
    """Migra reportes de forma transaccional e idempotente, conservando los existentes."""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    try:
        columnas = {r[1]: r for r in conn.execute("PRAGMA table_info(reportes_ciudadanos)")}
        necesita_recrear = bool(columnas.get("usuario_id") and columnas["usuario_id"][3])
        faltantes = {"codigo_seguimiento", "correo_contacto", "origen_reporte", "permite_consulta_publica"} - columnas.keys()
        if necesita_recrear:
            conn.execute("PRAGMA foreign_keys = OFF")
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("ALTER TABLE reportes_ciudadanos RENAME TO reportes_ciudadanos_anterior")
            conn.execute("""
                CREATE TABLE reportes_ciudadanos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    usuario_id INTEGER,
                    categoria TEXT NOT NULL CHECK(categoria IN ('ambiental','residuos','vigilancia')),
                    titulo TEXT NOT NULL,
                    ubicacion TEXT NOT NULL,
                    descripcion TEXT NOT NULL,
                    urgencia TEXT NOT NULL DEFAULT 'media' CHECK(urgencia IN ('baja','media','alta')),
                    estado TEXT NOT NULL DEFAULT 'pendiente' CHECK(estado IN ('pendiente','en_revision','atendido','rechazado')),
                    observacion_admin TEXT,
                    imagen TEXT,
                    creado_en TEXT NOT NULL DEFAULT (datetime('now','localtime')),
                    actualizado_en TEXT,
                    codigo_seguimiento TEXT,
                    correo_contacto TEXT,
                    origen_reporte TEXT NOT NULL DEFAULT 'cuenta',
                    permite_consulta_publica INTEGER NOT NULL DEFAULT 0,
                    FOREIGN KEY(usuario_id) REFERENCES usuarios(id)
                )
            """)
            conn.execute("""
                INSERT INTO reportes_ciudadanos
                    (id, usuario_id, categoria, titulo, ubicacion, descripcion, urgencia,
                     estado, observacion_admin, imagen, creado_en, actualizado_en,
                     origen_reporte, permite_consulta_publica)
                SELECT id, usuario_id, categoria, titulo, ubicacion, descripcion, urgencia,
                       estado, observacion_admin, imagen, creado_en, actualizado_en,
                       'cuenta', 0
                FROM reportes_ciudadanos_anterior
            """)
            conn.execute("DROP TABLE reportes_ciudadanos_anterior")
            conn.commit()
        elif faltantes:
            conn.execute("BEGIN IMMEDIATE")
            if "codigo_seguimiento" in faltantes: conn.execute("ALTER TABLE reportes_ciudadanos ADD COLUMN codigo_seguimiento TEXT")
            if "correo_contacto" in faltantes: conn.execute("ALTER TABLE reportes_ciudadanos ADD COLUMN correo_contacto TEXT")
            if "origen_reporte" in faltantes: conn.execute("ALTER TABLE reportes_ciudadanos ADD COLUMN origen_reporte TEXT NOT NULL DEFAULT 'cuenta'")
            if "permite_consulta_publica" in faltantes: conn.execute("ALTER TABLE reportes_ciudadanos ADD COLUMN permite_consulta_publica INTEGER NOT NULL DEFAULT 0")
            conn.commit()
        conn.execute("CREATE INDEX IF NOT EXISTS idx_reportes_estado ON reportes_ciudadanos(estado, creado_en DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_reportes_usuario ON reportes_ciudadanos(usuario_id, creado_en DESC)")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_reportes_codigo ON reportes_ciudadanos(codigo_seguimiento) WHERE codigo_seguimiento IS NOT NULL")
        conn.commit()
        errores_fk = conn.execute("PRAGMA foreign_key_check").fetchall()
        if errores_fk:
            raise RuntimeError(f"La migración dejó referencias inválidas: {errores_fk}")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def crear_tabla_rutas_recoleccion_si_no_existe():
    """Persistencia aditiva para recorridos generados manualmente."""
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS rutas_recoleccion (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha_generacion TEXT NOT NULL DEFAULT (datetime('now','localtime')),
                orden_tachos TEXT NOT NULL,
                tachos_incluidos TEXT NOT NULL,
                tachos_omitidos TEXT NOT NULL,
                distancia_estimada REAL NOT NULL DEFAULT 0,
                niveles_analizados TEXT NOT NULL,
                ultima_lectura_residuos TEXT,
                desactualizada INTEGER NOT NULL DEFAULT 0 CHECK(desactualizada IN (0,1))
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_rutas_recoleccion_fecha
            ON rutas_recoleccion(fecha_generacion DESC)
        """)


def obtener_ultima_ruta_recoleccion():
    with get_db() as conn:
        row = conn.execute("""
            SELECT * FROM rutas_recoleccion ORDER BY id DESC LIMIT 1
        """).fetchone()
        ultima_lectura = conn.execute(
            "SELECT MAX(timestamp) AS ultima FROM lecturas_residuos WHERE sensor_id BETWEEN 1 AND 4"
        ).fetchone()["ultima"]
        if not row:
            return None
        ruta = dict(row)
        desactualizada = bool(
            ultima_lectura and ruta.get("ultima_lectura_residuos")
            and ultima_lectura > ruta["ultima_lectura_residuos"]
        )
        if desactualizada and not ruta["desactualizada"]:
            conn.execute("UPDATE rutas_recoleccion SET desactualizada = 1 WHERE id = ?", (ruta["id"],))
        ruta["desactualizada"] = desactualizada or bool(ruta["desactualizada"])
    for campo in ("orden_tachos", "tachos_incluidos", "tachos_omitidos", "niveles_analizados"):
        ruta[campo] = json.loads(ruta[campo])
    return ruta


def login_requerido(func):
    """Protege rutas y expulsa sesiones anteriores si otro login reemplazó el token."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        user_id = session.get("user_id")
        token = session.get("session_token")

        if not user_id or not token:
            if request.path.startswith("/api/"):
                return jsonify({"error": "no_autenticado", "redirect": url_for("login")}), 401
            return redirect(url_for("login"))

        with get_db() as conn:
            user = conn.execute(
                "SELECT id, rol, active_session_token FROM usuarios WHERE id = ?",
                (user_id,)
            ).fetchone()

        if not user or user["active_session_token"] != token:
            session.clear()
            if request.path.startswith("/api/"):
                return jsonify({"error": "sesion_reemplazada", "redirect": url_for("login", mensaje="sesion_reemplazada")}), 401
            return redirect(url_for("login", mensaje="sesion_reemplazada"))

        session["rol"] = user["rol"]
        return func(*args, **kwargs)
    return wrapper


def admin_requerido(func):
    """Permite el acceso solo a usuarios con rol administrador."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        if session.get("rol") != "admin":
            return redirect(url_for("index"))
        return func(*args, **kwargs)
    return wrapper


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        clave_intento = (request.remote_addr or "desconocida", username.casefold())
        ahora = time.time()

        with intentos_login_lock:
            intentos = intentos_login[clave_intento]
            while intentos and ahora - intentos[0] > LOGIN_VENTANA_SEGUNDOS:
                intentos.popleft()
            if len(intentos) >= LOGIN_MAX_INTENTOS:
                return render_template(
                    "login.html",
                    error="Demasiados intentos. Espera unos minutos antes de volver a intentar."
                ), 429

        with get_db() as conn:
            user = conn.execute(
                "SELECT * FROM usuarios WHERE username = ?",
                (username,)
            ).fetchone()

            if user and check_password_hash(user["password_hash"], password):
                with intentos_login_lock:
                    intentos_login.pop(clave_intento, None)
                nuevo_token = secrets.token_urlsafe(32)

                # Aquí ocurre la sesión única:
                # si el usuario ya estaba conectado en otro navegador/dispositivo,
                # este token reemplaza al anterior y la sesión vieja queda inválida.
                conn.execute("""
                    UPDATE usuarios
                    SET active_session_token = ?, ultimo_login = datetime('now','localtime')
                    WHERE id = ?
                """, (nuevo_token, user["id"]))

                session.clear()
                session["user_id"] = user["id"]
                session["username"] = user["username"]
                session["rol"] = user["rol"]
                session["session_token"] = nuevo_token

                return redirect(url_for("index"))

        with intentos_login_lock:
            intentos_login[clave_intento].append(ahora)
        return render_template("login.html", error="Usuario o contraseña incorrectos")

    mensaje = request.args.get("mensaje")
    return render_template("login.html", mensaje=mensaje)


@app.route("/logout", methods=["POST"])
@login_requerido
def logout():
    user_id = session.get("user_id")
    token = session.get("session_token")

    if user_id and token:
        with get_db() as conn:
            conn.execute("""
                UPDATE usuarios
                SET active_session_token = NULL
                WHERE id = ? AND active_session_token = ?
            """, (user_id, token))

    session.clear()
    return redirect(url_for("index"))


@app.route("/registro", methods=["GET", "POST"])
def registro():
    """Registro público solo para ciudadanos/usuarios que enviarán reportes."""
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        confirmar = request.form.get("confirmar", "")

        if not username or not password:
            return render_template("registro.html", error="Completa usuario y contraseña.")
        if len(username) < 3 or len(username) > 50:
            return render_template("registro.html", error="El usuario debe tener entre 3 y 50 caracteres.")
        if len(password) < 10:
            return render_template("registro.html", error="La contraseña debe tener al menos 10 caracteres.")
        if password != confirmar:
            return render_template("registro.html", error="Las contraseñas no coinciden.")

        try:
            with get_db() as conn:
                conn.execute("""
                    INSERT INTO usuarios (username, password_hash, rol)
                    VALUES (?, ?, 'usuario')
                """, (username, generate_password_hash(password)))
            return redirect(url_for("login", mensaje="usuario_creado"))
        except sqlite3.IntegrityError:
            return render_template("registro.html", error="Ese usuario ya existe. Elige otro nombre.")
        except Exception:
            app.logger.exception("No se pudo registrar el usuario")
            return render_template("registro.html", error="No se pudo registrar el usuario. Inténtalo nuevamente.")

    return render_template("registro.html")


def trabajador_o_admin_requerido(func):
    """Permite acceso al personal interno: administradores y trabajadores."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        if session.get("rol") not in ("admin", "trabajador"):
            return redirect(url_for("index"))
        return func(*args, **kwargs)
    return wrapper


def usuario_requerido(func):
    """Permite reportar solo a usuarios ciudadanos."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        if session.get("rol") != "usuario":
            return redirect(url_for("reportes"))
        return func(*args, **kwargs)
    return wrapper


# ============================================================
# BASE DE DATOS — helpers
# ============================================================
def get_db():
    """Abre una conexión a SQLite con row_factory para acceso por nombre."""
    # mode=rw evita crear accidentalmente una base vacía si la ruta es incorrecta.
    db_uri = DB_PATH.resolve().as_uri() + "?mode=rw"
    conn = sqlite3.connect(db_uri, uri=True, timeout=5)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA busy_timeout = 5000;")
    return conn


def db_insert_ambiental(device_id, sensor, variable, valor, unidad,
                         estado, nivel=None, valor_raw=None, voltaje=None):
    try:
        with get_db() as conn:
            conn.execute("""
                INSERT INTO lecturas_ambientales
                  (device_id, sensor, variable, valor, valor_raw, voltaje,
                   unidad, nivel, estado)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (device_id, sensor, variable,
                  valor, valor_raw, voltaje,
                  unidad, nivel, estado))
    except Exception as e:
        print(f"[DB] Error ambiental: {e}")


def db_insert_residuos(device_id, sensor_id, distancia, porcentaje, nivel):
    try:
        with get_db() as conn:
            conn.execute("""
                INSERT INTO lecturas_residuos
                  (device_id, sensor_id, distancia_cm, porcentaje_llenado, nivel)
                VALUES (?, ?, ?, ?, ?)
            """, (device_id, sensor_id, distancia, porcentaje, nivel))
    except Exception as e:
        print(f"[DB] Error residuos: {e}")


def db_insert_sonido(device_id, raw, voltaje, porcentaje, nivel, evento):
    try:
        with get_db() as conn:
            conn.execute("""
                INSERT INTO lecturas_sonido
                  (device_id, valor_raw, voltaje, porcentaje, nivel, evento)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (device_id, raw, voltaje, porcentaje, nivel, evento))
    except Exception as e:
        print(f"[DB] Error sonido: {e}")


def db_insert_imagen_meta(device_id, width, height, size_bytes, trigger, ruta):
    try:
        with get_db() as conn:
            conn.execute("""
                INSERT INTO imagenes_meta
                  (device_id, width, height, size_bytes, trigger_tipo, ruta_archivo)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (device_id, width, height, size_bytes, trigger, ruta))
    except Exception as e:
        print(f"[DB] Error imagen_meta: {e}")


def db_insert_alerta(device_id, modulo, tipo, descripcion, prioridad):
    """Inserta una alerta respetando el antirrebote por tipo."""
    try:
        with get_db() as conn:
            # Verificar si ya existe una alerta activa reciente del mismo tipo
            row = conn.execute("""
                SELECT timestamp FROM eventos_alerta
                WHERE device_id = ? AND tipo_alerta = ? AND estado = 'activa'
                ORDER BY timestamp DESC LIMIT 1
            """, (device_id, tipo)).fetchone()

            if row:
                ts_str = row["timestamp"]
                try:
                    ts = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
                    segundos = (datetime.now() - ts).total_seconds()
                    if segundos < ALERTA_COOLDOWN:
                        return  # Antirrebote: no duplicar
                except Exception:
                    pass

            conn.execute("""
                INSERT INTO eventos_alerta
                  (device_id, modulo, tipo_alerta, descripcion, prioridad)
                VALUES (?, ?, ?, ?, ?)
            """, (device_id, modulo, tipo, descripcion, prioridad))
    except Exception as e:
        print(f"[DB] Error alerta: {e}")


def db_insert_estado(device_id, modulo, status, detalle=None):
    """Registra el último heartbeat del dispositivo."""
    try:
        with get_db() as conn:
            conn.execute("""
                INSERT INTO estado_dispositivos
                  (device_id, modulo, status, detalle)
                VALUES (?, ?, ?, ?)
            """, (device_id, modulo, status, detalle))
            conn.execute("""
                UPDATE dispositivos SET ultima_vez = datetime('now','localtime')
                WHERE device_id = ?
            """, (device_id,))
    except Exception as e:
        print(f"[DB] Error estado: {e}")


def db_dispositivo_registrado(device_id):
    conn = None
    try:
        conn = get_db()
        result = conn.execute(
            "SELECT 1 FROM dispositivos WHERE device_id = ? AND activo = 1",
            (device_id,)
        ).fetchone() is not None
        return result
    except Exception:
        return False
    finally:
        if conn:
            conn.close()


def db_cargar_historial(variable, limite=30):
    """Carga los últimos N puntos de una variable desde la DB al iniciar."""
    try:
        with get_db() as conn:
            rows = conn.execute("""
                SELECT timestamp, valor FROM lecturas_ambientales
                WHERE variable = ? AND estado = 'ok'
                ORDER BY timestamp DESC LIMIT ?
            """, (variable, limite)).fetchall()
        return [{"t": r["timestamp"][-8:], "v": r["valor"]}
                for r in reversed(rows)]
    except Exception:
        return []


def db_cargar_ultimo_ambiental():
    """Carga el último valor conocido de cada variable ambiental desde la DB."""
    resultado = {"temperatura": None, "humedad": None, "presion": None, "gas": None}
    try:
        with get_db() as conn:
            for var in ["temperatura", "humedad", "presion"]:
                row = conn.execute("""
                    SELECT valor FROM lecturas_ambientales
                    WHERE variable = ? AND estado = 'ok'
                    ORDER BY timestamp DESC LIMIT 1
                """, (var,)).fetchone()
                if row:
                    resultado[var] = row["valor"]
            row = conn.execute("""
                SELECT valor, valor_raw, voltaje, nivel
                FROM lecturas_ambientales
                WHERE variable = 'gas' AND estado = 'ok'
                ORDER BY timestamp DESC LIMIT 1
            """).fetchone()
            if row:
                resultado["gas"] = {
                    "value_raw": row["valor_raw"],
                    "voltage":   row["voltaje"],
                    "nivel":     row["nivel"],
                    "estado":    "ok",
                }
    except Exception:
        pass
    return resultado


def db_cargar_historial_residuos(sensor_id, limite=30):
    try:
        with get_db() as conn:
            rows = conn.execute("""
                SELECT timestamp, porcentaje_llenado FROM lecturas_residuos
                WHERE sensor_id = ?
                ORDER BY timestamp DESC LIMIT ?
            """, (sensor_id, limite)).fetchall()
        return [{"t": r["timestamp"][-8:], "v": r["porcentaje_llenado"]}
                for r in reversed(rows)]
    except Exception:
        return []


def db_cargar_ultimo_estado_tachos():
    """Carga el último registro de cada tacho desde la DB para mostrar al iniciar."""
    tachos = {str(i): nuevo_tacho(i) for i in range(1, 5)}
    try:
        with get_db() as conn:
            for sid in range(1, 5):
                row = conn.execute("""
                    SELECT device_id, sensor_id, distancia_cm, porcentaje_llenado,
                           nivel, timestamp
                    FROM lecturas_residuos
                    WHERE sensor_id = ?
                    ORDER BY timestamp DESC LIMIT 1
                """, (sid,)).fetchone()
                if row:
                    tachos[str(sid)].update({
                        "sensor_id":          row["sensor_id"],
                        "distancia_cm":       row["distancia_cm"],
                        "porcentaje_llenado": row["porcentaje_llenado"],
                        "nivel":              row["nivel"],
                        "estado":             "ok" if row["distancia_cm"] and row["distancia_cm"] >= 0 else "sin_datos",
                        "ultima_actualizacion": row["timestamp"][-8:] if row["timestamp"] else None,
                        "device_id":          row["device_id"],
                    })
    except Exception:
        pass
    return tachos


def db_cargar_historial_sonido(limite=30):
    try:
        with get_db() as conn:
            rows = conn.execute("""
                SELECT timestamp, porcentaje FROM lecturas_sonido
                ORDER BY timestamp DESC LIMIT ?
            """, (limite,)).fetchall()
        return [{"t": r["timestamp"][-8:], "v": r["porcentaje"]}
                for r in reversed(rows) if r["porcentaje"] is not None]
    except Exception:
        return []


# ============================================================
# ESTADO EN MEMORIA (idéntico al dashboard anterior + DB)
# ============================================================
def nuevo_tacho(sensor_id):
    return {
        "sensor_id": sensor_id, "distancia_cm": None,
        "porcentaje_llenado": None, "nivel": None,
        "estado": None, "ultima_actualizacion": None, "device_id": None,
    }


# Cargar historial inicial desde la DB (si ya existe)
estado = {
    "conexion_mqtt":      "desconectado",
    "ultimo_mensaje":     None,
    "ultima_actualizacion": None,
    "device_id":          None,
    "ambiental": db_cargar_ultimo_ambiental(),
    "residuos": {"tachos": db_cargar_ultimo_estado_tachos()},
    "vigilancia": {
        "sonido": None, "imagen_meta": None,
        "imagen_recibida": False, "imagen_timestamp": None,
        "cam_stream_url": None,
    },
    "sistema": {"status": None},
    "ultima_vez_modulos": {},
    "historial": {
        "temperatura":  db_cargar_historial("temperatura"),
        "humedad":      db_cargar_historial("humedad"),
        "presion":      db_cargar_historial("presion"),
        "gas":          db_cargar_historial("gas"),
        "sonido":       db_cargar_historial_sonido(),
        **{f"residuos_{i}": db_cargar_historial_residuos(i) for i in range(1, 5)},
    },
    "log": [],
}

lock = threading.Lock()

# ============================================================
# HELPERS
# ============================================================
def agregar_log(texto):
    with lock:
        hora = time.strftime("%H:%M:%S")
        estado["log"].insert(0, f"[{hora}] {texto}")
        estado["log"] = estado["log"][:25]


def agregar_historial(nombre, valor):
    if valor is None:
        return
    try:
        valor = float(valor)
    except (TypeError, ValueError):
        return
    punto = {"t": time.strftime("%H:%M:%S"), "v": round(valor, 2)}
    estado["historial"].setdefault(nombre, [])
    estado["historial"][nombre].append(punto)
    estado["historial"][nombre] = estado["historial"][nombre][-30:]


def parse_json(payload_bytes):
    try:
        return json.loads(payload_bytes.decode("utf-8"))
    except Exception:
        return None


def get_num(data, *keys):
    for key in keys:
        v = data.get(key)
        if v is not None:
            return v
    return None


def archivo_permitido(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in EXTENSIONES_PERMITIDAS


def validar_imagen_subida(archivo):
    """Valida el contenido real de la imagen, no solo su extensión."""
    if not archivo_permitido(archivo.filename):
        return None
    try:
        imagen = Image.open(archivo.stream)
        formato = (imagen.format or "").lower()
        imagen.verify()
        archivo.stream.seek(0)
    except (UnidentifiedImageError, OSError, ValueError):
        archivo.stream.seek(0)
        return None
    return {"jpeg": "jpg", "png": "png", "webp": "webp"}.get(formato)


def obtener_contadores_reportes(solo_usuario_id=None):
    where = ""
    params = []
    if solo_usuario_id is not None:
        where = "WHERE usuario_id = ?"
        params.append(solo_usuario_id)

    with get_db() as conn:
        rows = conn.execute(f"""
            SELECT estado, COUNT(*) AS total
            FROM reportes_ciudadanos
            {where}
            GROUP BY estado
        """, params).fetchall()

    contadores = {"pendiente": 0, "en_revision": 0, "atendido": 0, "rechazado": 0}
    for r in rows:
        contadores[r["estado"]] = r["total"]
    contadores["total"] = sum(contadores.values())
    return contadores


def normalizar_correo(correo):
    correo = (correo or "").strip().casefold()
    return correo if not correo or CORREO_RE.fullmatch(correo) else None


def generar_codigo_seguimiento():
    return f"LSCC-{datetime.now().year}-{secrets.token_hex(6).upper()}"


def limite_reporte_publico_superado(ip):
    ahora = time.time()
    with reportes_publicos_lock:
        intentos = reportes_publicos_ip[ip]
        while intentos and ahora - intentos[0] > REPORTES_PUBLICOS_VENTANA:
            intentos.popleft()
        if len(intentos) >= REPORTES_PUBLICOS_MAX:
            return True
        intentos.append(ahora)
    return False


def resumen_urbano_publico():
    with lock:
        conexion = estado.get("conexion_mqtt")
        ultima = estado.get("ultima_actualizacion")
        ultima_vez = dict(estado.get("ultima_vez_modulos") or {})
        tachos = dict((estado.get("residuos") or {}).get("tachos") or {})
    ahora = time.time()
    edades = [ahora - ts for ts in ultima_vez.values() if isinstance(ts, (int, float)) and ts > 0]
    reciente = bool(edades and min(edades) <= 120)
    if conexion == "conectado" and reciente:
        general = "Operativo"
    elif conexion == "conectado":
        general = "Datos en actualización"
    else:
        general = "Sin conexión reciente"
    ambiental_reciente = any(
        ahora - ultima_vez.get(dispositivo, 0) <= 120
        for dispositivo in ("ESP32_AIRE_01",) if ultima_vez.get(dispositivo)
    )
    requieren_atencion = sum(
        1 for t in tachos.values()
        if isinstance(t, dict) and (t.get("porcentaje_llenado") or 0) >= 80
    )
    ultima_ruta = obtener_ultima_ruta_recoleccion()
    if requieren_atencion == 0:
        estado_recojo = "No se requiere recojo por el momento"
    elif ultima_ruta and ultima_ruta.get("tachos_incluidos"):
        estado_recojo = "Ruta de recojo disponible"
    else:
        estado_recojo = "Atención de recojo pendiente"
    return {
        "general": general,
        "ambiente": "Lecturas ambientales disponibles" if ambiental_reciente else "Sin datos recientes",
        "contenedores": 4,
        "requieren_atencion": min(requieren_atencion, 4),
        "estado_recojo": estado_recojo,
        "ultima_ruta_recojo": ultima_ruta["fecha_generacion"] if ultima_ruta else "Sin planificación reciente",
        "reportes": obtener_contadores_reportes(),
        "ultima_actualizacion": ultima or "Sin actualización reciente",
    }

# ============================================================
# CALLBACKS MQTT
# ============================================================
def on_connect(client, userdata, flags, rc):
    print(f"[DEBUG on_connect] rc={rc}", flush=True)
    with lock:
        estado["conexion_mqtt"] = "conectado" if rc == 0 else f"error rc={rc}"
    if rc == 0:
        result = client.subscribe("lscc/#")
        print(f"[DEBUG on_connect] subscribe result={result}", flush=True)
        agregar_log("Dashboard conectado y suscrito a lscc/#")
    else:
        agregar_log(f"Error al conectar al broker. Código: {rc}")


def on_disconnect(client, userdata, rc):
    with lock:
        estado["conexion_mqtt"] = "desconectado"
    agregar_log("Dashboard desconectado del broker")

def on_message(client, userdata, msg):
    topic = msg.topic

    # --- Imagen binaria ESP32-CAM ---
    if topic == "lscc/vigilancia/imagen":
        try:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            nombre_archivo = f"{ts}_ESP32_CAM_01.jpg"
            ruta_foto = IMG_DIR / nombre_archivo

            # Guardar foto histórica
            ruta_foto.write_bytes(msg.payload)

            # Guardar última imagen para mostrar en dashboard
            LAST_IMAGE.write_bytes(msg.payload)

            with lock:
                estado["vigilancia"]["imagen_recibida"] = True
                estado["vigilancia"]["imagen_timestamp"] = int(time.time())
                estado["vigilancia"]["ultima_ruta"] = str(ruta_foto)
                estado["ultimo_mensaje"] = topic
                estado["ultima_actualizacion"] = time.strftime("%H:%M:%S")

            with lock:
                meta = dict(estado["vigilancia"].get("imagen_meta") or {})

            # Un único registro combina el binario recibido con su metadata.
            db_insert_imagen_meta(
                meta.get("device_id", "ESP32_CAM_01"),
                meta.get("width"),
                meta.get("height"),
                len(msg.payload),
                meta.get("trigger", "captura_imagen"),
                str(ruta_foto)
            )

            agregar_log(f"Imagen guardada: {nombre_archivo} ({len(msg.payload)} bytes)")

        except Exception as e:
            agregar_log(f"Error guardando imagen: {e}")

        return

    print(f"[DEBUG MQTT] topic={topic}", flush=True)

    data = parse_json(msg.payload)
    if data is None:
        print(f"[DEBUG MQTT] payload no es JSON", flush=True)
        agregar_log(f"Payload no-JSON en {topic}")
        return

    device_id = data.get("device_id", "desconocido")
    registrado = db_dispositivo_registrado(device_id)
    print(f"[DEBUG MQTT] device_id={device_id} registrado={registrado}", flush=True)
    if not registrado:
        agregar_log(f"Dispositivo no registrado rechazado: {device_id}")
        return

    with lock:
        estado["ultimo_mensaje"] = topic
        estado["ultima_actualizacion"] = time.strftime("%H:%M:%S")
        estado["device_id"] = device_id
        # Will offline = timestamp 0 → nodo aparece offline inmediatamente en el dashboard
        if topic == "lscc/sistema/status" and data.get("status") == "offline":
            estado["ultima_vez_modulos"][device_id] = 0
        else:
            estado["ultima_vez_modulos"][device_id] = time.time()

        if topic == "lscc/ambiental/temperatura":
            valor = data.get("value")
            est = data.get("estado", "ok")
            estado["ambiental"]["temperatura"] = valor
            agregar_historial("temperatura", valor)
            db_insert_ambiental(device_id, "DHT22", "temperatura", valor, "C", est)

        elif topic == "lscc/ambiental/humedad":
            valor = data.get("value")
            est = data.get("estado", "ok")
            estado["ambiental"]["humedad"] = valor
            agregar_historial("humedad", valor)
            db_insert_ambiental(device_id, "DHT22", "humedad", valor, "%HR", est)

        elif topic == "lscc/ambiental/presion":
            valor = data.get("value")
            est = data.get("estado", "ok")
            estado["ambiental"]["presion"] = valor
            agregar_historial("presion", valor)
            db_insert_ambiental(device_id, "BMP280", "presion", valor, "hPa", est)

        elif topic == "lscc/ambiental/gas":
            gas_data = {
                "value_raw": data.get("value_raw"),
                "voltage": data.get("voltage"),
                "nivel": data.get("nivel"),
                "estado": data.get("estado"),
            }

            estado["ambiental"]["gas"] = gas_data
            agregar_historial("gas", data.get("voltage"))

            raw = data.get("value_raw")
            voltage = data.get("voltage")
            nivel = data.get("nivel", "normal")
            est = data.get("estado", "ok")

            db_insert_ambiental(
                device_id,
                "MQ-2",
                "gas",
                voltage,
                "V",
                est,
                nivel=nivel,
                valor_raw=raw,
                voltaje=voltage
            )

            if nivel in ("preventivo", "elevado"):
                prioridad = "alta" if nivel == "elevado" else "media"
                db_insert_alerta(
                    device_id,
                    "ambiental",
                    f"gas_{nivel}",
                    f"MQ-2 nivel {nivel} — voltaje {voltage} V",
                    prioridad
                )

        elif topic == "lscc/residuos/nivel":
            sensor_id = str(data.get("sensor_id", "1"))

            if sensor_id not in estado["residuos"]["tachos"]:
                estado["residuos"]["tachos"][sensor_id] = nuevo_tacho(sensor_id)

            pct = get_num(data, "porcentaje_llenado", "nivel_llenado")
            nivel = data.get("nivel")

            tacho = estado["residuos"]["tachos"][sensor_id]
            tacho.update({
                "sensor_id": data.get("sensor_id"),
                "distancia_cm": data.get("distancia_cm"),
                "porcentaje_llenado": pct,
                "nivel": nivel,
                "estado": data.get("estado"),
                "ultima_actualizacion": time.strftime("%H:%M:%S"),
                "device_id": device_id,
            })

            agregar_historial(f"residuos_{sensor_id}", pct)

            db_insert_residuos(
                device_id,
                data.get("sensor_id"),
                data.get("distancia_cm"),
                pct,
                nivel
            )

            if nivel == "alto":
                db_insert_alerta(
                    device_id,
                    "residuos",
                    "contenedor_alto",
                    f"Contenedor {sensor_id} al {pct}% — requiere vaciado",
                    "alta"
                )

        elif topic == "lscc/vigilancia/sonido":
            estado["vigilancia"]["sonido"] = data
            agregar_historial("sonido", data.get("porcentaje", data.get("value")))

            db_insert_sonido(
                device_id,
                data.get("value"),
                data.get("voltage"),
                data.get("porcentaje"),
                data.get("nivel"),
                data.get("evento")
            )

        elif topic == "lscc/vigilancia/imagen_meta":
            estado["vigilancia"]["imagen_meta"] = data

        elif topic == "lscc/sistema/status":
            estado["sistema"]["status"] = data

            # Capturar stream URL cuando la cámara publica su IP
            if device_id == "ESP32_CAM_01" and data.get("stream_url"):
                estado["vigilancia"]["cam_stream_url"] = data["stream_url"]

            status_dispositivo = data.get("status", "error")
            if status_dispositivo not in ("online", "offline", "sin_datos", "error"):
                status_dispositivo = "error"

            db_insert_estado(
                device_id,
                data.get("modulo"),
                status_dispositivo,
                json.dumps(data)
            )

    agregar_log(f"← {topic} [{device_id}]")

# ============================================================
# HILO MQTT
# ============================================================
def iniciar_mqtt():
    try:
        client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION1,
            client_id="dashboard_lscc_fase1"
        )
    except AttributeError:
        client = mqtt.Client(client_id="dashboard_lscc_fase1")
    if MQTT_USER:
        client.username_pw_set(MQTT_USER, MQTT_PASSWORD)
    if MQTT_TLS:
        ca_cert = Path(MQTT_CA_CERT)
        if not ca_cert.is_absolute():
            ca_cert = BASE_DIR / ca_cert
        certfile = Path(MQTT_CERTFILE) if MQTT_CERTFILE else None
        keyfile = Path(MQTT_KEYFILE) if MQTT_KEYFILE else None
        if certfile and not certfile.is_absolute():
            certfile = BASE_DIR / certfile
        if keyfile and not keyfile.is_absolute():
            keyfile = BASE_DIR / keyfile
        if not ca_cert.is_file():
            raise RuntimeError(f"No se encontró el certificado CA MQTT: {ca_cert}")
        client.tls_set(
            ca_certs=str(ca_cert),
            certfile=str(certfile) if certfile else None,
            keyfile=str(keyfile) if keyfile else None,
            tls_version=ssl.PROTOCOL_TLS_CLIENT,
        )
    client.on_connect    = on_connect
    client.on_disconnect = on_disconnect
    client.on_message    = on_message

    while True:
        try:
            print(f"[DEBUG MQTT] Intentando connect a {MQTT_BROKER}:{MQTT_PORT}", flush=True)
            agregar_log(f"Conectando a broker {MQTT_BROKER}:{MQTT_PORT}")
            client.connect(MQTT_BROKER, MQTT_PORT, MQTT_KEEPALIVE)
            print(f"[DEBUG MQTT] connect() retornó OK, entrando a loop_forever", flush=True)
            client.loop_forever()
            print(f"[DEBUG MQTT] loop_forever() salió SIN excepción", flush=True)
        except Exception as e:
            print(f"[DEBUG MQTT] EXCEPCIÓN: {e}", flush=True)
            with lock:
                estado["conexion_mqtt"] = "desconectado"
            agregar_log(f"Error MQTT: {e}. Reintentando en 5 s...")
            time.sleep(5)


# ============================================================
# RUTAS FLASK
# ============================================================
@app.route("/")
def index():
    if not session.get("user_id") or not session.get("session_token"):
        return render_template("inicio_publico.html")
    return index_autenticado()


@login_requerido
def index_autenticado():
    contadores = obtener_contadores_reportes(
        None if session.get("rol") in ("admin", "trabajador") else session.get("user_id")
    )
    template = "index.html" if session.get("rol") == "usuario" else "dashboard_principal.html"
    return render_template(
        template,
        username=session.get("username"),
        rol=session.get("rol"),
        contadores=contadores
    )


@app.route("/estado-urbano")
def estado_urbano():
    return render_template("estado_urbano.html", resumen=resumen_urbano_publico())


def render_dashboard_tecnico(template):
    """Construye el contexto visual común sin duplicar lógica de datos IoT."""
    return render_template(
        template,
        username=session.get("username"),
        rol=session.get("rol")
    )


@app.route("/vigilancia")
@login_requerido
@trabajador_o_admin_requerido
def vigilancia():
    return render_dashboard_tecnico("vigilancia.html")


@app.route("/ambiente")
@login_requerido
@trabajador_o_admin_requerido
def ambiente():
    return render_dashboard_tecnico("ambiente.html")


@app.route("/residuos")
@login_requerido
@trabajador_o_admin_requerido
def residuos():
    return render_dashboard_tecnico("residuos.html")


@app.route("/ruta-recoleccion")
@login_requerido
@trabajador_o_admin_requerido
def ruta_recoleccion():
    return render_dashboard_tecnico("ruta_recoleccion.html")


@app.route("/api/ruta-recoleccion-datos")
@login_requerido
@trabajador_o_admin_requerido
def api_ruta_recoleccion_datos():
    with get_db() as conn:
        rows = conn.execute("""
            SELECT r.sensor_id, r.porcentaje_llenado, r.nivel, r.timestamp
            FROM lecturas_residuos r
            INNER JOIN (
                SELECT sensor_id, MAX(timestamp) AS ultimo
                FROM lecturas_residuos
                WHERE sensor_id BETWEEN 1 AND 4
                GROUP BY sensor_id
            ) ult ON ult.sensor_id = r.sensor_id AND ult.ultimo = r.timestamp
            ORDER BY r.sensor_id
        """).fetchall()
    lecturas = {row["sensor_id"]: dict(row) for row in rows}
    ahora = datetime.now()
    tachos = []
    for sensor_id, etiqueta in enumerate(("A", "B", "C", "D"), start=1):
        lectura = lecturas.get(sensor_id)
        reciente = False
        if lectura and lectura.get("timestamp"):
            try:
                reciente = (ahora - datetime.strptime(lectura["timestamp"], "%Y-%m-%d %H:%M:%S")).total_seconds() <= 120
            except ValueError:
                reciente = False
        tachos.append({
            "id": etiqueta,
            "sensor_id": sensor_id,
            "porcentaje": lectura.get("porcentaje_llenado") if lectura else None,
            "nivel": lectura.get("nivel") if lectura else None,
            "ultima_actualizacion": lectura.get("timestamp") if lectura else None,
            "reciente": reciente,
        })
    return jsonify({"tachos": tachos, "actualizado_en": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})


@app.route("/api/ruta-recoleccion-ultima")
@login_requerido
@trabajador_o_admin_requerido
def api_ruta_recoleccion_ultima():
    return jsonify({"ruta": obtener_ultima_ruta_recoleccion()})


@app.route("/api/ruta-recoleccion-guardar", methods=["POST"])
@login_requerido
@trabajador_o_admin_requerido
def api_ruta_recoleccion_guardar():
    datos = request.get_json(silent=True) or {}
    permitidos = {"A", "B", "C", "D"}
    orden = datos.get("orden") or []
    incluidos = datos.get("incluidos") or []
    omitidos = datos.get("omitidos") or []
    niveles = datos.get("niveles") or []
    try:
        distancia = float(datos.get("distancia", 0))
    except (TypeError, ValueError):
        return jsonify({"error": "datos_invalidos"}), 400
    if not (0 <= distancia <= 10000):
        return jsonify({"error": "datos_invalidos"}), 400
    if not all(isinstance(x, str) and x in permitidos for x in orden + incluidos + omitidos):
        return jsonify({"error": "datos_invalidos"}), 400
    if len(set(orden)) != len(orden) or set(orden) != set(incluidos):
        return jsonify({"error": "datos_invalidos"}), 400
    if set(incluidos) & set(omitidos) or set(incluidos) | set(omitidos) != permitidos:
        return jsonify({"error": "datos_invalidos"}), 400
    niveles_limpios = []
    for item in niveles:
        if not isinstance(item, dict) or item.get("id") not in permitidos:
            return jsonify({"error": "datos_invalidos"}), 400
        porcentaje = item.get("porcentaje")
        if porcentaje is not None:
            try:
                porcentaje = max(0, min(100, float(porcentaje)))
            except (TypeError, ValueError):
                return jsonify({"error": "datos_invalidos"}), 400
        niveles_limpios.append({
            "id": item["id"], "porcentaje": porcentaje,
            "reciente": bool(item.get("reciente")),
            "ultima_actualizacion": item.get("ultima_actualizacion")
        })
    if len(niveles_limpios) != 4 or {x["id"] for x in niveles_limpios} != permitidos:
        return jsonify({"error": "datos_invalidos"}), 400
    ultima_lectura = max((x["ultima_actualizacion"] for x in niveles_limpios if x["ultima_actualizacion"]), default=None)
    with get_db() as conn:
        conn.execute("""
            INSERT INTO rutas_recoleccion
                (orden_tachos, tachos_incluidos, tachos_omitidos, distancia_estimada,
                 niveles_analizados, ultima_lectura_residuos, desactualizada)
            VALUES (?, ?, ?, ?, ?, ?, 0)
        """, (
            json.dumps(orden), json.dumps(incluidos), json.dumps(omitidos), distancia,
            json.dumps(niveles_limpios), ultima_lectura
        ))
    return jsonify({"ok": True, "ruta": obtener_ultima_ruta_recoleccion()})


@app.route("/sonido")
@login_requerido
@trabajador_o_admin_requerido
def sonido():
    return render_dashboard_tecnico("sonido.html")


@app.route("/registro-tecnico")
@login_requerido
@trabajador_o_admin_requerido
def registro_tecnico():
    return render_dashboard_tecnico("registro_tecnico.html")


@app.route("/usuarios", methods=["GET", "POST"])
@login_requerido
@admin_requerido
def usuarios():
    mensaje = None
    error = None

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        # Desde administración se registran trabajadores internos.
        # El rol admin solo queda para la cuenta encargada del sistema.
        rol = request.form.get("rol", "trabajador")

        if not username or not password:
            error = "Debes completar usuario y contraseña."
        elif rol not in ("trabajador", "admin"):
            error = "Rol no válido."
        elif len(username) < 3 or len(username) > 50:
            error = "El usuario debe tener entre 3 y 50 caracteres."
        elif len(password) < 10:
            error = "La contraseña debe tener como mínimo 10 caracteres."
        else:
            try:
                with get_db() as conn:
                    conn.execute("""
                        INSERT INTO usuarios (username, password_hash, rol)
                        VALUES (?, ?, ?)
                    """, (username, generate_password_hash(password), rol))
                mensaje = f"Usuario '{username}' creado correctamente."
            except sqlite3.IntegrityError:
                error = "Ese usuario ya existe. Usa otro nombre."
            except Exception:
                app.logger.exception("No se pudo crear el usuario")
                error = "No se pudo crear el usuario. Revisa el registro del servidor."

    with get_db() as conn:
        rows = conn.execute("""
            SELECT id, username, rol, ultimo_login, creado_en,
                   CASE
                     WHEN active_session_token IS NULL THEN 'No'
                     ELSE 'Sí'
                   END AS conectado
            FROM usuarios
            ORDER BY rol, username
        """).fetchall()

    return render_template(
        "usuarios.html",
        usuarios=[dict(r) for r in rows],
        mensaje=mensaje,
        error=error,
        username=session.get("username"),
        rol=session.get("rol")
    )


@app.route("/nuevo-reporte", methods=["GET", "POST"])
def nuevo_reporte():
    mensaje = None
    error = None
    autenticado = bool(session.get("user_id") and session.get("session_token"))
    if autenticado:
        with get_db() as conn:
            usuario_actual = conn.execute(
                "SELECT rol, active_session_token FROM usuarios WHERE id = ?",
                (session.get("user_id"),)
            ).fetchone()
        if not usuario_actual or usuario_actual["active_session_token"] != session.get("session_token"):
            session.clear()
            return redirect(url_for("login", mensaje="sesion_reemplazada"))
        session["rol"] = usuario_actual["rol"]
    if autenticado and session.get("rol") != "usuario":
        return redirect(url_for("reportes"))

    if request.method == "POST":
        categoria = request.form.get("categoria", "").strip()
        titulo = request.form.get("titulo", "").strip()
        ubicacion = request.form.get("ubicacion", "").strip()
        descripcion = request.form.get("descripcion", "").strip()
        urgencia = request.form.get("urgencia", "media").strip()
        correo = normalizar_correo(request.form.get("correo_contacto"))

        if categoria not in ("ambiental", "residuos", "vigilancia"):
            error = "Selecciona una categoría válida."
        elif urgencia not in ("baja", "media", "alta"):
            error = "Selecciona una urgencia válida."
        elif not titulo or not ubicacion or not descripcion:
            error = "Completa título, ubicación y descripción."
        elif correo is None:
            error = "Ingresa un correo de contacto válido o deja el campo vacío."
        elif not autenticado and limite_reporte_publico_superado(request.remote_addr or "desconocida"):
            error = "Se alcanzó el límite temporal de reportes. Inténtalo nuevamente más tarde."
        else:
            nombre_guardado = None
            archivo = request.files.get("imagen")
            if archivo and archivo.filename:
                extension = validar_imagen_subida(archivo)
                if not extension:
                    error = "El archivo debe ser una imagen PNG, JPG o WEBP válida."
                else:
                    nombre_guardado = f"reporte_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.{extension}"
                    archivo.save(REPORTES_DIR / nombre_guardado)

            if not error:
                codigo = generar_codigo_seguimiento() if not autenticado else None
                with get_db() as conn:
                    conn.execute("""
                        INSERT INTO reportes_ciudadanos
                          (usuario_id, categoria, titulo, ubicacion, descripcion, urgencia, imagen,
                           codigo_seguimiento, correo_contacto, origen_reporte, permite_consulta_publica)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        session.get("user_id") if autenticado else None,
                        categoria, titulo, ubicacion, descripcion, urgencia, nombre_guardado,
                        codigo, correo, "cuenta" if autenticado else "publico", 0 if autenticado else 1
                    ))
                if not autenticado:
                    return render_template("reporte_confirmado.html", codigo=codigo)
                mensaje = "Reporte registrado correctamente. El administrador podrá revisarlo."

    return render_template(
        "nuevo_reporte.html" if autenticado else "nuevo_reporte_publico.html",
        mensaje=mensaje,
        error=error,
        username=session.get("username"),
        rol=session.get("rol"),
        correo_contacto=request.form.get("correo_contacto", "")
    )


@app.route("/consulta-reporte", methods=["GET", "POST"])
def consulta_reporte():
    reporte = None
    error = None
    codigo = request.values.get("codigo", "").strip().upper()
    if request.method == "POST":
        correo = normalizar_correo(request.form.get("correo_contacto"))
        if not CODIGO_SEGUIMIENTO_RE.fullmatch(codigo) or correo is None:
            error = "No se encontró un reporte con los datos proporcionados."
        else:
            with get_db() as conn:
                row = conn.execute("""
                    SELECT codigo_seguimiento, categoria, estado, creado_en, actualizado_en
                    FROM reportes_ciudadanos
                    WHERE codigo_seguimiento = ? AND origen_reporte = 'publico'
                      AND permite_consulta_publica = 1
                      AND (correo_contacto IS NULL OR correo_contacto = '' OR correo_contacto = ?)
                """, (codigo, correo or "")).fetchone()
            if row:
                reporte = dict(row)
                estados = {"pendiente": "Recibido", "en_revision": "En revisión", "atendido": "Atendido", "rechazado": "No procede"}
                reporte["estado_publico"] = estados.get(reporte["estado"], "Recibido")
            else:
                error = "No se encontró un reporte con los datos proporcionados."
    return render_template("consulta_reporte.html", reporte=reporte, error=error, codigo=codigo)


@app.route("/reportes")
@login_requerido
def reportes():
    estado_filtro = request.args.get("estado", "todos")
    categoria_filtro = request.args.get("categoria", "todos")
    params = []
    filtros = []

    if session.get("rol") == "usuario":
        filtros.append("r.usuario_id = ?")
        params.append(session.get("user_id"))

    if estado_filtro in ("pendiente", "en_revision", "atendido", "rechazado"):
        filtros.append("r.estado = ?")
        params.append(estado_filtro)

    if categoria_filtro in ("ambiental", "residuos", "vigilancia"):
        filtros.append("r.categoria = ?")
        params.append(categoria_filtro)

    where = "WHERE " + " AND ".join(filtros) if filtros else ""

    with get_db() as conn:
        rows = conn.execute(f"""
            SELECT r.*, COALESCE(u.username, 'Visitante') AS username
            FROM reportes_ciudadanos r
            LEFT JOIN usuarios u ON u.id = r.usuario_id
            {where}
            ORDER BY
                CASE r.estado
                    WHEN 'pendiente' THEN 1
                    WHEN 'en_revision' THEN 2
                    WHEN 'atendido' THEN 3
                    ELSE 4
                END,
                r.creado_en DESC
        """, params).fetchall()

    return render_template(
        "reportes.html",
        reportes=[dict(r) for r in rows],
        estado_filtro=estado_filtro,
        categoria_filtro=categoria_filtro,
        username=session.get("username"),
        rol=session.get("rol"),
        contadores=obtener_contadores_reportes(None if session.get("rol") in ("admin", "trabajador") else session.get("user_id"))
    )


@app.route("/reportes/<int:reporte_id>/actualizar", methods=["POST"])
@login_requerido
@trabajador_o_admin_requerido
def actualizar_reporte(reporte_id):
    nuevo_estado = request.form.get("estado", "pendiente")
    observacion = request.form.get("observacion_admin", "").strip()

    if nuevo_estado not in ("pendiente", "en_revision", "atendido", "rechazado"):
        return redirect(url_for("reportes"))

    with get_db() as conn:
        conn.execute("""
            UPDATE reportes_ciudadanos
            SET estado = ?, observacion_admin = ?, actualizado_en = datetime('now','localtime')
            WHERE id = ?
        """, (nuevo_estado, observacion, reporte_id))

    return redirect(url_for("reportes"))


@app.route("/reportes/adjunto/<filename>")
@login_requerido
def reporte_adjunto(filename):
    filename = secure_filename(filename)
    ruta = REPORTES_DIR / filename
    with get_db() as conn:
        reporte = conn.execute(
            "SELECT usuario_id FROM reportes_ciudadanos WHERE imagen = ?",
            (filename,)
        ).fetchone()
    autorizado = reporte and (
        session.get("rol") in ("admin", "trabajador")
        or reporte["usuario_id"] == session.get("user_id")
    )
    if not autorizado or not ruta.is_file():
        return "Archivo no encontrado", 404
    return send_file(ruta)


@app.route("/api/data")
@login_requerido
def api_data():
    with lock:
        copia = json.loads(json.dumps(estado))
    return jsonify(copia)


@app.route("/imagen")
@login_requerido
def imagen():
    if LAST_IMAGE.exists():
        return send_file(LAST_IMAGE, mimetype="image/jpeg")
    return send_file(BASE_DIR / "static" / "sin_imagen.svg", mimetype="image/svg+xml")


# Fase 1: Endpoint de historial desde la DB
@app.route("/api/history/<variable>")
@login_requerido
def api_history(variable):
    """
    Devuelve las últimas lecturas de una variable desde la DB.
    Uso: /api/history/temperatura?limite=50
    """
    try:
        limite = int(request.args.get("limite", 50))
    except (TypeError, ValueError):
        return jsonify({"error": "El límite debe ser un número entero"}), 400
    limite = max(1, min(limite, 500))

    variables_validas = {"temperatura", "humedad", "presion", "gas",
                         "sonido", "residuos_1", "residuos_2",
                         "residuos_3", "residuos_4"}
    if variable not in variables_validas:
        return jsonify({"error": f"Variable '{variable}' no válida"}), 400

    if variable.startswith("residuos_"):
        sid = int(variable.split("_")[1])
        data = db_cargar_historial_residuos(sid, limite)
    elif variable == "sonido":
        data = db_cargar_historial_sonido(limite)
    else:
        data = db_cargar_historial(variable, limite)

    return jsonify({"variable": variable, "datos": data, "total": len(data)})


@app.route("/api/alertas")
@login_requerido
def api_alertas():
    """Devuelve las alertas activas más recientes."""
    try:
        with get_db() as conn:
            rows = conn.execute("""
                SELECT device_id, modulo, tipo_alerta, descripcion,
                       prioridad, estado, timestamp
                FROM eventos_alerta
                WHERE estado = 'activa'
                ORDER BY timestamp DESC LIMIT 20
            """).fetchall()
        return jsonify([dict(r) for r in rows])
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/dispositivos")
@login_requerido
def api_dispositivos():
    """Devuelve el estado de todos los dispositivos registrados."""
    try:
        with get_db() as conn:
            rows = conn.execute("""
                SELECT d.device_id, d.modulo, d.descripcion, d.activo, d.ultima_vez,
                       e.status, e.timestamp as ultimo_heartbeat
                FROM dispositivos d
                LEFT JOIN estado_dispositivos e
                  ON e.id = (
                    SELECT MAX(id) FROM estado_dispositivos
                    WHERE device_id = d.device_id
                  )
                ORDER BY d.modulo, d.device_id
            """).fetchall()
        ahora = datetime.now()
        dispositivos = []
        for row in rows:
            item = dict(row)
            timestamp = item.get("ultimo_heartbeat") or item.get("ultima_vez")
            segundos_sin_datos = None
            if timestamp:
                try:
                    segundos_sin_datos = max(
                        0, int((ahora - datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S")).total_seconds())
                    )
                except ValueError:
                    pass
            item["segundos_sin_datos"] = segundos_sin_datos
            item["estado_calculado"] = (
                "offline"
                if segundos_sin_datos is None or segundos_sin_datos > DEVICE_OFFLINE_SECONDS
                else item.get("status", "online")
            )
            dispositivos.append(item)
        return jsonify(dispositivos)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ============================================================
# MAIN
# ============================================================
if __name__ == "__main__":
    # Verificar que la DB existe
    if not os.path.exists(DB_PATH):
        print(f"[ERROR] No se encontró '{DB_PATH}'.")
        print("[ERROR] Ejecuta primero: python db/crear_db.py")
        exit(1)

    crear_tablas_auth_si_no_existen()
    print(f"[DB] Usando base de datos: {DB_PATH}")
    print(f"[MQTT] Broker: {MQTT_BROKER}:{MQTT_PORT} | TLS: {MQTT_TLS} | User: {MQTT_USER}")

    hilo = threading.Thread(target=iniciar_mqtt, daemon=True)
    hilo.start()

    app.run(host="0.0.0.0", port=5000, debug=False)
