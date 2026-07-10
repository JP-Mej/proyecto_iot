# Arquitectura LSCC alineada con ITU-T Y.2060

Versión del proyecto: `0.2.0-consolidacion-fase1`. Firmware base: `1.1.0`.

## Estado operativo verificado

- Mosquitto 2.1.2 funcionando con autenticación en el puerto 1883.
- Publicación y suscripción local verificadas.
- Flask conectado al broker y disponible en el puerto 5000.
- Flujo ESP32 -> Mosquitto -> Flask -> SQLite -> dashboard verificado.
- Secretos retirados de los archivos `.ino` y del seguimiento Git.
- TLS y ACL preparados como plantillas, todavía no activados.
- Módulo de residuos configurado físicamente para tres HC-SR04; la aplicación aún muestra cuatro posiciones.

## Capas

| Capa Y.2060 | Implementación LSCC |
|---|---|
| Aplicación | Dashboard Flask, portal de reportes y Power BI |
| Apoyo a servicios y aplicaciones | Ingesta MQTT, reglas, SQLite, APIs, S3 y Athena |
| Red | Wi-Fi, IPv4, TCP y MQTT; perfil TLS preparado |
| Dispositivo | ESP32 ambiental, residuos, cámara y sonido |

## Trazabilidad de componentes

| Componente | Capa principal | Capacidad transversal |
|---|---|---|
| ESP32 y sensores | Dispositivo | Gestión de identidad, firmware y heartbeat |
| Wi-Fi, IPv4 y TCP | Red | Monitoreo y seguridad del transporte |
| MQTT y Mosquitto | Red / apoyo a servicios | Autenticación, ACL y Last Will |
| Flask y APIs | Apoyo a servicios | Gestión de sesiones, validación y auditoría |
| SQLite | Apoyo a servicios | Persistencia, integridad y respaldo |
| S3, Athena y modelo Gold | Apoyo a servicios | Gobierno, retención y seguridad del dato |
| Dashboard web y Power BI | Aplicación | Roles, privacidad e indicadores operativos |

## Capacidades transversales

### Gestión

- Identidad estable por dispositivo.
- Versión de firmware y de contrato de mensajes.
- Heartbeat con uptime, RSSI e IP.
- Estado offline mediante MQTT Last Will y timeout del servidor.
- Inventario en la tabla `dispositivos`.

### Seguridad

- Secretos locales fuera del repositorio.
- Autenticación MQTT y ACL de referencia.
- Perfil MQTT/TLS configurable.
- Control de acceso por roles, CSRF y protección de sesiones.

## Contrato de estado

Tópico: `lscc/sistema/status`.

Campos mínimos:

```json
{
  "schema_version": "1.0",
  "device_id": "ESP32_AIRE_01",
  "modulo": "ambiental",
  "status": "online"
}
```

El esquema formal se encuentra en `schemas/estado-dispositivo.schema.json`.

## Pendientes de consolidación

1. Crear una PKI local y activar MQTT/TLS en broker y dispositivos.
2. Asignar credenciales y ACL únicas por dispositivo.
3. Separar la ingesta MQTT del proceso web.
4. Añadir configuración remota y actualización OTA firmada.
5. Automatizar backups, monitoreo, S3/Athena y Power BI.
