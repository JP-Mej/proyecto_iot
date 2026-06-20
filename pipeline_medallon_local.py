#!/usr/bin/env python3
"""
Pipeline medallon local para Lima Smart Core City.

Lee dashboard/lscc.db y genera un data lake local:
  datalake_local/bronze  datos crudos exportados desde SQLite
  datalake_local/silver  datos limpios y validados
  datalake_local/gold    tablas listas para Athena/Power BI

No usa AWS ni dependencias externas. La subida a S3 debe hacerse despues,
cuando los archivos gold/silver ya esten correctos.
"""

from __future__ import annotations

import argparse
import csv
import shutil
import sqlite3
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parent
DB_PATH = ROOT_DIR / "dashboard" / "lscc.db"
DATALAKE_DIR = ROOT_DIR / "datalake_local"

BRONZE_TABLES = [
    "dispositivos",
    "lecturas_ambientales",
    "lecturas_residuos",
    "lecturas_sonido",
    "imagenes_meta",
    "eventos_alerta",
    "estado_dispositivos",
    "usuarios",
    "reportes_ciudadanos",
]

VALID_AMBIENTAL_RANGES = {
    "temperatura": (-20.0, 80.0),
    "humedad": (0.0, 100.0),
    "presion": (800.0, 1200.0),
    "gas": (0.0, 5.0),
}


def connect_db(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_dirs() -> None:
    for layer in ("bronze", "silver", "gold", "backups_sqlite"):
        (DATALAKE_DIR / layer).mkdir(parents=True, exist_ok=True)


def run_id() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def today_partition() -> str:
    return datetime.now().strftime("anio=%Y/mes=%m/dia=%d")


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def to_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def to_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def add_time_columns(row: dict[str, Any], timestamp_key: str = "timestamp") -> None:
    ts = parse_timestamp(str(row.get(timestamp_key) or ""))
    row["timestamp_normalizado"] = ts.strftime("%Y-%m-%d %H:%M:%S") if ts else ""
    row["fecha"] = ts.strftime("%Y-%m-%d") if ts else ""
    row["hora"] = ts.strftime("%H:%M:%S") if ts else ""
    row["anio"] = ts.strftime("%Y") if ts else ""
    row["mes"] = ts.strftime("%m") if ts else ""
    row["dia"] = ts.strftime("%d") if ts else ""


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    ).fetchone()
    return row is not None


def export_bronze(conn: sqlite3.Connection, rid: str) -> dict[str, Path]:
    exported: dict[str, Path] = {}
    partition = today_partition()

    for table in BRONZE_TABLES:
        if not table_exists(conn, table):
            continue

        rows = [dict(r) for r in conn.execute(f"SELECT * FROM {table}").fetchall()]
        columns = [r["name"] for r in conn.execute(f"PRAGMA table_info({table})")]
        out = DATALAKE_DIR / "bronze" / table / partition / f"{rid}.csv"
        write_csv(out, rows, columns)
        exported[table] = out

    backup = DATALAKE_DIR / "backups_sqlite" / f"lscc_{rid}.db"
    shutil.copy2(DB_PATH, backup)
    return exported


def validate_ambiental(row: dict[str, Any]) -> tuple[str, str]:
    variable = str(row.get("variable") or "")
    valor = to_float(row.get("valor"))
    estado = str(row.get("estado") or "")

    if estado and estado != "ok":
        return "observado", f"estado_sensor_{estado}"
    if valor is None:
        return "invalido", "valor_vacio"
    min_value, max_value = VALID_AMBIENTAL_RANGES.get(variable, (-999999.0, 999999.0))
    if valor < min_value or valor > max_value:
        return "invalido", "fuera_de_rango"
    return "valido", ""


def build_silver(exported: dict[str, Path], rid: str) -> dict[str, Path]:
    outputs: dict[str, Path] = {}
    partition = today_partition()

    if "lecturas_ambientales" in exported:
        seen = set()
        rows = []
        for row in read_csv(exported["lecturas_ambientales"]):
            key = (row.get("device_id"), row.get("variable"), row.get("timestamp"), row.get("valor"))
            if key in seen:
                continue
            seen.add(key)
            row["valor"] = to_float(row.get("valor"))
            row["valor_raw"] = to_int(row.get("valor_raw"))
            row["voltaje"] = to_float(row.get("voltaje"))
            estado_validacion, motivo = validate_ambiental(row)
            row["estado_validacion"] = estado_validacion
            row["motivo_validacion"] = motivo
            add_time_columns(row)
            rows.append(row)

        fields = [
            "id", "device_id", "sensor", "variable", "valor", "valor_raw", "voltaje",
            "unidad", "nivel", "estado", "timestamp", "timestamp_normalizado",
            "fecha", "hora", "anio", "mes", "dia", "estado_validacion", "motivo_validacion",
        ]
        out = DATALAKE_DIR / "silver" / "lecturas_ambientales" / partition / f"{rid}.csv"
        write_csv(out, rows, fields)
        outputs["lecturas_ambientales"] = out

    if "lecturas_residuos" in exported:
        seen = set()
        rows = []
        for row in read_csv(exported["lecturas_residuos"]):
            key = (row.get("device_id"), row.get("sensor_id"), row.get("timestamp"))
            if key in seen:
                continue
            seen.add(key)
            row["sensor_id"] = to_int(row.get("sensor_id"))
            row["distancia_cm"] = to_float(row.get("distancia_cm"))
            row["porcentaje_llenado"] = to_int(row.get("porcentaje_llenado"))
            pct = row["porcentaje_llenado"]
            row["estado_validacion"] = "valido" if pct is not None and 0 <= pct <= 100 else "invalido"
            row["motivo_validacion"] = "" if row["estado_validacion"] == "valido" else "porcentaje_fuera_de_rango"
            add_time_columns(row)
            rows.append(row)

        fields = [
            "id", "device_id", "sensor_id", "distancia_cm", "porcentaje_llenado",
            "nivel", "timestamp", "timestamp_normalizado", "fecha", "hora",
            "anio", "mes", "dia", "estado_validacion", "motivo_validacion",
        ]
        out = DATALAKE_DIR / "silver" / "lecturas_residuos" / partition / f"{rid}.csv"
        write_csv(out, rows, fields)
        outputs["lecturas_residuos"] = out

    if "lecturas_sonido" in exported:
        rows = []
        for row in read_csv(exported["lecturas_sonido"]):
            row["valor_raw"] = to_int(row.get("valor_raw"))
            row["voltaje"] = to_float(row.get("voltaje"))
            row["porcentaje"] = to_int(row.get("porcentaje"))
            pct = row["porcentaje"]
            row["evento_ruido_anomalo"] = "1" if pct is not None and pct >= 75 else "0"
            row["estado_validacion"] = "valido" if row["valor_raw"] is not None else "invalido"
            add_time_columns(row)
            rows.append(row)

        fields = [
            "id", "device_id", "valor_raw", "voltaje", "porcentaje", "nivel",
            "evento", "timestamp", "timestamp_normalizado", "fecha", "hora",
            "anio", "mes", "dia", "evento_ruido_anomalo", "estado_validacion",
        ]
        out = DATALAKE_DIR / "silver" / "lecturas_sonido" / partition / f"{rid}.csv"
        write_csv(out, rows, fields)
        outputs["lecturas_sonido"] = out

    passthrough_tables = ["eventos_alerta", "reportes_ciudadanos", "imagenes_meta", "estado_dispositivos"]
    for table in passthrough_tables:
        if table not in exported:
            continue
        rows = read_csv(exported[table])
        for row in rows:
            timestamp_key = "creado_en" if table == "reportes_ciudadanos" else "timestamp"
            add_time_columns(row, timestamp_key)
        fields = list(rows[0].keys()) if rows else []
        out = DATALAKE_DIR / "silver" / table / partition / f"{rid}.csv"
        write_csv(out, rows, fields)
        outputs[table] = out

    return outputs


def avg(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 2) if values else None


def build_gold(silver: dict[str, Path], rid: str) -> dict[str, Path]:
    outputs: dict[str, Path] = {}

    if "lecturas_ambientales" in silver:
        rows = [
            r for r in read_csv(silver["lecturas_ambientales"])
            if r.get("estado_validacion") == "valido"
        ]
        grouped: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
        for row in rows:
            grouped[(row.get("fecha", ""), row.get("variable", ""))].append(row)

        gold_rows = []
        for (fecha, variable), items in sorted(grouped.items()):
            values = [v for v in (to_float(i.get("valor")) for i in items) if v is not None]
            gold_rows.append({
                "fecha": fecha,
                "variable": variable,
                "lecturas": len(values),
                "valor_promedio": avg(values),
                "valor_minimo": round(min(values), 2) if values else "",
                "valor_maximo": round(max(values), 2) if values else "",
            })

        out = DATALAKE_DIR / "gold" / "resumen_ambiental_diario.csv"
        write_csv(out, gold_rows, ["fecha", "variable", "lecturas", "valor_promedio", "valor_minimo", "valor_maximo"])
        outputs["resumen_ambiental_diario"] = out

    if "lecturas_residuos" in silver:
        rows = [
            r for r in read_csv(silver["lecturas_residuos"])
            if r.get("estado_validacion") == "valido"
        ]
        grouped: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
        for row in rows:
            grouped[(row.get("fecha", ""), row.get("sensor_id", ""))].append(row)

        gold_rows = []
        for (fecha, sensor_id), items in sorted(grouped.items()):
            values = [v for v in (to_int(i.get("porcentaje_llenado")) for i in items) if v is not None]
            latest = sorted(items, key=lambda i: i.get("timestamp_normalizado", ""))[-1] if items else {}
            gold_rows.append({
                "fecha": fecha,
                "sensor_id": sensor_id,
                "lecturas": len(values),
                "llenado_promedio": avg([float(v) for v in values]),
                "llenado_maximo": max(values) if values else "",
                "ultimo_nivel": latest.get("nivel", ""),
                "ultimo_porcentaje": latest.get("porcentaje_llenado", ""),
            })

        out = DATALAKE_DIR / "gold" / "residuos_por_contenedor_diario.csv"
        write_csv(out, gold_rows, [
            "fecha", "sensor_id", "lecturas", "llenado_promedio",
            "llenado_maximo", "ultimo_nivel", "ultimo_porcentaje",
        ])
        outputs["residuos_por_contenedor_diario"] = out

    if "lecturas_sonido" in silver:
        rows = read_csv(silver["lecturas_sonido"])
        grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
        for row in rows:
            grouped[row.get("fecha", "")].append(row)

        gold_rows = []
        for fecha, items in sorted(grouped.items()):
            pct_values = [v for v in (to_int(i.get("porcentaje")) for i in items) if v is not None]
            anomalias = sum(1 for i in items if i.get("evento_ruido_anomalo") == "1")
            gold_rows.append({
                "fecha": fecha,
                "lecturas": len(items),
                "porcentaje_promedio": avg([float(v) for v in pct_values]),
                "porcentaje_maximo": max(pct_values) if pct_values else "",
                "eventos_ruido_anomalo": anomalias,
            })

        out = DATALAKE_DIR / "gold" / "sonido_eventos_diario.csv"
        write_csv(out, gold_rows, [
            "fecha", "lecturas", "porcentaje_promedio",
            "porcentaje_maximo", "eventos_ruido_anomalo",
        ])
        outputs["sonido_eventos_diario"] = out

    if "reportes_ciudadanos" in silver:
        rows = read_csv(silver["reportes_ciudadanos"])
        grouped: dict[tuple[str, str, str], int] = defaultdict(int)
        for row in rows:
            grouped[(row.get("fecha", ""), row.get("categoria", ""), row.get("estado", ""))] += 1

        gold_rows = [
            {"fecha": fecha, "categoria": categoria, "estado": estado, "total": total}
            for (fecha, categoria, estado), total in sorted(grouped.items())
        ]
        out = DATALAKE_DIR / "gold" / "reportes_por_estado_categoria.csv"
        write_csv(out, gold_rows, ["fecha", "categoria", "estado", "total"])
        outputs["reportes_por_estado_categoria"] = out

    if "eventos_alerta" in silver:
        rows = read_csv(silver["eventos_alerta"])
        grouped: dict[tuple[str, str, str, str], int] = defaultdict(int)
        for row in rows:
            grouped[(row.get("fecha", ""), row.get("modulo", ""), row.get("prioridad", ""), row.get("estado", ""))] += 1

        gold_rows = [
            {"fecha": fecha, "modulo": modulo, "prioridad": prioridad, "estado": estado, "total": total}
            for (fecha, modulo, prioridad, estado), total in sorted(grouped.items())
        ]
        out = DATALAKE_DIR / "gold" / "alertas_por_modulo_prioridad.csv"
        write_csv(out, gold_rows, ["fecha", "modulo", "prioridad", "estado", "total"])
        outputs["alertas_por_modulo_prioridad"] = out

    write_manifest(rid, outputs)
    return outputs


def write_manifest(rid: str, outputs: dict[str, Path]) -> None:
    rows = [
        {
            "run_id": rid,
            "generado_en": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "dataset": name,
            "ruta": str(path.relative_to(ROOT_DIR)),
        }
        for name, path in sorted(outputs.items())
    ]
    write_csv(DATALAKE_DIR / "gold" / "manifest.csv", rows, ["run_id", "generado_en", "dataset", "ruta"])


def run_pipeline(db_path: Path) -> None:
    if not db_path.exists():
        raise SystemExit(f"No se encontro la base de datos: {db_path}")

    ensure_dirs()
    rid = run_id()
    with connect_db(db_path) as conn:
        bronze = export_bronze(conn, rid)
    silver = build_silver(bronze, rid)
    gold = build_gold(silver, rid)

    print("Pipeline medallon local completado")
    print(f"Run ID: {rid}")
    print(f"Bronze: {len(bronze)} datasets")
    print(f"Silver: {len(silver)} datasets")
    print(f"Gold: {len(gold)} datasets")
    print(f"Salida: {DATALAKE_DIR}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Genera bronze/silver/gold local desde SQLite.")
    parser.add_argument("--db", default=str(DB_PATH), help="Ruta al archivo SQLite lscc.db")
    args = parser.parse_args()
    run_pipeline(Path(args.db).resolve())


if __name__ == "__main__":
    main()
