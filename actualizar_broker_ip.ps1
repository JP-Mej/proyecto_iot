# Lima Smart — actualizar IP del broker MQTT en todos los secrets.h
# Uso: .\actualizar_broker_ip.ps1
# Uso con IP manual: .\actualizar_broker_ip.ps1 -IP "192.168.100.99"

param(
    [string]$IP = ""
)

if ($IP -eq "") {
    # Detectar IP automaticamente (adaptador Wi-Fi o Ethernet activo)
    $IP = (Get-NetIPAddress -AddressFamily IPv4 |
           Where-Object { $_.IPAddress -notmatch "^(127\.|169\.)" -and $_.PrefixOrigin -ne "WellKnown" } |
           Sort-Object InterfaceMetric |
           Select-Object -First 1).IPAddress
    Write-Host "IP detectada automaticamente: $IP"
}

if (-not $IP) {
    Write-Error "No se pudo detectar la IP. Usa: .\actualizar_broker_ip.ps1 -IP '192.168.x.x'"
    exit 1
}

$archivos = @(
    "arduino\ambiental\MQ2_BMP280_DHT22\secrets.h",
    "arduino\camara\CAMARA\secrets.h",
    "arduino\ky037\secrets.h",
    "arduino\residuos\HCR_04\secrets.h"
)

$raiz = $PSScriptRoot
$actualizados = 0

foreach ($rel in $archivos) {
    $ruta = Join-Path $raiz $rel
    if (Test-Path $ruta) {
        $contenido = Get-Content $ruta -Raw
        if ($contenido -match 'LSCC_MQTT_BROKER') {
            $nuevo = $contenido -replace '(#define LSCC_MQTT_BROKER\s+")[^"]*(")', "`${1}$IP`$2"
            if ($nuevo -ne $contenido) {
                Set-Content $ruta $nuevo -NoNewline -Encoding UTF8
                Write-Host "  [OK] $rel -> $IP"
                $actualizados++
            } else {
                Write-Host "  [=]  $rel ya tenia $IP"
            }
        } else {
            Write-Host "  [!]  $rel no tiene LSCC_MQTT_BROKER (revisar manualmente)"
        }
    } else {
        Write-Host "  [X]  No encontrado: $rel"
    }
}

Write-Host ""
Write-Host "Listo. $actualizados archivo(s) actualizado(s) con broker: $IP"
Write-Host "Recuerda recompilar y subir cada sketch al Arduino."
