# Athena para la capa Gold LSCC

Athena permite consultar los CSV de S3 con SQL. Power BI se conectara a
Athena para leer las tablas `gold`.

## Estado actual

Ya esta configurado:

- Bucket S3: `lscc-datalake-fisi-347011900597`
- Region: `us-east-2`
- Capa Gold subida a S3 en estructura compatible con Athena
- Database Athena: `lscc_gold`
- Workgroup Athena: `primary`
- Carpeta de resultados: `s3://lscc-datalake-fisi-347011900597/athena-results/`
- Tablas externas creadas y validadas

Validacion realizada:

```text
resumen_ambiental_diario              5 filas
residuos_por_contenedor_diario        7 filas
sonido_eventos_diario                 0 filas
alertas_por_modulo_prioridad          3 filas
reportes_por_estado_categoria         1 fila
```

La consulta de validacion escaneo 852 bytes.

## Estructura S3 correcta para Athena

Cada tabla debe tener su propia carpeta:

```text
s3://lscc-datalake-fisi-347011900597/gold/
  resumen_ambiental_diario/
    resumen_ambiental_diario.csv
  residuos_por_contenedor_diario/
    residuos_por_contenedor_diario.csv
  sonido_eventos_diario/
    sonido_eventos_diario.csv
  reportes_por_estado_categoria/
    reportes_por_estado_categoria.csv
  alertas_por_modulo_prioridad/
    alertas_por_modulo_prioridad.csv
  manifest/
    manifest.csv
```

Esta estructura ya se genera con:

```powershell
python subir_gold_s3.py --bucket lscc-datalake-fisi-347011900597 --layout athena --execute
```

## Permisos necesarios para iot-IAM

El usuario `iot-IAM` debe tener esta policy adjunta:

Nombre sugerido:

```text
LSCCAthenaGoldPolicy
```

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AthenaQueryAccess",
      "Effect": "Allow",
      "Action": [
        "athena:StartQueryExecution",
        "athena:GetQueryExecution",
        "athena:GetQueryResults",
        "athena:ListWorkGroups",
        "athena:GetWorkGroup",
        "athena:ListDataCatalogs",
        "athena:GetDataCatalog",
        "athena:ListDatabases",
        "athena:ListTableMetadata",
        "athena:GetTableMetadata"
      ],
      "Resource": "*"
    },
    {
      "Sid": "GlueCatalogAccess",
      "Effect": "Allow",
      "Action": [
        "glue:CreateDatabase",
        "glue:GetDatabase",
        "glue:GetDatabases",
        "glue:CreateTable",
        "glue:GetTable",
        "glue:GetTables",
        "glue:UpdateTable"
      ],
      "Resource": "*"
    },
    {
      "Sid": "S3AthenaGoldAndResults",
      "Effect": "Allow",
      "Action": [
        "s3:GetBucketLocation",
        "s3:GetObject",
        "s3:PutObject",
        "s3:ListBucket",
        "s3:AbortMultipartUpload",
        "s3:ListMultipartUploadParts"
      ],
      "Resource": [
        "arn:aws:s3:::lscc-datalake-fisi-347011900597",
        "arn:aws:s3:::lscc-datalake-fisi-347011900597/*"
      ]
    }
  ]
}
```

## Carpeta de resultados de Athena

Athena guarda resultados de consultas en S3. Usaremos:

```text
s3://lscc-datalake-fisi-347011900597/athena-results/
```

## Crear tablas

El archivo SQL ya esta en:

```text
athena_gold_tables.sql
```

Para crear o recrear las tablas desde la raiz del proyecto:

```powershell
python ejecutar_athena_gold.py
```

Este script ejecuta las sentencias de `athena_gold_tables.sql` una por una.

Salida esperada:

```text
Tablas Gold listas en Athena.
```

## Consultas de prueba

```sql
SELECT * FROM lscc_gold.resumen_ambiental_diario LIMIT 10;
SELECT * FROM lscc_gold.residuos_por_contenedor_diario LIMIT 10;
SELECT * FROM lscc_gold.sonido_eventos_diario LIMIT 10;
SELECT * FROM lscc_gold.alertas_por_modulo_prioridad LIMIT 10;
SELECT * FROM lscc_gold.reportes_por_estado_categoria LIMIT 10;
```

Consulta de conteo recomendada:

```sql
SELECT 'resumen_ambiental_diario' tabla, count(*) total
FROM lscc_gold.resumen_ambiental_diario
UNION ALL
SELECT 'residuos_por_contenedor_diario', count(*)
FROM lscc_gold.residuos_por_contenedor_diario
UNION ALL
SELECT 'sonido_eventos_diario', count(*)
FROM lscc_gold.sonido_eventos_diario
UNION ALL
SELECT 'alertas_por_modulo_prioridad', count(*)
FROM lscc_gold.alertas_por_modulo_prioridad
UNION ALL
SELECT 'reportes_por_estado_categoria', count(*)
FROM lscc_gold.reportes_por_estado_categoria;
```

## Conexion con Power BI

Si Power BI muestra este error:

```text
not authorized to perform: athena:ListDataCatalogs
```

significa que la policy `LSCCAthenaGoldPolicy` no tiene todavia permisos de
catalogo/metadata de Athena o que la policy no esta adjunta al usuario
`iot-IAM`. Confirmar que el bloque `AthenaQueryAccess` incluya:

```text
athena:ListDataCatalogs
athena:GetDataCatalog
athena:ListDatabases
athena:ListTableMetadata
athena:GetTableMetadata
```

Para probar desde PowerShell:

```powershell
aws athena list-data-catalogs --region us-east-2
```

Si ese comando funciona, Power BI ya deberia poder listar catalogos y tablas.

En Power BI Desktop:

1. Instalar Amazon Athena ODBC Driver para Windows.
2. Abrir `ODBC Data Sources (64-bit)`.
3. Crear un System DSN llamado `LSCC_Athena`.
4. Configurar:
   - Region: `us-east-2`
   - S3 Output Location: `s3://lscc-datalake-fisi-347011900597/athena-results/`
   - Workgroup: `primary`
   - Catalog: `AwsDataCatalog`
   - Database: `lscc_gold`
   - Autenticacion: perfil AWS `default` o credenciales IAM
5. Abrir Power BI Desktop.
6. Inicio -> Obtener datos -> Amazon Athena.
7. DSN: `LSCC_Athena`.
8. Modo: `Import`.
9. Seleccionar tablas de `lscc_gold`.

Para empezar, usar modo Import. DirectQuery puede generar mas consultas y
por tanto mas costo.

Tablas recomendadas para Power BI:

- `resumen_ambiental_diario`
- `residuos_por_contenedor_diario`
- `sonido_eventos_diario`
- `alertas_por_modulo_prioridad`
- `reportes_por_estado_categoria`

La tabla `manifest` se usa principalmente para control tecnico.
