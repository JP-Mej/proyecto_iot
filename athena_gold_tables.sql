CREATE DATABASE IF NOT EXISTS lscc_gold;

CREATE EXTERNAL TABLE IF NOT EXISTS lscc_gold.resumen_ambiental_diario (
  fecha string,
  variable string,
  lecturas int,
  valor_promedio double,
  valor_minimo double,
  valor_maximo double
)
ROW FORMAT SERDE 'org.apache.hadoop.hive.serde2.OpenCSVSerde'
WITH SERDEPROPERTIES (
  'separatorChar' = ',',
  'quoteChar' = '"',
  'escapeChar' = '\\'
)
LOCATION 's3://lscc-datalake-fisi-347011900597/gold/resumen_ambiental_diario/'
TBLPROPERTIES ('skip.header.line.count'='1');

CREATE EXTERNAL TABLE IF NOT EXISTS lscc_gold.residuos_por_contenedor_diario (
  fecha string,
  sensor_id string,
  lecturas int,
  llenado_promedio double,
  llenado_maximo int,
  ultimo_nivel string,
  ultimo_porcentaje int
)
ROW FORMAT SERDE 'org.apache.hadoop.hive.serde2.OpenCSVSerde'
WITH SERDEPROPERTIES (
  'separatorChar' = ',',
  'quoteChar' = '"',
  'escapeChar' = '\\'
)
LOCATION 's3://lscc-datalake-fisi-347011900597/gold/residuos_por_contenedor_diario/'
TBLPROPERTIES ('skip.header.line.count'='1');

CREATE EXTERNAL TABLE IF NOT EXISTS lscc_gold.sonido_eventos_diario (
  fecha string,
  lecturas int,
  porcentaje_promedio double,
  porcentaje_maximo int,
  eventos_ruido_anomalo int
)
ROW FORMAT SERDE 'org.apache.hadoop.hive.serde2.OpenCSVSerde'
WITH SERDEPROPERTIES (
  'separatorChar' = ',',
  'quoteChar' = '"',
  'escapeChar' = '\\'
)
LOCATION 's3://lscc-datalake-fisi-347011900597/gold/sonido_eventos_diario/'
TBLPROPERTIES ('skip.header.line.count'='1');

CREATE EXTERNAL TABLE IF NOT EXISTS lscc_gold.reportes_por_estado_categoria (
  fecha string,
  categoria string,
  estado string,
  total int
)
ROW FORMAT SERDE 'org.apache.hadoop.hive.serde2.OpenCSVSerde'
WITH SERDEPROPERTIES (
  'separatorChar' = ',',
  'quoteChar' = '"',
  'escapeChar' = '\\'
)
LOCATION 's3://lscc-datalake-fisi-347011900597/gold/reportes_por_estado_categoria/'
TBLPROPERTIES ('skip.header.line.count'='1');

CREATE EXTERNAL TABLE IF NOT EXISTS lscc_gold.alertas_por_modulo_prioridad (
  fecha string,
  modulo string,
  prioridad string,
  estado string,
  total int
)
ROW FORMAT SERDE 'org.apache.hadoop.hive.serde2.OpenCSVSerde'
WITH SERDEPROPERTIES (
  'separatorChar' = ',',
  'quoteChar' = '"',
  'escapeChar' = '\\'
)
LOCATION 's3://lscc-datalake-fisi-347011900597/gold/alertas_por_modulo_prioridad/'
TBLPROPERTIES ('skip.header.line.count'='1');

CREATE EXTERNAL TABLE IF NOT EXISTS lscc_gold.manifest (
  run_id string,
  generado_en string,
  dataset string,
  ruta string
)
ROW FORMAT SERDE 'org.apache.hadoop.hive.serde2.OpenCSVSerde'
WITH SERDEPROPERTIES (
  'separatorChar' = ',',
  'quoteChar' = '"',
  'escapeChar' = '\\'
)
LOCATION 's3://lscc-datalake-fisi-347011900597/gold/manifest/'
TBLPROPERTIES ('skip.header.line.count'='1');
