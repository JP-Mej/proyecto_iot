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

from flask import Flask, Response, render_template, jsonify, send_file, request, redirect, url_for, session
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
import requests
os.environ["OPENCV_VIDEOIO_PRIORITY_OBSENSOR"] = "0"
import cv2
from pygrabber.dshow_graph import FilterGraph
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

# Bot de WhatsApp (microservicio Node.js aparte, ver whatsapp_bot/)
WHATSAPP_BOT_URL = os.environ.get("WHATSAPP_BOT_URL", "").rstrip("/")
WHATSAPP_BOT_TOKEN = os.environ.get("WHATSAPP_BOT_TOKEN", "")
USB_CAMERA_INDEX = 0
OBS_CAMERA_INDEX = 1
YOLO_MODEL_NAME = "yolov8n.pt"
YOLO_MODEL_PATH = BASE_DIR / YOLO_MODEL_NAME
PERSONA_CONFIANZA_MINIMA = 0.45
ANALISIS_CADA_N_FRAMES = 5
PERSONA_FRAMES_CONSECUTIVOS = 3
EVENTO_VIGILANCIA_COOLDOWN = 20
PERMANENCIA_PROLONGADA_SEGUNDOS = 25
TRANSITO_REPETITIVO_APARICIONES = 3
TRANSITO_REPETITIVO_VENTANA_SEGUNDOS = 120
PERSONA_FRAMES_AUSENTES = 2
DETECCION_ROSTRO_ACTIVA = True
DETECCION_POSE_ACTIVA = True
POSE_MODEL_NAME = "yolov8n-pose.pt"
POSE_MODEL_PATH = BASE_DIR / POSE_MODEL_NAME
ROSTRO_REGION_SUPERIOR = 0.60
ROSTRO_NO_VISIBLE_FRAMES = 8
ROSTRO_NO_VISIBLE_COOLDOWN = 30
CONFIANZA_POSE_MINIMA = 0.35
CONFIANZA_ROSTRO_MINIMA = 0.40
# Detector facial DNN (YuNet) — detecta rostros frontales, en ángulo y de perfil;
# los Haar Cascades quedan solo como respaldo si falta el .onnx
YUNET_MODEL_NAME = "face_detection_yunet_2023mar.onnx"
YUNET_MODEL_PATH = BASE_DIR / YUNET_MODEL_NAME
CONFIANZA_YUNET_MINIMA = 0.6
# Modelo ML ambiental (Random Forest, entrenar_modelo_ambiental.py):
# clasifica 'Normal'/'Incendio' con temperatura, humedad, presión y gas (V)
MODELO_AMBIENTAL_NAME = "modelo_ambiental_lscc.pkl"
MODELO_AMBIENTAL_PATH = BASE_DIR / MODELO_AMBIENTAL_NAME
RIESGO_INCENDIO_CONSECUTIVOS = 3
PERFIL_FRAMES_CONSECUTIVOS = 8
ESPALDA_FRAMES_CONSECUTIVOS = 10

DB_PATH_CONFIG = Path(os.environ.get("LSCC_DB", "lscc.db"))
DB_PATH = DB_PATH_CONFIG if DB_PATH_CONFIG.is_absolute() else BASE_DIR / DB_PATH_CONFIG

IMG_DIR       = BASE_DIR / "imagenes"
IMG_DIR.mkdir(exist_ok=True)
LAST_IMAGE    = IMG_DIR / "ultima_imagen.jpg"

REPORTES_DIR = BASE_DIR / "reportes_adjuntos"
REPORTES_DIR.mkdir(exist_ok=True)
CAPTURAS_VIGILANCIA_DIR = BASE_DIR / "static" / "capturas_vigilancia"
CAPTURAS_VIGILANCIA_DIR.mkdir(parents=True, exist_ok=True)
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
analisis_vigilancia_lock = threading.Lock()
modelo_yolo = None
modelo_yolo_error = None
modelo_pose = None
modelo_pose_error = None
persona_frames_actuales = 0
persona_frames_ausentes = 0
presencia_confirmada = False
inicio_presencia = None
evento_persona_emitido = False
evento_permanencia_emitido = False
apariciones_persona = deque()
ultimo_evento_por_tipo = defaultdict(float)
detectores_rostro = None
detectores_rostro_error = None
detector_yunet = None
detector_yunet_error = None
modelo_ambiental = None
modelo_ambiental_error = None
riesgo_incendio_consecutivos = 0
rostro_no_visible_frames = 0
perfil_frames_actuales = 0
espalda_frames_actuales = 0
evento_perfil_emitido = False
rostro_no_visible_activo = False
permanencia_activa = False
transito_repetitivo_hasta = 0.0
evento_rostro_permanencia_emitido = False
evento_rostro_transito_emitido = False
estado_analisis_vigilancia = {
    "disponible": None,
    "estado": "Iniciando análisis de Cámara USB",
    "persona_detectada": False,
    "estado_persona": "Sin persona",
    "orientacion_rostro": "No determinado",
    "orientacion_estimada": "No determinada",
    "visibilidad_facial": "No concluyente",
    "nivel_alerta": "normal",
    "pose_disponible": None,
    "ultima_alerta": None,
}
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
                telefono TEXT,
                creado_en TEXT NOT NULL DEFAULT (datetime('now','localtime'))
            );
        """)

        columnas_usuarios = {fila["name"] for fila in conn.execute("PRAGMA table_info(usuarios)").fetchall()}
        if "telefono" not in columnas_usuarios:
            conn.execute("ALTER TABLE usuarios ADD COLUMN telefono TEXT")

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

        conn.execute("""
            CREATE TABLE IF NOT EXISTS eventos_vigilancia (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                camara TEXT NOT NULL,
                tipo_evento TEXT NOT NULL,
                descripcion TEXT NOT NULL,
                fecha_hora TEXT NOT NULL DEFAULT (datetime('now','localtime')),
                imagen_path TEXT,
                estado TEXT NOT NULL DEFAULT 'pendiente'
                    CHECK(estado IN ('pendiente','revisado'))
            );
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_eventos_vigilancia_fecha
            ON eventos_vigilancia(fecha_hora DESC);
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
        telefono = re.sub(r"[^0-9+]", "", request.form.get("telefono", "").strip())
        if telefono and not telefono.startswith("+") and len(telefono) == 9 and telefono.startswith("9"):
            # Celular peruano sin código de país (ej: 987654321) -> anteponer +51
            telefono = "+51" + telefono

        if not username or not password:
            return render_template("registro.html", error="Completa usuario y contraseña.")
        if len(username) < 3 or len(username) > 50:
            return render_template("registro.html", error="El usuario debe tener entre 3 y 50 caracteres.")
        if len(password) < 10:
            return render_template("registro.html", error="La contraseña debe tener al menos 10 caracteres.")
        if password != confirmar:
            return render_template("registro.html", error="Las contraseñas no coinciden.")
        if telefono and not re.fullmatch(r"\+?[0-9]{9,15}", telefono):
            return render_template("registro.html", error="Ingresa un celular válido (solo números, con código de país opcional, ej: +51987654321) o deja el campo vacío.")

        try:
            with get_db() as conn:
                conn.execute("""
                    INSERT INTO usuarios (username, password_hash, rol, telefono)
                    VALUES (?, ?, 'usuario', ?)
                """, (username, generate_password_hash(password), telefono or None))
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


def enviar_whatsapp(telefono, mensaje):
    """Pide al microservicio Node (whatsapp_bot/) que envíe un WhatsApp.

    No lanza excepción hacia el llamador: una falla en la notificación
    (bot caído, número inválido, etc.) nunca debe romper la actualización
    del reporte.
    """
    if not telefono or not WHATSAPP_BOT_URL:
        return
    try:
        requests.post(
            f"{WHATSAPP_BOT_URL}/enviar",
            json={"telefono": telefono, "mensaje": mensaje},
            headers={"Authorization": f"Bearer {WHATSAPP_BOT_TOKEN}"},
            timeout=10,
        )
    except requests.RequestException:
        app.logger.exception("No se pudo enviar la notificación de WhatsApp a %s", telefono)


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


def hace_cuanto(marca_tiempo):
    """Humaniza un timestamp 'YYYY-MM-DD HH:MM:SS' (hora local) tipo 'hace 12 min'."""
    if not marca_tiempo:
        return None
    try:
        entonces = datetime.strptime(marca_tiempo, "%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError):
        return None
    segundos = max((datetime.now() - entonces).total_seconds(), 0)
    if segundos < 60:
        return "hace unos segundos"
    minutos = int(segundos // 60)
    if minutos < 60:
        return f"hace {minutos} min"
    horas = int(minutos // 60)
    if horas < 24:
        return f"hace {horas} h"
    return f"hace {int(horas // 24)} d"


def resumen_urbano_publico():
    with lock:
        conexion = estado.get("conexion_mqtt")
        ultima = estado.get("ultima_actualizacion")
        ultima_vez = dict(estado.get("ultima_vez_modulos") or {})
        tachos = dict((estado.get("residuos") or {}).get("tachos") or {})
        riesgo_ml = dict((estado.get("ambiental") or {}).get("riesgo_ml") or {})
    ahora = time.time()
    edades = [ahora - ts for ts in ultima_vez.values() if isinstance(ts, (int, float)) and ts > 0]
    reciente = bool(edades and min(edades) <= 120)
    if conexion == "conectado" and reciente:
        general = "Operativo"
    elif conexion == "conectado":
        general = "Datos en actualización"
    else:
        general = "Sin conexión reciente"

    with get_db() as conn:
        dispositivos_total = conn.execute(
            "SELECT COUNT(*) AS n FROM dispositivos WHERE activo = 1"
        ).fetchone()["n"]
        dispositivos_activos = conn.execute("""
            SELECT COUNT(*) AS n FROM dispositivos
            WHERE activo = 1 AND ultima_vez >= datetime('now', '-1 day', 'localtime')
        """).fetchone()["n"]
        ultima_lectura_ambiental = conn.execute(
            "SELECT MAX(timestamp) AS t FROM lecturas_ambientales"
        ).fetchone()["t"]
        ultima_lectura_residuos = conn.execute(
            "SELECT MAX(timestamp) AS t FROM lecturas_residuos"
        ).fetchone()["t"]
        reportes_semana = conn.execute("""
            SELECT COUNT(*) AS n FROM reportes_ciudadanos
            WHERE creado_en >= datetime('now', '-7 days', 'localtime')
        """).fetchone()["n"]

    ambiental_reciente = any(
        ahora - ultima_vez.get(dispositivo, 0) <= 120
        for dispositivo in ("ESP32_AIRE_01",) if ultima_vez.get(dispositivo)
    )
    prediccion_ml = riesgo_ml.get("prediccion")
    if prediccion_ml == "Incendio":
        ambiente_texto = "Riesgo de incendio detectado"
    elif prediccion_ml == "Normal":
        ambiente_texto = "Ambiente normal"
    elif ambiental_reciente:
        ambiente_texto = "Lecturas ambientales disponibles"
    else:
        ambiente_texto = "Sin datos recientes"

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
        "dispositivos_activos": dispositivos_activos,
        "dispositivos_total": dispositivos_total,
        "ambiente": ambiente_texto,
        "ambiente_actualizado": hace_cuanto(ultima_lectura_ambiental),
        "contenedores": 4,
        "requieren_atencion": min(requieren_atencion, 4),
        "estado_recojo": estado_recojo,
        "residuos_actualizado": hace_cuanto(ultima_lectura_residuos),
        "ultima_ruta_recojo": ultima_ruta["fecha_generacion"] if ultima_ruta else "Sin planificación reciente",
        "reportes": obtener_contadores_reportes(),
        "reportes_semana": reportes_semana,
        "ultima_actualizacion": ultima or "Sin actualización reciente",
    }

# ============================================================
# MODELO ML AMBIENTAL (Normal / Incendio)
# ============================================================
def obtener_modelo_ambiental():
    """Carga el Random Forest una vez; si falta el .pkl la página sigue sin ML."""
    global modelo_ambiental, modelo_ambiental_error
    if modelo_ambiental is not None:
        return modelo_ambiental
    if modelo_ambiental_error is not None:
        return None
    try:
        if not MODELO_AMBIENTAL_PATH.exists():
            raise FileNotFoundError(
                f"No existe {MODELO_AMBIENTAL_NAME} (ejecuta entrenar_modelo_ambiental.py)"
            )
        import joblib
        modelo_ambiental = joblib.load(MODELO_AMBIENTAL_PATH)
        print("[ML] Modelo ambiental Normal/Incendio cargado")
    except Exception as error:
        modelo_ambiental_error = str(error)
        print(f"[ML] Modelo ambiental no disponible: {error}")
    return modelo_ambiental


def evaluar_riesgo_ambiental(device_id):
    """Predice Normal/Incendio con las últimas 4 variables. Requiere `lock` tomado."""
    global riesgo_incendio_consecutivos
    modelo = obtener_modelo_ambiental()
    if modelo is None:
        return

    amb = estado["ambiental"]
    gas = amb.get("gas") or {}
    crudos = [amb.get("temperatura"), amb.get("humedad"), amb.get("presion"), gas.get("voltage")]
    try:
        fila = [float(v) for v in crudos]
    except (TypeError, ValueError):
        return
    # Lecturas de error del hardware (-1) no se evalúan
    if fila[0] <= 0 or fila[1] <= 0 or fila[2] <= 0 or fila[3] < 0:
        return

    try:
        prediccion = str(modelo.predict([fila])[0])
        confianza = float(max(modelo.predict_proba([fila])[0]))
    except Exception as error:
        print(f"[ML] Error en predicción ambiental: {error}")
        return

    if prediccion == "Incendio":
        riesgo_incendio_consecutivos += 1
    else:
        riesgo_incendio_consecutivos = 0

    amb["riesgo_ml"] = {
        "prediccion": prediccion,
        "confianza": round(confianza * 100, 1),
        "consecutivos": riesgo_incendio_consecutivos,
    }

    # Alerta solo con N predicciones seguidas; db_insert_alerta aplica su antirrebote
    if prediccion == "Incendio" and riesgo_incendio_consecutivos >= RIESGO_INCENDIO_CONSECUTIVOS:
        db_insert_alerta(
            device_id,
            "ambiental",
            "riesgo_incendio_ml",
            f"Modelo ML detecta patrón de incendio ({confianza*100:.0f}% confianza) — "
            f"T={fila[0]:.1f}°C · H={fila[1]:.0f}%HR · Gas={fila[3]:.2f}V",
            "alta"
        )


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

            # El gas cierra la ráfaga de publicación: evaluar riesgo con las 4 variables
            evaluar_riesgo_ambiental(device_id)

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


def obtener_modelo_yolo():
    """Carga el modelo liviano una sola vez y deja el stream operativo si falla."""
    global modelo_yolo, modelo_yolo_error
    with analisis_vigilancia_lock:
        if modelo_yolo is not None:
            return modelo_yolo
        if modelo_yolo_error is not None:
            return None
        try:
            from ultralytics import YOLO
            print(f"[VIGILANCIA] Cargando modelo {YOLO_MODEL_PATH}...")
            modelo_yolo = YOLO(str(YOLO_MODEL_PATH))
            estado_analisis_vigilancia["disponible"] = True
            estado_analisis_vigilancia["estado"] = "Análisis inteligente activo"
            print("[VIGILANCIA] Modelo de detección listo")
        except Exception as error:
            modelo_yolo_error = str(error)
            estado_analisis_vigilancia["disponible"] = False
            estado_analisis_vigilancia["estado"] = "Análisis inteligente no disponible"
            print(f"[VIGILANCIA] Análisis inteligente no disponible: {error}")
        return modelo_yolo


def obtener_modelo_pose():
    """Carga YOLO Pose una vez; Haar sigue disponible si la carga falla."""
    global modelo_pose, modelo_pose_error
    if not DETECCION_POSE_ACTIVA:
        return None
    with analisis_vigilancia_lock:
        if modelo_pose is not None:
            return modelo_pose
        if modelo_pose_error is not None:
            return None
        try:
            from ultralytics import YOLO
            print(f"[VIGILANCIA] Cargando modelo de pose {POSE_MODEL_PATH}...")
            modelo_pose = YOLO(str(POSE_MODEL_PATH))
            estado_analisis_vigilancia["pose_disponible"] = True
            print("[VIGILANCIA] Análisis de orientación disponible")
        except Exception as error:
            modelo_pose_error = str(error)
            estado_analisis_vigilancia["pose_disponible"] = False
            print(f"[VIGILANCIA] Análisis de orientación no disponible: {error}")
        return modelo_pose


def registrar_evento_vigilancia(frame, tipo_evento, descripcion, cooldown=None):
    """Guarda una captura puntual y su evento asociado en SQLite."""
    ahora = time.time()
    cooldown = EVENTO_VIGILANCIA_COOLDOWN if cooldown is None else cooldown
    if ahora - ultimo_evento_por_tipo[tipo_evento] < cooldown:
        return None

    fecha = datetime.now()
    tipo_archivo = re.sub(r"[^a-z0-9]+", "_", tipo_evento.casefold()).strip("_")
    nombre = f"evento_{tipo_archivo}_{fecha.strftime('%Y%m%d_%H%M%S')}.jpg"
    destino = CAPTURAS_VIGILANCIA_DIR / nombre
    if not cv2.imwrite(str(destino), frame, [cv2.IMWRITE_JPEG_QUALITY, 85]):
        print(f"[VIGILANCIA] No se pudo guardar captura: {destino}")
        return None

    ruta_relativa = f"capturas_vigilancia/{nombre}"
    with get_db() as conn:
        cursor = conn.execute("""
            INSERT INTO eventos_vigilancia
                (camara, tipo_evento, descripcion, fecha_hora, imagen_path, estado)
            VALUES (?, ?, ?, ?, ?, 'pendiente')
        """, ("Cámara USB", tipo_evento, descripcion,
              fecha.strftime("%Y-%m-%d %H:%M:%S"), ruta_relativa))
        evento_id = cursor.lastrowid

    ultimo_evento_por_tipo[tipo_evento] = ahora
    alerta = {
        "id": evento_id,
        "camara": "Cámara USB",
        "tipo_evento": tipo_evento,
        "descripcion": descripcion,
        "fecha_hora": fecha.strftime("%Y-%m-%d %H:%M:%S"),
        "imagen_path": ruta_relativa,
        "estado": "pendiente",
    }
    with analisis_vigilancia_lock:
        estado_analisis_vigilancia["ultima_alerta"] = alerta
    print(f"[VIGILANCIA] {tipo_evento}; evento #{evento_id} registrado")
    return alerta


def evaluar_reglas_vigilancia(frame, detecciones, ahora=None):
    """Genera eventos temporales sin reconocer ni identificar personas."""
    global persona_frames_actuales, persona_frames_ausentes, presencia_confirmada
    global inicio_presencia, evento_persona_emitido, evento_permanencia_emitido
    global permanencia_activa, transito_repetitivo_hasta
    ahora = ahora if ahora is not None else time.time()

    if detecciones:
        persona_frames_actuales += 1
        persona_frames_ausentes = 0
        if persona_frames_actuales < PERSONA_FRAMES_CONSECUTIVOS:
            return

        confianza = max(item[4] for item in detecciones)
        if not presencia_confirmada:
            presencia_confirmada = True
            inicio_presencia = ahora
            evento_persona_emitido = False
            evento_permanencia_emitido = False
            apariciones_persona.append(ahora)
            while (apariciones_persona
                   and ahora - apariciones_persona[0] > TRANSITO_REPETITIVO_VENTANA_SEGUNDOS):
                apariciones_persona.popleft()

        if not evento_persona_emitido:
            registrar_evento_vigilancia(
                frame,
                "Persona detectada",
                f"Persona detectada con confianza {confianza:.0%}. Evento de revisión.",
            )
            evento_persona_emitido = True

        permanencia = ahora - inicio_presencia if inicio_presencia is not None else 0
        if (permanencia >= PERMANENCIA_PROLONGADA_SEGUNDOS
                and not evento_permanencia_emitido):
            permanencia_activa = True
            registrar_evento_vigilancia(
                frame,
                "Permanencia prolongada",
                f"Presencia continua durante aproximadamente {int(permanencia)} segundos.",
            )
            evento_permanencia_emitido = True

        if len(apariciones_persona) >= TRANSITO_REPETITIVO_APARICIONES:
            transito_repetitivo_hasta = ahora + ROSTRO_NO_VISIBLE_COOLDOWN
            registrar_evento_vigilancia(
                frame,
                "Tránsito repetitivo",
                f"Se registraron {len(apariciones_persona)} apariciones en un intervalo corto.",
            )
            apariciones_persona.clear()
    else:
        persona_frames_actuales = 0
        persona_frames_ausentes += 1
        if persona_frames_ausentes >= PERSONA_FRAMES_AUSENTES:
            presencia_confirmada = False
            inicio_presencia = None
            permanencia_activa = False
            evento_persona_emitido = False
            evento_permanencia_emitido = False


def obtener_detector_yunet():
    """Carga YuNet (DNN) una vez; detecta rostros frontales, en ángulo y de perfil."""
    global detector_yunet, detector_yunet_error
    if not DETECCION_ROSTRO_ACTIVA or detector_yunet_error is not None:
        return None
    if detector_yunet is not None:
        return detector_yunet
    try:
        if not YUNET_MODEL_PATH.exists():
            raise FileNotFoundError(f"No existe {YUNET_MODEL_PATH}")
        detector_yunet = cv2.FaceDetectorYN_create(
            str(YUNET_MODEL_PATH), "", (320, 320),
            CONFIANZA_YUNET_MINIMA, 0.3, 50
        )
        print("[VIGILANCIA] Detector facial YuNet disponible")
    except Exception as error:
        detector_yunet_error = str(error)
        print(f"[VIGILANCIA] YuNet no disponible, se usará Haar: {error}")
    return detector_yunet


def obtener_detectores_rostro():
    """Carga cascades locales; no descarga modelos ni almacena rasgos faciales."""
    global detectores_rostro, detectores_rostro_error
    if not DETECCION_ROSTRO_ACTIVA or detectores_rostro_error is not None:
        return None
    if detectores_rostro is not None:
        return detectores_rostro
    try:
        frontal = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        )
        perfil = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_profileface.xml"
        )
        ojos = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_eye_tree_eyeglasses.xml"
        )
        if frontal.empty() or perfil.empty() or ojos.empty():
            raise RuntimeError("No se pudieron cargar los Haar Cascades")
        detectores_rostro = (frontal, perfil, ojos)
        print("[VIGILANCIA] Detección de rostro disponible")
    except Exception as error:
        detectores_rostro_error = str(error)
        print(f"[VIGILANCIA] Detección de rostro no disponible: {error}")
    return detectores_rostro


def estimar_orientacion_pose(frame, deteccion):
    """Estima frontal, perfil o espalda usando keypoints del recorte de persona."""
    modelo = obtener_modelo_pose()
    if modelo is None:
        return None
    x1, y1, x2, y2, _confianza = deteccion
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(frame.shape[1], x2), min(frame.shape[0], y2)
    recorte = frame[y1:y2, x1:x2]
    if recorte.size == 0:
        return None
    try:
        resultado = modelo.predict(
            source=recorte, conf=0.25, imgsz=256, verbose=False, device="cpu"
        )[0]
        with analisis_vigilancia_lock:
            estado_analisis_vigilancia["pose_disponible"] = True
        if resultado.keypoints is None or resultado.keypoints.conf is None:
            return "no_concluyente"
        confianzas = resultado.keypoints.conf[0].cpu().tolist()
        nariz, ojo_i, ojo_d, oreja_i, oreja_d = confianzas[:5]
        hombro_i, hombro_d = confianzas[5:7]
        facial = [nariz, ojo_i, ojo_d, oreja_i, oreja_d]
        frontal = (
            nariz >= CONFIANZA_POSE_MINIMA
            and ojo_i >= CONFIANZA_ROSTRO_MINIMA
            and ojo_d >= CONFIANZA_ROSTRO_MINIMA
        )
        un_ojo = (ojo_i >= CONFIANZA_ROSTRO_MINIMA) ^ (ojo_d >= CONFIANZA_ROSTRO_MINIMA)
        un_lado = (
            (ojo_i >= CONFIANZA_ROSTRO_MINIMA and oreja_i >= CONFIANZA_POSE_MINIMA)
            or (ojo_d >= CONFIANZA_ROSTRO_MINIMA and oreja_d >= CONFIANZA_POSE_MINIMA)
        )
        espalda = (
            hombro_i >= CONFIANZA_POSE_MINIMA
            and hombro_d >= CONFIANZA_POSE_MINIMA
            and max(facial) < CONFIANZA_POSE_MINIMA
        )
        if frontal:
            return "frontal"
        if (nariz >= CONFIANZA_POSE_MINIMA and un_ojo) or un_lado:
            return "perfil"
        if espalda:
            return "espalda"
        return "no_concluyente"
    except Exception as error:
        print(f"[VIGILANCIA] Error en análisis de orientación: {error}")
        return None


def analizar_orientacion_rostro(frame, detecciones):
    """Combina pose y Haar; ante duda no genera una alerta fuerte."""
    global rostro_no_visible_frames, perfil_frames_actuales
    global espalda_frames_actuales, evento_perfil_emitido, rostro_no_visible_activo
    global evento_rostro_permanencia_emitido, evento_rostro_transito_emitido

    orientacion = "No determinada"
    visibilidad = "No concluyente"
    ahora = time.time()

    if not DETECCION_ROSTRO_ACTIVA:
        orientacion, visibilidad = "Detección desactivada", "No aplica"
        rostro_no_visible_activo = False
    elif not detecciones:
        rostro_no_visible_frames = perfil_frames_actuales = espalda_frames_actuales = 0
        rostro_no_visible_activo = False
        evento_perfil_emitido = False
    else:
        deteccion = max(
            detecciones, key=lambda item: (item[2] - item[0]) * (item[3] - item[1])
        )
        x1, y1, x2, y2, _confianza = deteccion
        alto_superior = max(1, int((y2 - y1) * ROSTRO_REGION_SUPERIOR))
        sx1, sy1 = max(0, x1), max(0, y1)
        sx2, sy2 = min(frame.shape[1], x2), min(frame.shape[0], y1 + alto_superior)
        region = frame[sy1:sy2, sx1:sx2]
        pose = estimar_orientacion_pose(frame, deteccion)
        if pose is None and DETECCION_POSE_ACTIVA:
            with analisis_vigilancia_lock:
                estado_analisis_vigilancia["pose_disponible"] = False

        rostros = perfiles = ojos_detectados = []
        yunet = obtener_detector_yunet()
        if yunet is not None and region.size:
            alto_region, ancho_region = region.shape[:2]
            yunet.setInputSize((ancho_region, alto_region))
            _retval, caras = yunet.detect(region)
            if caras is not None and len(caras) > 0:
                # Cada fila YuNet: [x, y, ancho, alto, ...landmarks, score]
                rostros = [tuple(int(v) for v in cara[:4]) for cara in caras]
        elif region.size:
            detectores = obtener_detectores_rostro()
            if detectores is not None:
                frontal, perfil, ojos = detectores
                gris = cv2.equalizeHist(cv2.cvtColor(region, cv2.COLOR_BGR2GRAY))
                rostros = frontal.detectMultiScale(
                    gris, scaleFactor=1.1, minNeighbors=6, minSize=(30, 30)
                )
                perfiles = perfil.detectMultiScale(
                    gris, scaleFactor=1.1, minNeighbors=6, minSize=(30, 30)
                )
                if len(perfiles) == 0:
                    perfiles = perfil.detectMultiScale(
                        cv2.flip(gris, 1), scaleFactor=1.1,
                        minNeighbors=6, minSize=(30, 30)
                    )
                ojos_detectados = ojos.detectMultiScale(
                    gris, scaleFactor=1.1, minNeighbors=7, minSize=(14, 14)
                )

        if len(rostros) > 0:
            orientacion = "Perfil" if pose == "perfil" else "Frontal o semi frontal"
            visibilidad = "Rostro visible"
            rostro_no_visible_frames = perfil_frames_actuales = espalda_frames_actuales = 0
            rostro_no_visible_activo = False
            evento_perfil_emitido = False
            rx, ry, rw, rh = rostros[0]
            cv2.rectangle(frame, (sx1 + rx, sy1 + ry),
                          (sx1 + rx + rw, sy1 + ry + rh), (34, 197, 94), 2)
        elif len(perfiles) > 0 or pose == "perfil":
            orientacion, visibilidad = "Perfil", "Parcialmente visible"
            perfil_frames_actuales += 1
            rostro_no_visible_frames = espalda_frames_actuales = 0
            rostro_no_visible_activo = False
            permanencia = ahora - inicio_presencia if inicio_presencia is not None else 0
            if (perfil_frames_actuales >= PERFIL_FRAMES_CONSECUTIVOS
                    and permanencia >= PERMANENCIA_PROLONGADA_SEGUNDOS
                    and not evento_perfil_emitido):
                registrar_evento_vigilancia(
                    frame, "Persona de perfil",
                    "Actividad inusual para revisión: persona de perfil durante una permanencia prolongada."
                )
                evento_perfil_emitido = True
        elif pose == "espalda":
            espalda_frames_actuales += 1
            rostro_no_visible_frames = perfil_frames_actuales = 0
            rostro_no_visible_activo = False
            if espalda_frames_actuales >= ESPALDA_FRAMES_CONSECUTIVOS:
                orientacion, visibilidad = "Persona de espaldas", "No aplica"
            else:
                orientacion, visibilidad = "Orientación no frontal", "No concluyente"
        elif pose == "frontal" or len(ojos_detectados) >= 2:
            orientacion = "Frontal o semi frontal"
            rostro_no_visible_frames += 1
            perfil_frames_actuales = espalda_frames_actuales = 0
            if rostro_no_visible_frames >= ROSTRO_NO_VISIBLE_FRAMES:
                visibilidad = "Rostro no visible"
                rostro_no_visible_activo = True
                registrar_evento_vigilancia(
                    frame, "Rostro no visible",
                    "Persona orientada hacia la cámara sin rostro visible durante varios frames.",
                    cooldown=ROSTRO_NO_VISIBLE_COOLDOWN,
                )
            else:
                visibilidad = "No concluyente"
        else:
            orientacion, visibilidad = "No determinada", "Visibilidad facial no concluyente"
            rostro_no_visible_frames = perfil_frames_actuales = 0
            rostro_no_visible_activo = False

        if rostro_no_visible_activo and permanencia_activa:
            if not evento_rostro_permanencia_emitido:
                registrar_evento_vigilancia(
                    frame, "Permanencia con rostro no visible",
                    "Permanencia prolongada con rostro no visible. Evento de revisión de prioridad alta.",
                    cooldown=ROSTRO_NO_VISIBLE_COOLDOWN,
                )
                evento_rostro_permanencia_emitido = True
        else:
            evento_rostro_permanencia_emitido = False

        if rostro_no_visible_activo and ahora <= transito_repetitivo_hasta:
            if not evento_rostro_transito_emitido:
                registrar_evento_vigilancia(
                    frame, "Tránsito repetitivo con rostro no visible",
                    "Tránsito repetitivo coincidente con rostro no visible. Evento de revisión de prioridad alta.",
                    cooldown=ROSTRO_NO_VISIBLE_COOLDOWN,
                )
                evento_rostro_transito_emitido = True
        elif ahora > transito_repetitivo_hasta:
            evento_rostro_transito_emitido = False

    if rostro_no_visible_activo and (permanencia_activa or ahora <= transito_repetitivo_hasta):
        nivel = "alto"
    elif rostro_no_visible_activo:
        nivel = "revisión"
    elif permanencia_activa or ahora <= transito_repetitivo_hasta:
        nivel = "medio"
    elif detecciones:
        nivel = "bajo"
    else:
        nivel = "normal"

    with analisis_vigilancia_lock:
        estado_analisis_vigilancia["orientacion_rostro"] = orientacion
        estado_analisis_vigilancia["orientacion_estimada"] = orientacion
        estado_analisis_vigilancia["visibilidad_facial"] = visibilidad
        estado_analisis_vigilancia["nivel_alerta"] = nivel
    return orientacion


def analizar_personas(frame):
    """Procesa un frame y devuelve una copia con las detecciones dibujadas."""
    modelo = obtener_modelo_yolo()
    if modelo is None:
        return frame

    try:
        resultado = modelo.predict(
            source=frame,
            classes=[0],
            conf=PERSONA_CONFIANZA_MINIMA,
            imgsz=416,
            verbose=False,
            device="cpu",
        )[0]
        detecciones = []
        for caja in resultado.boxes:
            confianza = float(caja.conf[0])
            x1, y1, x2, y2 = map(int, caja.xyxy[0].tolist())
            detecciones.append((x1, y1, x2, y2, confianza))
            cv2.rectangle(frame, (x1, y1), (x2, y2), (37, 99, 235), 2)
            cv2.putText(frame, f"Persona {confianza:.0%}", (x1, max(22, y1 - 8)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (37, 99, 235), 2)

        evaluar_reglas_vigilancia(frame, detecciones)
        analizar_orientacion_rostro(frame, detecciones)
        with analisis_vigilancia_lock:
            estado_analisis_vigilancia["disponible"] = True
            estado_analisis_vigilancia["persona_detectada"] = bool(detecciones)
            estado_analisis_vigilancia["estado_persona"] = (
                "Persona detectada" if detecciones else "Sin persona"
            )
            estado_analisis_vigilancia["estado"] = (
                "Persona detectada" if detecciones else "Análisis inteligente activo"
            )
        return frame
    except Exception as error:
        with analisis_vigilancia_lock:
            estado_analisis_vigilancia["disponible"] = False
            estado_analisis_vigilancia["estado"] = "Análisis inteligente no disponible"
        print(f"[VIGILANCIA] Error procesando frame: {error}")
        return frame


def abrir_camara_usb():
    """Abre exclusivamente la cámara USB física; nunca usa OBS como fallback."""
    try:
        dispositivos = FilterGraph().get_input_devices()
        nombre_dispositivo = (
            dispositivos[USB_CAMERA_INDEX]
            if USB_CAMERA_INDEX < len(dispositivos)
            else None
        )
    except Exception as error:
        nombre_dispositivo = None
        print(f"[CAM USB] No se pudieron enumerar nombres DirectShow: {error}")

    if nombre_dispositivo and "obs" in nombre_dispositivo.casefold():
        print(
            f"[CAM USB] Advertencia: se está usando OBS Virtual Camera "
            f"en el índice {USB_CAMERA_INDEX}; selección rechazada"
        )
        return None
    if nombre_dispositivo:
        print(
            f"[CAM USB] Cámara física seleccionada: {nombre_dispositivo} "
            f"(índice {USB_CAMERA_INDEX})"
        )

    intentos_apertura = (
        ("DSHOW (índice y backend)", lambda: cv2.VideoCapture(USB_CAMERA_INDEX, cv2.CAP_DSHOW)),
        ("DSHOW (backend + índice)", lambda: cv2.VideoCapture(cv2.CAP_DSHOW + USB_CAMERA_INDEX)),
        ("MSMF", lambda: cv2.VideoCapture(USB_CAMERA_INDEX, cv2.CAP_MSMF)),
        ("AUTO", lambda: cv2.VideoCapture(USB_CAMERA_INDEX)),
    )

    for nombre_backend, crear_captura in intentos_apertura:
        print(
            f"[CAM USB] Intentando abrir cámara índice "
            f"{USB_CAMERA_INDEX} con {nombre_backend}"
        )
        captura = crear_captura()
        captura.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        captura.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        captura.set(cv2.CAP_PROP_FPS, 20)

        if captura.isOpened():
            disponible, _frame = captura.read()
            if disponible:
                print(
                    f"[CAM USB] Cámara USB detectada en índice "
                    f"{USB_CAMERA_INDEX} con {nombre_backend}"
                )
                return captura
            print(f"[CAM USB] No se pudo leer frame con {nombre_backend}")

        captura.release()

    print(
        "[CAM USB] USB CAMERA detectada por DirectShow, pero OpenCV no pudo "
        "abrirla. Verificar si está ocupada por otra aplicación o permisos de Windows."
    )
    return None


def reiniciar_presencia_vigilancia():
    """Evita conservar temporizadores si la cámara se desconecta."""
    global persona_frames_actuales, persona_frames_ausentes, presencia_confirmada
    global inicio_presencia, evento_persona_emitido, evento_permanencia_emitido
    global rostro_no_visible_frames, perfil_frames_actuales
    global espalda_frames_actuales, evento_perfil_emitido
    global rostro_no_visible_activo, permanencia_activa, transito_repetitivo_hasta
    global evento_rostro_permanencia_emitido, evento_rostro_transito_emitido
    persona_frames_actuales = 0
    persona_frames_ausentes = 0
    presencia_confirmada = False
    inicio_presencia = None
    evento_persona_emitido = False
    evento_permanencia_emitido = False
    rostro_no_visible_frames = 0
    perfil_frames_actuales = 0
    espalda_frames_actuales = 0
    evento_perfil_emitido = False
    rostro_no_visible_activo = False
    permanencia_activa = False
    transito_repetitivo_hasta = 0.0
    evento_rostro_permanencia_emitido = False
    evento_rostro_transito_emitido = False
    apariciones_persona.clear()
    with analisis_vigilancia_lock:
        estado_analisis_vigilancia["orientacion_rostro"] = "No determinado"
        estado_analisis_vigilancia["orientacion_estimada"] = "No determinada"
        estado_analisis_vigilancia["visibilidad_facial"] = "No concluyente"
        estado_analisis_vigilancia["nivel_alerta"] = "normal"


class ServicioCamaraUSB:
    """Único propietario de la cámara física y del último frame compartido."""

    def __init__(self):
        self._inicio_lock = threading.Lock()
        self._condicion = threading.Condition()
        self._ultimo_frame = None
        self._secuencia = 0
        self._disponible = False
        self._hilo = None
        self._detener = threading.Event()

    @property
    def disponible(self):
        with self._condicion:
            return self._disponible

    def iniciar(self):
        with self._inicio_lock:
            if self._hilo and self._hilo.is_alive():
                return
            self._detener.clear()
            self._hilo = threading.Thread(
                target=self._ejecutar,
                name="camara-usb-inteligente",
                daemon=True,
            )
            self._hilo.start()
            print("[CAM USB] Servicio de análisis en segundo plano iniciado")

    def detener(self):
        self._detener.set()
        with self._condicion:
            self._condicion.notify_all()
        if self._hilo and self._hilo.is_alive():
            self._hilo.join(timeout=3)

    def obtener_frame(self, secuencia_anterior=-1, timeout=5):
        with self._condicion:
            self._condicion.wait_for(
                lambda: self._secuencia != secuencia_anterior or self._detener.is_set(),
                timeout=timeout,
            )
            if self._ultimo_frame is None or self._secuencia == secuencia_anterior:
                return None
            return self._secuencia, self._ultimo_frame.copy()

    def _publicar_frame(self, frame):
        with self._condicion:
            self._ultimo_frame = frame
            self._secuencia += 1
            self._condicion.notify_all()

    def _marcar_disponible(self, disponible):
        with self._condicion:
            self._disponible = disponible
            if not disponible:
                self._ultimo_frame = None
            self._condicion.notify_all()

    def _ejecutar(self):
        while not self._detener.is_set():
            captura = abrir_camara_usb()
            if captura is None:
                self._marcar_disponible(False)
                with analisis_vigilancia_lock:
                    estado_analisis_vigilancia["disponible"] = False
                    estado_analisis_vigilancia["estado"] = "Cámara USB física no disponible"
                self._detener.wait(5)
                continue

            self._marcar_disponible(True)
            reiniciar_presencia_vigilancia()
            numero_frame = 0
            try:
                while not self._detener.is_set():
                    disponible, frame = captura.read()
                    if not disponible:
                        print(f"[CAM USB] No se pudo leer frame del índice {USB_CAMERA_INDEX}")
                        break
                    numero_frame += 1
                    frame_salida = frame
                    if numero_frame % ANALISIS_CADA_N_FRAMES == 0:
                        frame_salida = analizar_personas(frame.copy())
                    self._publicar_frame(frame_salida)
            finally:
                captura.release()
                self._marcar_disponible(False)
                reiniciar_presencia_vigilancia()
                print("[CAM USB] Captura liberada; reintentando conexión")
            self._detener.wait(2)


servicio_camara_usb = ServicioCamaraUSB()


def generar_video_usb():
    """Transmite el último frame compartido sin volver a abrir la cámara."""
    secuencia = -1
    while True:
        resultado = servicio_camara_usb.obtener_frame(secuencia)
        if resultado is None:
            if not servicio_camara_usb.disponible:
                return
            continue
        secuencia, frame = resultado
        codificado, buffer = cv2.imencode(
            ".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 75]
        )
        if not codificado:
            continue
        yield (
            b"--frame\r\n"
            b"Content-Type: image/jpeg\r\n\r\n" + buffer.tobytes() + b"\r\n"
        )


@app.route("/video_usb")
@login_requerido
@trabajador_o_admin_requerido
def video_usb():
    servicio_camara_usb.iniciar()
    if not servicio_camara_usb.disponible:
        return "Cámara USB física no disponible", 503

    return Response(
        generar_video_usb(),
        mimetype="multipart/x-mixed-replace; boundary=frame",
        headers={"Cache-Control": "no-store, no-cache, must-revalidate"},
    )


EVENTOS_VIGILANCIA_ALTO = {
    "Permanencia con rostro no visible",
    "Tránsito repetitivo con rostro no visible",
}
EVENTOS_VIGILANCIA_REVISION = {
    "Rostro no visible",
    "Persona de perfil",
    "Permanencia prolongada",
    "Tránsito repetitivo",
}


def nivel_evento_vigilancia(tipo_evento):
    if tipo_evento in EVENTOS_VIGILANCIA_ALTO:
        return "alto"
    if tipo_evento in EVENTOS_VIGILANCIA_REVISION:
        return "revision"
    return "informativo"


def obtener_eventos_vigilancia(limite=10, nivel=None, tipo=None):
    with get_db() as conn:
        rows = conn.execute("""
            SELECT id, camara, tipo_evento, descripcion, fecha_hora,
                   imagen_path, estado
            FROM eventos_vigilancia
            ORDER BY fecha_hora DESC, id DESC
            LIMIT 200
        """).fetchall()
    eventos = []
    for row in rows:
        evento = dict(row)
        evento["nivel"] = nivel_evento_vigilancia(evento["tipo_evento"])
        if nivel and nivel != "todos" and evento["nivel"] != nivel:
            continue
        if tipo and tipo != "todos" and evento["tipo_evento"] != tipo:
            continue
        eventos.append(evento)
        if len(eventos) >= limite:
            break
    return eventos


@app.route("/api/vigilancia/estado")
@login_requerido
@trabajador_o_admin_requerido
def api_vigilancia_estado():
    eventos = obtener_eventos_vigilancia(1)
    with analisis_vigilancia_lock:
        respuesta = dict(estado_analisis_vigilancia)
    respuesta["ultima_alerta"] = eventos[0] if eventos else None
    respuesta["configuracion"] = {
        "modelo": YOLO_MODEL_NAME,
        "confianza_minima": PERSONA_CONFIANZA_MINIMA,
        "cada_n_frames": ANALISIS_CADA_N_FRAMES,
        "frames_consecutivos": PERSONA_FRAMES_CONSECUTIVOS,
        "cooldown_segundos": EVENTO_VIGILANCIA_COOLDOWN,
        "permanencia_segundos": PERMANENCIA_PROLONGADA_SEGUNDOS,
        "transito_apariciones": TRANSITO_REPETITIVO_APARICIONES,
        "transito_ventana_segundos": TRANSITO_REPETITIVO_VENTANA_SEGUNDOS,
        "deteccion_rostro_activa": DETECCION_ROSTRO_ACTIVA,
        "detector_rostro": "yunet" if detector_yunet is not None else "haar",
        "deteccion_pose_activa": DETECCION_POSE_ACTIVA,
        "modelo_pose": POSE_MODEL_NAME,
        "rostro_region_superior": ROSTRO_REGION_SUPERIOR,
        "rostro_no_visible_frames": ROSTRO_NO_VISIBLE_FRAMES,
        "rostro_no_visible_cooldown": ROSTRO_NO_VISIBLE_COOLDOWN,
        "confianza_pose_minima": CONFIANZA_POSE_MINIMA,
        "confianza_rostro_minima": CONFIANZA_ROSTRO_MINIMA,
        "perfil_frames_consecutivos": PERFIL_FRAMES_CONSECUTIVOS,
        "espalda_frames_consecutivos": ESPALDA_FRAMES_CONSECUTIVOS,
    }
    return jsonify(respuesta)


@app.route("/api/vigilancia/eventos")
@login_requerido
@trabajador_o_admin_requerido
def api_vigilancia_eventos():
    try:
        limite = max(1, min(int(request.args.get("limite", 10)), 50))
    except (TypeError, ValueError):
        limite = 10
    nivel = request.args.get("nivel", "todos").strip().lower()
    if nivel not in {"todos", "alto", "revision", "informativo"}:
        nivel = "todos"
    tipo = request.args.get("tipo", "todos").strip()
    return jsonify(obtener_eventos_vigilancia(limite, nivel=nivel, tipo=tipo))


@app.route("/api/vigilancia/resumen")
@login_requerido
@trabajador_o_admin_requerido
def api_vigilancia_resumen():
    eventos = obtener_eventos_vigilancia(50)
    tipos_tarjeta = (
        ("Persona detectada", "informativo"),
        ("Permanencia prolongada", "revision"),
        ("Rostro no visible", "revision"),
        ("Tránsito repetitivo", "revision"),
    )
    tarjetas = []
    for tipo, nivel in tipos_tarjeta:
        coincidencias = [evento for evento in eventos if evento["tipo_evento"] == tipo]
        tarjetas.append({
            "tipo_evento": tipo,
            "cantidad": len(coincidencias),
            "ultima_hora": coincidencias[0]["fecha_hora"] if coincidencias else None,
            "nivel": nivel,
        })
    eventos_altos = [evento for evento in eventos if evento["nivel"] == "alto"]
    tarjetas.append({
        "tipo_evento": "Eventos de nivel alto",
        "cantidad": len(eventos_altos),
        "ultima_hora": eventos_altos[0]["fecha_hora"] if eventos_altos else None,
        "nivel": "alto",
    })
    tipos_importantes = EVENTOS_VIGILANCIA_ALTO | {"Rostro no visible"}
    ultima_importante = next(
        (evento for evento in eventos if evento["tipo_evento"] in tipos_importantes),
        None,
    )
    tipos_disponibles = sorted({evento["tipo_evento"] for evento in eventos})
    return jsonify({
        "tarjetas": tarjetas,
        "ultima_importante": ultima_importante,
        "tipos_disponibles": tipos_disponibles,
    })


@app.route("/api/vigilancia/eventos/<int:evento_id>/revisar", methods=["POST"])
@login_requerido
@trabajador_o_admin_requerido
def api_vigilancia_evento_revisar(evento_id):
    with get_db() as conn:
        cursor = conn.execute("""
            UPDATE eventos_vigilancia
            SET estado = 'revisado'
            WHERE id = ? AND estado = 'pendiente'
        """, (evento_id,))
        existe = conn.execute(
            "SELECT id, estado FROM eventos_vigilancia WHERE id = ?", (evento_id,)
        ).fetchone()
    if not existe:
        return jsonify({"error": "Evento no encontrado"}), 404
    return jsonify({"id": evento_id, "estado": existe["estado"], "actualizado": cursor.rowcount > 0})


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


@app.route("/api/estado-urbano/ruta")
def api_estado_urbano_ruta():
    """Versión pública de la última ruta de recojo: solo orden, omitidos y
    distancia (sin niveles de llenado ni datos de dispositivos)."""
    ruta = obtener_ultima_ruta_recoleccion()
    if not ruta:
        return jsonify({"ruta": None})
    return jsonify({"ruta": {
        "orden_tachos": ruta["orden_tachos"],
        "tachos_incluidos": ruta["tachos_incluidos"],
        "tachos_omitidos": ruta["tachos_omitidos"],
        "distancia_estimada": ruta["distancia_estimada"],
        "fecha_generacion": ruta["fecha_generacion"],
        "desactualizada": ruta["desactualizada"],
    }})


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
        reporte_previo = conn.execute("""
            SELECT r.estado, r.titulo, u.telefono
            FROM reportes_ciudadanos r
            LEFT JOIN usuarios u ON u.id = r.usuario_id
            WHERE r.id = ?
        """, (reporte_id,)).fetchone()

        conn.execute("""
            UPDATE reportes_ciudadanos
            SET estado = ?, observacion_admin = ?, actualizado_en = datetime('now','localtime')
            WHERE id = ?
        """, (nuevo_estado, observacion, reporte_id))

    if (reporte_previo and nuevo_estado == "atendido" and reporte_previo["estado"] != "atendido"
            and reporte_previo["telefono"]):
        mensaje = f'Tu reporte "{reporte_previo["titulo"]}" ha sido atendido por LSCC.'
        if observacion:
            mensaje += f"\nObservación: {observacion}"
        enviar_whatsapp(reporte_previo["telefono"], mensaje)

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
    servicio_camara_usb.iniciar()

    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)
