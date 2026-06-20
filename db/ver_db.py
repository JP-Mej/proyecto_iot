#!/usr/bin/env python3
"""
============================================================
LIMA SMART CORE CITY — Fase 1
Script de diagnóstico de la base de datos

Uso:
    python ver_db.py              # Resumen general
    python ver_db.py temperatura  # Últimas 10 lecturas de temperatura
    python ver_db.py residuos     # Estado de los 4 contenedores
    python ver_db.py alertas      # Alertas activas
    python ver_db.py dispositivos # Estado de dispositivos
============================================================
"""

import sqlite3
import sys
from datetime import datetime

DB_PATH = "lscc.db"


def conectar():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def resumen():
    with conectar() as conn:
        print("\n" + "="*55)
        print("  LIMA SMART — Resumen de la base de datos")
        print("="*55)

        tablas = [
            ("dispositivos",         "Dispositivos registrados"),
            ("lecturas_ambientales", "Lecturas ambientales totales"),
            ("lecturas_residuos",    "Lecturas de residuos totales"),
            ("lecturas_sonido",      "Lecturas de sonido totales"),
            ("imagenes_meta",        "Metadatos de imágenes"),
            ("eventos_alerta",       "Eventos de alerta totales"),
            ("estado_dispositivos",  "Registros de estado"),
        ]

        for tabla, desc in tablas:
            try:
                cnt = conn.execute(f"SELECT COUNT(*) FROM {tabla}").fetchone()[0]
                print(f"  {desc:<35} {cnt:>6} registros")
            except Exception:
                print(f"  {desc:<35}   ??? (tabla no existe)")

        print()

        # Última lectura por módulo
        print("  Última lectura por variable:")
        variables = ["temperatura", "humedad", "presion", "gas"]
        for var in variables:
            row = conn.execute("""
                SELECT valor, unidad, nivel, estado, timestamp
                FROM lecturas_ambientales
                WHERE variable = ?
                ORDER BY timestamp DESC LIMIT 1
            """, (var,)).fetchone()
            if row:
                val = f"{row['valor']:.2f} {row['unit']}" if row["valor"] else "sin_datos"
                print(f"    {var:<15} {val:<20} [{row['timestamp'][-8:]}]")
            else:
                print(f"    {var:<15} (sin lecturas aún)")

        print()

        # Alertas activas
        cnt_alertas = conn.execute(
            "SELECT COUNT(*) FROM eventos_alerta WHERE estado='activa'"
        ).fetchone()[0]
        print(f"  Alertas activas: {cnt_alertas}")
        print("="*55 + "\n")


def ver_temperatura(variable="temperatura", limite=10):
    with conectar() as conn:
        rows = conn.execute("""
            SELECT timestamp, valor, unidad, nivel, estado
            FROM lecturas_ambientales
            WHERE variable = ?
            ORDER BY timestamp DESC LIMIT ?
        """, (variable, limite)).fetchall()

    print(f"\n  Últimas {limite} lecturas de {variable}:")
    print(f"  {'Timestamp':<22} {'Valor':>10} {'Unidad':<8} {'Nivel':<12} {'Estado'}")
    print("  " + "-"*65)
    for r in rows:
        val = f"{r['valor']:.2f}" if r["valor"] is not None else "N/A"
        niv = r["nivel"] or "-"
        print(f"  {r['timestamp']:<22} {val:>10} {r['unidad']:<8} {niv:<12} {r['estado']}")
    print()


def ver_residuos():
    with conectar() as conn:
        rows = conn.execute("""
            SELECT sensor_id,
                   distancia_cm,
                   porcentaje_llenado,
                   nivel,
                   timestamp
            FROM lecturas_residuos
            WHERE id IN (
                SELECT MAX(id) FROM lecturas_residuos
                GROUP BY sensor_id
            )
            ORDER BY sensor_id
        """).fetchall()

    print("\n  Estado actual de contenedores (última lectura):")
    print(f"  {'Sensor':<10} {'Distancia':>10} {'Llenado':>10} {'Nivel':<12} {'Timestamp'}")
    print("  " + "-"*65)
    for r in rows:
        dist = f"{r['distancia_cm']:.1f} cm" if r["distancia_cm"] else "N/A"
        pct  = f"{r['porcentaje_llenado']}%"  if r["porcentaje_llenado"] is not None else "N/A"
        print(f"  {r['sensor_id']:<10} {dist:>10} {pct:>10} {r['nivel']:<12} {r['timestamp']}")
    print()


def ver_alertas():
    with conectar() as conn:
        rows = conn.execute("""
            SELECT device_id, modulo, tipo_alerta, descripcion,
                   prioridad, estado, timestamp
            FROM eventos_alerta
            WHERE estado = 'activa'
            ORDER BY timestamp DESC LIMIT 20
        """).fetchall()

    print(f"\n  Alertas activas ({len(rows)}):")
    if not rows:
        print("  ✅ Sin alertas activas")
    for r in rows:
        print(f"  [{r['prioridad'].upper():<6}] {r['tipo_alerta']:<20} "
              f"{r['device_id']:<20} {r['timestamp'][-8:]}")
        if r["descripcion"]:
            print(f"         → {r['descripcion']}")
    print()


def ver_dispositivos():
    with conectar() as conn:
        rows = conn.execute("""
            SELECT d.device_id, d.modulo, d.ultima_vez,
                   e.status
            FROM dispositivos d
            LEFT JOIN estado_dispositivos e ON e.id = (
                SELECT MAX(id) FROM estado_dispositivos
                WHERE device_id = d.device_id
            )
        """).fetchall()

    print("\n  Dispositivos registrados:")
    print(f"  {'Device ID':<25} {'Módulo':<15} {'Status':<12} {'Última vez'}")
    print("  " + "-"*70)
    for r in rows:
        status = r["status"] or "sin_registro"
        ultima = r["ultima_vez"] or "nunca"
        icono  = "🟢" if status == "online" else "🔴"
        print(f"  {icono} {r['device_id']:<23} {r['modulo']:<15} {status:<12} {ultima}")
    print()


# ============================================================
# MAIN
# ============================================================
if __name__ == "__main__":
    arg = sys.argv[1].lower() if len(sys.argv) > 1 else "resumen"

    mapa = {
        "temperatura": lambda: ver_temperatura("temperatura"),
        "humedad":     lambda: ver_temperatura("humedad"),
        "presion":     lambda: ver_temperatura("presion"),
        "gas":         lambda: ver_temperatura("gas"),
        "residuos":    ver_residuos,
        "alertas":     ver_alertas,
        "dispositivos": ver_dispositivos,
        "resumen":     resumen,
    }

    fn = mapa.get(arg)
    if fn:
        fn()
    else:
        print(f"Opción '{arg}' no reconocida.")
        print("Uso: python ver_db.py [resumen|temperatura|humedad|presion|gas|residuos|alertas|dispositivos]")
