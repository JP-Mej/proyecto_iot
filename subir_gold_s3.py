#!/usr/bin/env python3
"""
Subida controlada de la capa gold local a Amazon S3.

Por seguridad, el script corre en modo simulacion por defecto.
Para subir realmente archivos se debe usar --execute.

Ejemplos:
  python subir_gold_s3.py --bucket mi-bucket-lscc
  python subir_gold_s3.py --bucket mi-bucket-lscc --execute
  python subir_gold_s3.py --bucket mi-bucket-lscc --prefix gold/lscc --region us-east-2 --execute
"""

from __future__ import annotations

import argparse
import mimetypes
from datetime import datetime
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent
GOLD_DIR = ROOT_DIR / "datalake_local" / "gold"
DEFAULT_REGION = "us-east-2"
DEFAULT_PREFIX = "gold"


def normalize_prefix(prefix: str) -> str:
    return prefix.strip().strip("/")


def list_gold_files(gold_dir: Path) -> list[Path]:
    if not gold_dir.exists():
        raise SystemExit(f"No existe la carpeta gold: {gold_dir}")

    files = sorted(p for p in gold_dir.rglob("*") if p.is_file())
    if not files:
        raise SystemExit(f"No hay archivos para subir en: {gold_dir}")
    return files


def s3_key_for(path: Path, gold_dir: Path, prefix: str, layout: str) -> str:
    relative = path.relative_to(gold_dir).as_posix()
    clean_prefix = normalize_prefix(prefix)
    if layout == "athena":
        dataset = path.stem
        relative = f"{dataset}/{path.name}"
    return f"{clean_prefix}/{relative}" if clean_prefix else relative


def content_type_for(path: Path) -> str:
    guessed, _ = mimetypes.guess_type(path.name)
    if guessed:
        return guessed
    if path.suffix.lower() == ".csv":
        return "text/csv"
    return "application/octet-stream"


def print_plan(bucket: str, region: str, prefix: str, gold_dir: Path, files: list[Path], layout: str) -> None:
    total_bytes = sum(p.stat().st_size for p in files)
    print("Plan de subida a S3")
    print(f"Bucket: {bucket}")
    print(f"Region: {region}")
    print(f"Prefijo: s3://{bucket}/{normalize_prefix(prefix)}/")
    print(f"Layout: {layout}")
    print(f"Archivos: {len(files)}")
    print(f"Tamano total: {total_bytes} bytes")
    print()
    for path in files:
        print(f"- {path.relative_to(ROOT_DIR)} -> s3://{bucket}/{s3_key_for(path, gold_dir, prefix, layout)}")


def upload_files(bucket: str, region: str, prefix: str, gold_dir: Path, files: list[Path], layout: str) -> None:
    try:
        import boto3
        from botocore.exceptions import BotoCoreError, ClientError
    except ImportError as exc:
        raise SystemExit(
            "Falta boto3. Instala dependencias con: pip install -r requirements_aws.txt"
        ) from exc

    session = boto3.session.Session(region_name=region)
    s3 = session.client("s3")

    uploaded = 0
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for path in files:
        key = s3_key_for(path, gold_dir, prefix, layout)
        extra_args = {
            "ContentType": content_type_for(path),
            "ServerSideEncryption": "AES256",
            "Metadata": {
                "lscc-layer": "gold",
                "uploaded-at": generated_at,
            },
        }
        try:
            s3.upload_file(str(path), bucket, key, ExtraArgs=extra_args)
        except (BotoCoreError, ClientError) as exc:
            raise SystemExit(f"Error subiendo {path.name} a s3://{bucket}/{key}: {exc}") from exc
        uploaded += 1
        print(f"Subido: s3://{bucket}/{key}")

    print()
    print(f"Subida completada: {uploaded} archivos.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Sube datalake_local/gold a Amazon S3.")
    parser.add_argument("--bucket", required=True, help="Nombre del bucket S3 destino.")
    parser.add_argument("--region", default=DEFAULT_REGION, help="Region AWS. Por defecto: us-east-2.")
    parser.add_argument("--prefix", default=DEFAULT_PREFIX, help="Prefijo/carpeta dentro del bucket. Por defecto: gold.")
    parser.add_argument("--gold-dir", default=str(GOLD_DIR), help="Carpeta local gold a subir.")
    parser.add_argument(
        "--layout",
        choices=["athena", "flat"],
        default="athena",
        help="athena sube cada CSV a gold/nombre_tabla/archivo.csv. flat sube todo directo a gold/.",
    )
    parser.add_argument("--execute", action="store_true", help="Ejecuta la subida real. Sin esto solo muestra el plan.")
    args = parser.parse_args()

    gold_dir = Path(args.gold_dir).resolve()
    files = list_gold_files(gold_dir)

    print_plan(args.bucket, args.region, args.prefix, gold_dir, files, args.layout)
    if not args.execute:
        print()
        print("Modo simulacion. No se subio nada.")
        print("Para subir realmente usa: --execute")
        return

    print()
    upload_files(args.bucket, args.region, args.prefix, gold_dir, files, args.layout)


if __name__ == "__main__":
    main()
