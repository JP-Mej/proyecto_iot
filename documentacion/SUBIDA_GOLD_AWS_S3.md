# Subida controlada de Gold a AWS S3

Este paso sube solo la capa `gold` del medallon local a Amazon S3.
La idea es cuidar creditos y evitar subir datos crudos, fotos constantes o
archivos grandes sin necesidad.

## Flujo

```text
SQLite local
  -> pipeline_medallon_local.py
  -> datalake_local/gold
  -> subir_gold_s3.py
  -> Amazon S3
  -> Athena
  -> Power BI
```

## 1. Crear bucket S3

Bucket creado para el proyecto:

```text
lscc-datalake-fisi-347011900597
```

Region:

```text
us-east-2
```

Configuracion aplicada:

- Block all public access: activado.
- Server-side encryption: SSE-S3.
- Versioning: desactivado al inicio para ahorrar.

Si se necesita recrear en otra cuenta, crear un bucket privado con un nombre
equivalente.

Nombre usado:

```text
lscc-datalake-fisi-347011900597
```

Configuracion recomendada:

- Block all public access: activado.
- Versioning: desactivado al inicio para ahorrar.
- Server-side encryption: SSE-S3.
- Lifecycle: opcional, borrar versiones antiguas luego de 90 o 180 dias.

## 2. Crear usuario IAM con permisos minimos

Usuario IAM usado:

```text
iot-IAM
```

Para subir Gold a S3, el usuario necesita como minimo:

Permisos minimos:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:ListBucket"
      ],
      "Resource": "arn:aws:s3:::NOMBRE_DEL_BUCKET"
    },
    {
      "Effect": "Allow",
      "Action": [
        "s3:PutObject",
        "s3:GetObject"
      ],
      "Resource": "arn:aws:s3:::NOMBRE_DEL_BUCKET/*"
    }
  ]
}
```

Reemplazar `NOMBRE_DEL_BUCKET` por el bucket real.

No usar `AdministratorAccess` para el proyecto.

## 3. Instalar dependencia local

Desde la raiz del proyecto:

```powershell
pip install -r requirements_aws.txt
```

## 4. Configurar credenciales

Opcion recomendada:

```powershell
aws configure
```

Valores:

```text
AWS Access Key ID: clave del usuario IAM
AWS Secret Access Key: secreto del usuario IAM
Default region name: us-east-2
Default output format: json
```

Tambien se puede usar `AWS_PROFILE` si hay varios perfiles configurados.

## 5. Simular subida

Primero ejecutar sin `--execute`.

```powershell
python subir_gold_s3.py --bucket lscc-datalake-fisi-347011900597
```

Esto solo muestra que archivos se subirian.

## 6. Subir realmente

Cuando el plan se vea correcto:

```powershell
python subir_gold_s3.py --bucket lscc-datalake-fisi-347011900597 --layout athena --execute
```

Por defecto sube a:

```text
s3://lscc-datalake-fisi-347011900597/gold/
```

Con `--layout athena`, cada CSV se sube a su propia carpeta:

```text
s3://lscc-datalake-fisi-347011900597/gold/resumen_ambiental_diario/resumen_ambiental_diario.csv
s3://lscc-datalake-fisi-347011900597/gold/residuos_por_contenedor_diario/residuos_por_contenedor_diario.csv
s3://lscc-datalake-fisi-347011900597/gold/sonido_eventos_diario/sonido_eventos_diario.csv
s3://lscc-datalake-fisi-347011900597/gold/reportes_por_estado_categoria/reportes_por_estado_categoria.csv
s3://lscc-datalake-fisi-347011900597/gold/alertas_por_modulo_prioridad/alertas_por_modulo_prioridad.csv
```

Con prefijo personalizado:

```powershell
python subir_gold_s3.py --bucket lscc-datalake-fisi-347011900597 --prefix lscc/gold --layout athena --execute
```

## Recomendacion de frecuencia

Para cuidar creditos:

- Ejecutar `pipeline_medallon_local.py` cada 30 o 60 minutos.
- Subir `gold` cada 30 o 60 minutos.
- Subir `silver` solo si Athena necesita detalle.
- Subir backup SQLite una vez al dia.
- No subir imagenes cada 10 segundos.

## Siguiente paso

Estado actual:

- Gold ya esta en S3.
- Athena ya tiene database `lscc_gold`.
- Las tablas externas ya fueron creadas y validadas.

Siguiente paso:

1. Instalar Amazon Athena ODBC Driver.
2. Crear DSN `LSCC_Athena`.
3. Conectar Power BI a Athena.
