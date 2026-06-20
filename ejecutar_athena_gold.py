#!/usr/bin/env python3
"""
Ejecuta el SQL de creacion de tablas Gold en Amazon Athena.

Usa el archivo athena_gold_tables.sql y guarda resultados de Athena en:
  s3://lscc-datalake-fisi-347011900597/athena-results/
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent
DEFAULT_SQL = ROOT_DIR / "athena_gold_tables.sql"
DEFAULT_OUTPUT = "s3://lscc-datalake-fisi-347011900597/athena-results/"
DEFAULT_REGION = "us-east-2"
DEFAULT_WORKGROUP = "primary"


def load_statements(path: Path) -> list[str]:
    sql = path.read_text(encoding="utf-8")
    statements = []
    current = []
    for line in sql.splitlines():
        stripped = line.strip()
        if stripped.startswith("--"):
            continue
        current.append(line)
        if stripped.endswith(";"):
            statement = "\n".join(current).strip().rstrip(";").strip()
            if statement:
                statements.append(statement)
            current = []
    tail = "\n".join(current).strip()
    if tail:
        statements.append(tail)
    return statements


def wait_for_query(athena, query_id: str) -> None:
    while True:
        result = athena.get_query_execution(QueryExecutionId=query_id)
        status = result["QueryExecution"]["Status"]
        state = status["State"]
        if state == "SUCCEEDED":
            return
        if state in {"FAILED", "CANCELLED"}:
            reason = status.get("StateChangeReason", "sin detalle")
            raise SystemExit(f"Consulta Athena {query_id} termino en {state}: {reason}")
        time.sleep(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Crea tablas Gold en Athena.")
    parser.add_argument("--sql", default=str(DEFAULT_SQL), help="Archivo SQL a ejecutar.")
    parser.add_argument("--region", default=DEFAULT_REGION, help="Region AWS.")
    parser.add_argument("--output", default=DEFAULT_OUTPUT, help="S3 output location de Athena.")
    parser.add_argument("--workgroup", default=DEFAULT_WORKGROUP, help="Workgroup Athena.")
    args = parser.parse_args()

    try:
        import boto3
    except ImportError as exc:
        raise SystemExit("Falta boto3. Instala con: pip install -r requirements_aws.txt") from exc

    statements = load_statements(Path(args.sql))
    if not statements:
        raise SystemExit("No se encontraron sentencias SQL para ejecutar.")

    athena = boto3.client("athena", region_name=args.region)
    print(f"Ejecutando {len(statements)} sentencias en Athena...")

    for index, statement in enumerate(statements, start=1):
        preview = " ".join(statement.split())[:90]
        response = athena.start_query_execution(
            QueryString=statement,
            ResultConfiguration={"OutputLocation": args.output},
            WorkGroup=args.workgroup,
        )
        query_id = response["QueryExecutionId"]
        wait_for_query(athena, query_id)
        print(f"{index}. OK {query_id} :: {preview}")

    print("Tablas Gold listas en Athena.")


if __name__ == "__main__":
    main()
