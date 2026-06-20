#!/usr/bin/env python3
"""
============================================================
LIMA SMART CORE CITY — Fase 1
Script de inicialización de la base de datos SQLite local

Ejecutar UNA VEZ antes de iniciar el dashboard:
    python crear_db.py

Crea el archivo lscc.db con todas las tablas, índices
y registros iniciales de dispositivos.
============================================================
"""

import sqlite3
import os
from datetime import datetime

DB_PATH = "lscc.db"


def crear_base_de_datos():
    # Si ya existe, hacer backup y recrear
    if os.path.exists(DB_PATH):
        backup = DB_PATH.replace(".db", "_backup.db")
        respuesta = input(f"[DB] '{DB_PATH}' ya existe. ¿Recrear? (s/n): ").strip().lower()
        if respuesta != 's':
            print("[DB] Operación cancelada. Base de datos sin cambios.")
            return
        os.replace(DB_PATH, backup)
        print(f"[DB] Backup guardado en '{backup}'")

    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()

    # Habilitar claves foráneas y WAL (mejor rendimiento concurrente)
    cur.execute("PRAGMA foreign_keys = ON;")
    cur.execute("PRAGMA journal_mode = WAL;")

    print("[DB] Creando tablas...")

    # ----------------------------------------------------------
    # 1. DISPOSITIVOS — Tabla maestra de nodos IoT
    # ----------------------------------------------------------
    cur.execute("""
        CREATE TABLE IF NOT EXISTS dispositivos (
            device_id    TEXT PRIMARY KEY,
            modulo       TEXT NOT NULL
                         CHECK(modulo IN ('ambiental','residuos','vigilancia','sistema')),
            descripcion  TEXT,
            activo       INTEGER NOT NULL DEFAULT 1,
            creado_en    TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
            ultima_vez   TEXT
        );
    """)

    # ----------------------------------------------------------
    # 2. LECTURAS AMBIENTALES — DHT22, BMP280, MQ-2
    # ----------------------------------------------------------
    cur.execute("""
        CREATE TABLE IF NOT EXISTS lecturas_ambientales (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id  TEXT    NOT NULL REFERENCES dispositivos(device_id),
            sensor     TEXT    NOT NULL,   -- 'DHT22', 'BMP280', 'MQ-2'
            variable   TEXT    NOT NULL,   -- 'temperatura', 'humedad', 'presion', 'gas'
            valor      REAL,              -- NULL si estado=sin_datos
            valor_raw  INTEGER,           -- para MQ-2: valor ADC crudo
            voltaje    REAL,              -- para MQ-2: voltaje calculado
            unidad     TEXT,              -- 'C', '%HR', 'hPa', 'V'
            nivel      TEXT,              -- 'normal','preventivo','elevado' (solo gas)
            estado     TEXT    NOT NULL DEFAULT 'ok'
                       CHECK(estado IN ('ok','sin_datos','calentando','error')),
            timestamp  TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
        );
    """)

    # ----------------------------------------------------------
    # 3. LECTURAS DE RESIDUOS — HC-SR04 × 4
    # ----------------------------------------------------------
    cur.execute("""
        CREATE TABLE IF NOT EXISTS lecturas_residuos (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id           TEXT    NOT NULL REFERENCES dispositivos(device_id),
            sensor_id           INTEGER NOT NULL CHECK(sensor_id BETWEEN 1 AND 4),
            distancia_cm        REAL,
            porcentaje_llenado  INTEGER,
            nivel               TEXT    CHECK(nivel IN ('bajo','medio','alto','sin_datos')),
            timestamp           TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
        );
    """)

    # ----------------------------------------------------------
    # 4. LECTURAS DE SONIDO — KY-037
    # ----------------------------------------------------------
    cur.execute("""
        CREATE TABLE IF NOT EXISTS lecturas_sonido (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id   TEXT    NOT NULL REFERENCES dispositivos(device_id),
            valor_raw   INTEGER NOT NULL,
            voltaje     REAL,
            porcentaje  INTEGER,
            nivel       TEXT    CHECK(nivel IN ('bajo','medio','alto')),
            evento      TEXT,    -- 'sonido_detectado' o 'sin_sonido_relevante'
            timestamp   TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
        );
    """)

    # ----------------------------------------------------------
    # 5. METADATA DE IMÁGENES — ESP32-CAM
    # ----------------------------------------------------------
    cur.execute("""
        CREATE TABLE IF NOT EXISTS imagenes_meta (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id    TEXT    NOT NULL REFERENCES dispositivos(device_id),
            width        INTEGER,
            height       INTEGER,
            size_bytes   INTEGER,
            trigger_tipo TEXT,
            ruta_archivo TEXT,    -- ruta local del JPEG guardado
            timestamp    TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
        );
    """)

    # ----------------------------------------------------------
    # 6. EVENTOS DE ALERTA — Todas las fuentes
    # ----------------------------------------------------------
    cur.execute("""
        CREATE TABLE IF NOT EXISTS eventos_alerta (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id    TEXT    NOT NULL REFERENCES dispositivos(device_id),
            modulo       TEXT    NOT NULL,
            tipo_alerta  TEXT    NOT NULL,  -- 'gas_elevado','contenedor_alto','sin_datos',etc.
            descripcion  TEXT,
            prioridad    TEXT    NOT NULL DEFAULT 'media'
                         CHECK(prioridad IN ('alta','media','baja')),
            estado       TEXT    NOT NULL DEFAULT 'activa'
                         CHECK(estado IN ('activa','resuelta')),
            timestamp    TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
            resuelto_en  TEXT
        );
    """)

    # ----------------------------------------------------------
    # 7. ESTADO DE DISPOSITIVOS — Heartbeat / última conexión
    # ----------------------------------------------------------
    cur.execute("""
        CREATE TABLE IF NOT EXISTS estado_dispositivos (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id TEXT    NOT NULL REFERENCES dispositivos(device_id),
            modulo    TEXT,
            status    TEXT    NOT NULL CHECK(status IN ('online','offline','sin_datos','error')),
            detalle   TEXT,    -- JSON extra del mensaje de status
            timestamp TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
        );
    """)

    # ----------------------------------------------------------
    # 9. REPORTES CIUDADANOS — Incidencias enviadas por usuarios
    # ----------------------------------------------------------
    cur.execute("""
        CREATE TABLE IF NOT EXISTS reportes_ciudadanos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id INTEGER NOT NULL,
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
            FOREIGN KEY(usuario_id) REFERENCES usuarios(id)
        );
    """)

    # ----------------------------------------------------------
    # ÍNDICES para consultas rápidas por tiempo y dispositivo
    # ----------------------------------------------------------
    indices = [
        "CREATE INDEX IF NOT EXISTS idx_amb_ts   ON lecturas_ambientales(timestamp DESC);",
        "CREATE INDEX IF NOT EXISTS idx_amb_dev  ON lecturas_ambientales(device_id, variable, timestamp DESC);",
        "CREATE INDEX IF NOT EXISTS idx_res_ts   ON lecturas_residuos(timestamp DESC);",
        "CREATE INDEX IF NOT EXISTS idx_res_sid  ON lecturas_residuos(sensor_id, timestamp DESC);",
        "CREATE INDEX IF NOT EXISTS idx_son_ts   ON lecturas_sonido(timestamp DESC);",
        "CREATE INDEX IF NOT EXISTS idx_img_ts   ON imagenes_meta(timestamp DESC);",
        "CREATE INDEX IF NOT EXISTS idx_alt_est  ON eventos_alerta(estado, timestamp DESC);",
        "CREATE INDEX IF NOT EXISTS idx_alt_mod  ON eventos_alerta(modulo, tipo_alerta, timestamp DESC);",
        "CREATE INDEX IF NOT EXISTS idx_est_dev  ON estado_dispositivos(device_id, timestamp DESC);",
    ]
    for idx in indices:
        cur.execute(idx)

    # ----------------------------------------------------------
    # REGISTROS INICIALES — Dispositivos del proyecto
    # ----------------------------------------------------------
    dispositivos_iniciales = [
        ("ESP32_AIRE_01",    "ambiental",   "ESP32 módulo ambiental — DHT22 + BMP280 + MQ-2"),
        ("ESP32_RESIDUOS_01","residuos",    "ESP32 módulo residuos — 4x HC-SR04"),
        ("ESP32_CAM_01",     "vigilancia",  "ESP32-CAM módulo vigilancia — OV2640"),
        ("ESP32_KY037_01",   "vigilancia",  "ESP32 módulo sonido — KY-037"),
    ]
    cur.executemany("""
        INSERT OR IGNORE INTO dispositivos (device_id, modulo, descripcion)
        VALUES (?, ?, ?);
    """, dispositivos_iniciales)

    conn.commit()
    conn.close()

    print(f"[DB] Base de datos '{DB_PATH}' creada exitosamente.")
    print("[DB] Tablas creadas:")
    print("       • dispositivos")
    print("       • lecturas_ambientales")
    print("       • lecturas_residuos")
    print("       • lecturas_sonido")
    print("       • imagenes_meta")
    print("       • eventos_alerta")
    print("       • estado_dispositivos")
    print("[DB] Índices creados para consultas rápidas.")
    print(f"[DB] {len(dispositivos_iniciales)} dispositivos registrados.")
    print()
    print("✅  Listo. Ahora puedes iniciar el dashboard con: python app.py")


if __name__ == "__main__":
    # Mantener este acceso por compatibilidad, usando el inicializador canónico.
    import runpy
    from pathlib import Path
    runpy.run_path(
        str(Path(__file__).resolve().parent.parent / "dashboard" / "crear_db.py"),
        run_name="__main__"
    )
