$ErrorActionPreference = "Stop"

$docDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$outPath = Join-Path $docDir "Proyecto_LSCC_AWS_SQLite_PowerBI.docx"
$buildDir = Join-Path $docDir ("_docx_build_" + [guid]::NewGuid().ToString("N"))

function Escape-XmlText {
    param([string]$Text)
    if ($null -eq $Text) { return "" }
    return [System.Security.SecurityElement]::Escape($Text)
}

function New-Run {
    param(
        [string]$Text,
        [bool]$Bold = $false,
        [int]$Size = 22
    )
    $escaped = Escape-XmlText $Text
    $boldXml = if ($Bold) { "<w:b/>" } else { "" }
    return "<w:r><w:rPr>$boldXml<w:sz w:val=`"$Size`"/><w:szCs w:val=`"$Size`"/></w:rPr><w:t xml:space=`"preserve`">$escaped</w:t></w:r>"
}

function New-Paragraph {
    param(
        [string]$Text,
        [string]$Style = "Normal",
        [bool]$Bold = $false
    )
    $size = switch ($Style) {
        "Title" { 32 }
        "Heading1" { 28 }
        "Heading2" { 24 }
        default { 22 }
    }
    $spacing = if ($Style -eq "Title") { "<w:spacing w:after=`"240`"/>" } else { "<w:spacing w:after=`"140`"/>" }
    $run = New-Run -Text $Text -Bold:($Bold -or $Style -in @("Title", "Heading1", "Heading2")) -Size $size
    return "<w:p><w:pPr>$spacing</w:pPr>$run</w:p>"
}

function New-Bullet {
    param([string]$Text)
    $run = New-Run -Text ("- " + $Text) -Size 22
    return "<w:p><w:pPr><w:spacing w:after=`"80`"/></w:pPr>$run</w:p>"
}

function New-Table {
    param([array]$Rows)
    $xml = "<w:tbl><w:tblPr><w:tblW w:w=`"0`" w:type=`"auto`"/><w:tblBorders><w:top w:val=`"single`" w:sz=`"4`" w:space=`"0`" w:color=`"999999`"/><w:left w:val=`"single`" w:sz=`"4`" w:space=`"0`" w:color=`"999999`"/><w:bottom w:val=`"single`" w:sz=`"4`" w:space=`"0`" w:color=`"999999`"/><w:right w:val=`"single`" w:sz=`"4`" w:space=`"0`" w:color=`"999999`"/><w:insideH w:val=`"single`" w:sz=`"4`" w:space=`"0`" w:color=`"999999`"/><w:insideV w:val=`"single`" w:sz=`"4`" w:space=`"0`" w:color=`"999999`"/></w:tblBorders></w:tblPr>"
    for ($i = 0; $i -lt $Rows.Count; $i++) {
        $xml += "<w:tr>"
        foreach ($cell in $Rows[$i]) {
            $cellRun = New-Run -Text $cell -Bold:($i -eq 0) -Size 20
            $shade = if ($i -eq 0) { "<w:shd w:fill=`"D9EAF7`"/>" } else { "" }
            $xml += "<w:tc><w:tcPr><w:tcW w:w=`"2400`" w:type=`"dxa`"/>$shade</w:tcPr><w:p>$cellRun</w:p></w:tc>"
        }
        $xml += "</w:tr>"
    }
    $xml += "</w:tbl>"
    return $xml
}

function Add-Section {
    param([System.Collections.Generic.List[string]]$Parts, [string]$Title)
    $Parts.Add((New-Paragraph -Text $Title -Style "Heading1")) | Out-Null
}

New-Item -ItemType Directory -Path $buildDir | Out-Null
New-Item -ItemType Directory -Path (Join-Path $buildDir "_rels") | Out-Null
New-Item -ItemType Directory -Path (Join-Path $buildDir "word") | Out-Null
New-Item -ItemType Directory -Path (Join-Path $buildDir "word\_rels") | Out-Null
New-Item -ItemType Directory -Path (Join-Path $buildDir "docProps") | Out-Null

$parts = [System.Collections.Generic.List[string]]::new()
$parts.Add((New-Paragraph -Text "Proyecto Lima Smart Core City: SQLite, AWS y Power BI" -Style "Title")) | Out-Null
$parts.Add((New-Paragraph -Text "Documento de arquitectura e implementacion para conectar el dashboard local a AWS cuidando costos, mantener SQLite como respaldo y construir dashboards en Power BI para integrarlos a una pagina web.")) | Out-Null
$parts.Add((New-Paragraph -Text ("Fecha: " + (Get-Date -Format "yyyy-MM-dd HH:mm")))) | Out-Null

Add-Section $parts "Estado implementado"
$parts.Add((New-Bullet "Pipeline medallon local creado y validado: bronze, silver, gold y backup SQLite.")) | Out-Null
$parts.Add((New-Bullet "Bucket S3 creado: lscc-datalake-fisi-347011900597 en us-east-2.")) | Out-Null
$parts.Add((New-Bullet "Capa Gold subida a S3 en estructura compatible con Athena.")) | Out-Null
$parts.Add((New-Bullet "Athena configurado con database lscc_gold y workgroup primary.")) | Out-Null
$parts.Add((New-Bullet "Tablas externas Gold creadas y validadas en Athena.")) | Out-Null
$parts.Add((New-Bullet "Validacion Athena: 5 filas ambiental, 7 residuos, 3 alertas, 1 reportes, 0 sonido.")) | Out-Null
$parts.Add((New-Bullet "Siguiente paso operativo: conectar Power BI Desktop a Amazon Athena usando modo Import.")) | Out-Null

Add-Section $parts "1. Resumen del proyecto actual"
$parts.Add((New-Paragraph -Text "El proyecto Lima Smart Core City Fase 1 esta organizado como una solucion IoT local con dashboard web, almacenamiento SQLite, broker MQTT y modulos ESP32. Actualmente el sistema recibe datos de sensores ambientales, residuos, vigilancia por sonido y camara, y permite gestionar reportes ciudadanos mediante roles de usuario.")) | Out-Null
$parts.Add((New-Bullet "Backend principal: Flask en dashboard/app.py.")) | Out-Null
$parts.Add((New-Bullet "Base de datos local: SQLite en dashboard/lscc.db.")) | Out-Null
$parts.Add((New-Bullet "Mensajeria IoT: MQTT local mediante Mosquitto.")) | Out-Null
$parts.Add((New-Bullet "Frontend: plantillas HTML en dashboard/templates y archivos estaticos en dashboard/static.")) | Out-Null
$parts.Add((New-Bullet "Modulos de hardware: ESP32 ambiental, residuos, camara ESP32-CAM y KY-037.")) | Out-Null

Add-Section $parts "2. Estructura de carpetas"
$parts.Add((New-Table @(
    @("Carpeta o archivo", "Funcion"),
    @("dashboard/app.py", "Aplicacion Flask, rutas web, API, login, roles, MQTT y persistencia."),
    @("dashboard/lscc.db", "Base SQLite operativa del dashboard."),
    @("dashboard/templates", "Vistas HTML para login, dashboard, usuarios y reportes."),
    @("dashboard/static", "CSS, JavaScript e imagenes estaticas."),
    @("dashboard/imagenes", "Imagenes recibidas desde ESP32-CAM."),
    @("dashboard/reportes_adjuntos", "Adjuntos subidos por usuarios ciudadanos."),
    @("db/crear_db.py", "Script de creacion de tablas SQLite."),
    @("db/ver_db.py", "Script de diagnostico de la base de datos."),
    @("arduino", "Codigo fuente de los modulos ESP32.")
))) | Out-Null

Add-Section $parts "3. Roles y funciones"
$parts.Add((New-Table @(
    @("Rol", "Permisos principales"),
    @("admin", "Acceso al dashboard, gestion de usuarios internos y revision de reportes."),
    @("trabajador", "Acceso al dashboard y revision/actualizacion de reportes ciudadanos."),
    @("usuario", "Registro ciudadano y creacion de reportes con categoria, ubicacion, descripcion e imagen opcional.")
))) | Out-Null

Add-Section $parts "4. Estrategia recomendada en AWS cuidando creditos"
$parts.Add((New-Paragraph -Text "La recomendacion es no iniciar con servicios que permanecen encendidos o que pueden consumir creditos rapidamente, como EC2, RDS, Redshift, NAT Gateway, Load Balancer u OpenSearch. Para esta etapa conviene usar almacenamiento barato y consultas bajo demanda.")) | Out-Null
$parts.Add((New-Table @(
    @("Necesidad", "Servicio recomendado", "Motivo"),
    @("Respaldo en nube", "Amazon S3", "Costo bajo, simple y suficiente para CSV, JSON, SQLite e imagenes."),
    @("Consulta SQL para Power BI", "Amazon Athena", "Permite consultar archivos en S3 como tablas SQL sin servidor permanente."),
    @("Catalogo de tablas", "AWS Glue Data Catalog", "Athena usa este catalogo para reconocer tablas y esquemas."),
    @("Permisos", "IAM", "Permisos minimos para que la app solo acceda al bucket necesario."),
    @("Control de gasto", "AWS Budgets", "Alertas por correo cuando se acerque al limite definido.")
))) | Out-Null
$parts.Add((New-Bullet "Crear un presupuesto AWS de 1 USD o 5 USD con alertas al 50%, 80% y 100%.")) | Out-Null
$parts.Add((New-Bullet "Mantener el bucket S3 privado con Block Public Access activado.")) | Out-Null
$parts.Add((New-Bullet "Usar ciclo de vida en S3 para borrar respaldos antiguos despues de 90 o 180 dias.")) | Out-Null
$parts.Add((New-Bullet "Evitar servicios de computo o bases de datos administradas hasta que el sistema este validado.")) | Out-Null

Add-Section $parts "5. Arquitectura propuesta"
$parts.Add((New-Paragraph -Text "La arquitectura recomendada mantiene SQLite como base local y respaldo principal, pero exporta copias a AWS para consulta y visualizacion.")) | Out-Null
$parts.Add((New-Paragraph -Text "ESP32 y sensores -> Mosquitto local -> Flask dashboard -> SQLite local -> exportacion CSV/JSON -> Amazon S3 -> Amazon Athena -> Power BI -> pagina web.")) | Out-Null
$parts.Add((New-Paragraph -Text "Esta arquitectura permite trabajar sin depender permanentemente de Internet para operar localmente, y al mismo tiempo tener una copia en la nube para analisis y publicacion de dashboards.")) | Out-Null

Add-Section $parts "6. Datos a guardar y destino"
$parts.Add((New-Table @(
    @("Dato", "Origen local", "Destino AWS", "Uso en Power BI"),
    @("Lecturas ambientales", "lecturas_ambientales", "S3 + Athena", "Graficas de temperatura, humedad, presion y gas."),
    @("Lecturas de residuos", "lecturas_residuos", "S3 + Athena", "Estado de contenedores por sensor."),
    @("Lecturas de sonido", "lecturas_sonido", "S3 + Athena", "Eventos y niveles de ruido."),
    @("Reportes ciudadanos", "reportes_ciudadanos", "S3 + Athena", "Reportes por estado, categoria, urgencia y fecha."),
    @("Alertas", "eventos_alerta", "S3 + Athena", "Alertas activas, prioridad e historial."),
    @("Imagenes", "dashboard/imagenes", "S3", "Evidencia visual y enlaces/metadatos.")
))) | Out-Null

Add-Section $parts "7. Implementacion AWS realizada"
$parts.Add((New-Bullet "AWS CLI configurado con el usuario IAM iot-IAM.")) | Out-Null
$parts.Add((New-Bullet "Bucket S3 privado creado en us-east-2: lscc-datalake-fisi-347011900597.")) | Out-Null
$parts.Add((New-Bullet "Block Public Access activado en el bucket.")) | Out-Null
$parts.Add((New-Bullet "Cifrado SSE-S3 activado por defecto.")) | Out-Null
$parts.Add((New-Bullet "Script subir_gold_s3.py creado para subir solo la capa Gold.")) | Out-Null
$parts.Add((New-Bullet "Script ejecutar_athena_gold.py creado para ejecutar el SQL de Athena.")) | Out-Null
$parts.Add((New-Bullet "Archivo athena_gold_tables.sql creado con las tablas externas.")) | Out-Null
$parts.Add((New-Bullet "Base Athena lscc_gold creada y validada.")) | Out-Null

Add-Section $parts "8. Power BI conectado a AWS"
$parts.Add((New-Paragraph -Text "Power BI puede leer datos de AWS mediante Amazon Athena. Athena consulta datos almacenados en S3 y los presenta como tablas SQL. Power BI Desktop usa el conector Amazon Athena y requiere instalar el driver ODBC de Athena.")) | Out-Null
$parts.Add((New-Bullet "Modo Import: recomendado para empezar, porque descarga una copia de los datos al modelo Power BI y es mas simple.")) | Out-Null
$parts.Add((New-Bullet "Modo DirectQuery: consulta Athena en vivo, util para datos grandes o actualizados frecuentemente, pero cada interaccion puede generar consultas y costo.")) | Out-Null
$parts.Add((New-Bullet "Para refresco automatico en Power BI Service se necesita configurar On-premises Data Gateway con el driver ODBC.")) | Out-Null
$parts.Add((New-Bullet "Permisos extra requeridos por Power BI: athena:ListDataCatalogs, athena:GetDataCatalog, athena:ListDatabases, athena:ListTableMetadata y athena:GetTableMetadata.")) | Out-Null
$parts.Add((New-Bullet "Si Power BI muestra AccessDenied para athena:ListDataCatalogs, revisar que LSCCAthenaGoldPolicy este actualizada y adjunta al usuario iot-IAM.")) | Out-Null
$parts.Add((New-Bullet "Prueba recomendada en PowerShell: aws athena list-data-catalogs --region us-east-2.")) | Out-Null

Add-Section $parts "9. Integracion con la pagina web"
$parts.Add((New-Paragraph -Text "Para mostrar el dashboard dentro de la pagina web existen dos opciones. La primera es Publish to web, que genera un iframe publico. Es simple, pero cualquier persona con el enlace puede ver el reporte, por lo que no debe usarse con datos privados o sensibles. La segunda es embed seguro, que conserva permisos de Power BI, pero puede requerir licencias o configuracion adicional.")) | Out-Null
$parts.Add((New-Bullet "Si el tablero es demostrativo y publico: usar Publish to web.")) | Out-Null
$parts.Add((New-Bullet "Si contiene usuarios, ubicaciones sensibles o datos internos: usar embed seguro o mantenerlo privado.")) | Out-Null

Add-Section $parts "10. Tareas pendientes"
$parts.Add((New-Bullet "Instalar Amazon Athena ODBC Driver en Windows.")) | Out-Null
$parts.Add((New-Bullet "Crear DSN ODBC llamado LSCC_Athena con region us-east-2 y output athena-results.")) | Out-Null
$parts.Add((New-Bullet "Actualizar LSCCAthenaGoldPolicy con permisos de catalogo Athena para que Power BI liste bases y tablas.")) | Out-Null
$parts.Add((New-Bullet "Conectar Power BI Desktop a Amazon Athena en modo Import.")) | Out-Null
$parts.Add((New-Bullet "Construir visualizaciones para ambiental, residuos, sonido, alertas y reportes.")) | Out-Null
$parts.Add((New-Bullet "Configurar AWS Budgets si aun no esta configurado.")) | Out-Null
$parts.Add((New-Bullet "Automatizar pipeline_medallon_local.py y subir_gold_s3.py cada 30 o 60 minutos.")) | Out-Null
$parts.Add((New-Bullet "Opcional: subir solo imagenes asociadas a eventos importantes, no todas las fotos cada 10 segundos.")) | Out-Null

Add-Section $parts "11. Riesgos y recomendaciones"
$parts.Add((New-Bullet "No publicar credenciales en GitHub ni en documentos publicos.")) | Out-Null
$parts.Add((New-Bullet "Cambiar credenciales por defecto como admin123, lscc2025 y la clave secreta Flask antes de exponer el sistema.")) | Out-Null
$parts.Add((New-Bullet "Evitar abrir el bucket S3 al publico.")) | Out-Null
$parts.Add((New-Bullet "Usar Athena con cuidado: cobra por datos escaneados, asi que conviene particionar archivos por fecha y preferir Parquet en una fase posterior.")) | Out-Null
$parts.Add((New-Bullet "Mantener SQLite local como respaldo operativo y crear copias periodicas en S3.")) | Out-Null

Add-Section $parts "12. Fuentes oficiales consultadas"
$parts.Add((New-Bullet "AWS Free Tier: https://aws.amazon.com/free/")) | Out-Null
$parts.Add((New-Bullet "AWS Budgets: https://docs.aws.amazon.com/cost-management/latest/userguide/budgets-managing-costs.html")) | Out-Null
$parts.Add((New-Bullet "AWS IoT Rules: https://docs.aws.amazon.com/iot/latest/developerguide/iot-rules.html")) | Out-Null
$parts.Add((New-Bullet "Power BI Amazon Athena connector: https://learn.microsoft.com/en-us/power-query/connectors/amazon-athena")) | Out-Null
$parts.Add((New-Bullet "AWS Athena con Power BI: https://docs.aws.amazon.com/athena/latest/ug/connect-with-odbc-and-power-bi.html")) | Out-Null
$parts.Add((New-Bullet "Power BI Publish to web: https://learn.microsoft.com/en-us/power-bi/collaborate-share/service-publish-to-web")) | Out-Null

$body = [string]::Join("`n", $parts)
$documentXml = @"
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    $body
    <w:sectPr>
      <w:pgSz w:w="12240" w:h="15840"/>
      <w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440" w:header="720" w:footer="720" w:gutter="0"/>
    </w:sectPr>
  </w:body>
</w:document>
"@

$contentTypes = @"
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
</Types>
"@

$rels = @"
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>
"@

$documentRels = @"
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>
"@

$created = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
$core = @"
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:dcmitype="http://purl.org/dc/dcmitype/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dc:title>Proyecto LSCC AWS SQLite Power BI</dc:title>
  <dc:creator>Codex</dc:creator>
  <cp:lastModifiedBy>Codex</cp:lastModifiedBy>
  <dcterms:created xsi:type="dcterms:W3CDTF">$created</dcterms:created>
  <dcterms:modified xsi:type="dcterms:W3CDTF">$created</dcterms:modified>
</cp:coreProperties>
"@

$app = @"
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
  <Application>Codex OpenXML Generator</Application>
</Properties>
"@

$utf8NoBom = [System.Text.UTF8Encoding]::new($false)
[System.IO.File]::WriteAllText((Join-Path $buildDir "[Content_Types].xml"), $contentTypes, $utf8NoBom)
[System.IO.File]::WriteAllText((Join-Path $buildDir "_rels\.rels"), $rels, $utf8NoBom)
[System.IO.File]::WriteAllText((Join-Path $buildDir "word\document.xml"), $documentXml, $utf8NoBom)
[System.IO.File]::WriteAllText((Join-Path $buildDir "word\_rels\document.xml.rels"), $documentRels, $utf8NoBom)
[System.IO.File]::WriteAllText((Join-Path $buildDir "docProps\core.xml"), $core, $utf8NoBom)
[System.IO.File]::WriteAllText((Join-Path $buildDir "docProps\app.xml"), $app, $utf8NoBom)

if (Test-Path $outPath) {
    Remove-Item -LiteralPath $outPath -Force
}

Add-Type -AssemblyName System.IO.Compression.FileSystem
[System.IO.Compression.ZipFile]::CreateFromDirectory($buildDir, $outPath)

$resolvedDocDir = (Resolve-Path $docDir).Path
$resolvedBuildDir = (Resolve-Path $buildDir).Path
if ($resolvedBuildDir.StartsWith($resolvedDocDir, [System.StringComparison]::OrdinalIgnoreCase)) {
    Remove-Item -LiteralPath $buildDir -Recurse -Force
}

Write-Host "Documento generado: $outPath"
