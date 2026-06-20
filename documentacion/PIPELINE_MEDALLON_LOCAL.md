# Pipeline medallon local LSCC

Este pipeline procesa los datos IoT sin gastar recursos de AWS.

## Objetivo

Mantener SQLite como fuente local y generar tres capas ordenadas:

```text
dashboard/lscc.db
  -> datalake_local/bronze
  -> datalake_local/silver
  -> datalake_local/gold
```

Luego se suben a AWS principalmente los archivos de `gold` y, si se desea,
algunos archivos de `silver`.

## Capas

### Bronze

Datos crudos exportados desde SQLite.

Ruta:

```text
datalake_local/bronze/
```

Tambien se crea una copia de respaldo de SQLite en:

```text
datalake_local/backups_sqlite/
```

### Silver

Datos limpios y validados:

- timestamps normalizados
- columnas de fecha, hora, anio, mes y dia
- valores numericos convertidos
- duplicados simples eliminados
- estados de validacion agregados

Ruta:

```text
datalake_local/silver/
```

### Gold

Tablas listas para Athena y Power BI:

- `resumen_ambiental_diario.csv`
- `residuos_por_contenedor_diario.csv`
- `sonido_eventos_diario.csv`
- `reportes_por_estado_categoria.csv`
- `alertas_por_modulo_prioridad.csv`
- `manifest.csv`

Ruta:

```text
datalake_local/gold/
```

## Ejecucion

Desde la raiz del proyecto:

```powershell
python pipeline_medallon_local.py
```

Si se desea indicar otra base SQLite:

```powershell
python pipeline_medallon_local.py --db dashboard/lscc.db
```

## Frecuencia recomendada

Para cuidar creditos:

- Ejecutar medallon local cada 15, 30 o 60 minutos.
- Subir `gold` a S3 cada 30 o 60 minutos.
- Subir backup SQLite una vez al dia.
- No subir todas las fotos de la camara cada 10 segundos.
- Subir imagenes solo si estan asociadas a eventos importantes.

## Siguiente fase

Estado actual:

- Pipeline local validado.
- Bucket S3 creado: `lscc-datalake-fisi-347011900597`.
- Capa `gold` subida a S3.
- Athena configurado con database `lscc_gold`.
- Tablas externas creadas y validadas.

Flujo operativo recomendado:

```powershell
python pipeline_medallon_local.py
python subir_gold_s3.py --bucket lscc-datalake-fisi-347011900597 --layout athena --execute
```

Cuando cambie la estructura de las tablas Gold, ejecutar:

```powershell
python ejecutar_athena_gold.py
```

Si solo cambian los datos CSV y no cambian las columnas, no hace falta recrear
las tablas Athena.

Siguiente fase:

1. Instalar Amazon Athena ODBC Driver.
2. Crear DSN ODBC `LSCC_Athena`.
3. Conectar Power BI en modo Import.
4. Construir visualizaciones.
