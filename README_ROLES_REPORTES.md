# Lima Smart Core City — Roles y reportes ciudadanos

Esta versión agrega una división funcional entre usuarios normales y administradores.

## Credenciales iniciales

- Usuario: `admin`
- Contraseña: valor privado `ADMIN_INITIAL_PASSWORD` de `dashboard/.env`.
- Rol: `admin`

## Roles

### Usuario normal
Puede:

- Ver el dashboard/resumen.
- Crear reportes ciudadanos.
- Ver únicamente sus propios reportes.
- Adjuntar una imagen opcional al reporte.

No puede:

- Crear usuarios.
- Ver reportes de otros usuarios.
- Cambiar estados de atención.

### Administrador
Puede:

- Ver el dashboard completo.
- Crear usuarios normales o administradores.
- Ver todos los reportes ciudadanos.
- Filtrar reportes por categoría y estado.
- Cambiar el estado de cada reporte.
- Agregar observaciones administrativas.

## Nuevas rutas

- `/nuevo-reporte`: formulario para crear reportes.
- `/reportes`: listado de reportes.
- `/usuarios`: gestión de usuarios, solo para administradores.

## Categorías de reporte

- Ambiental
- Residuos
- Videovigilancia / Seguridad

## Estados de atención

- Pendiente
- En revisión
- Atendido
- Rechazado

## Flujo recomendado

1. Un usuario normal registra una incidencia.
2. El administrador revisa el reporte junto con los datos de sensores.
3. El administrador cambia el estado a `en revisión` o `atendido`.
4. El reporte queda guardado en historial para sustentar decisiones.

## Ejecución

Desde la carpeta `dashboard`:

```bash
pip install -r requirements.txt
python app.py
```

Luego abrir:

```text
http://127.0.0.1:5000
```
