# Lima Smart Core City — Roles y reportes modularizados

## Roles

- **admin**: gestiona el sistema, revisa dashboard completo, crea trabajadores internos y consulta todos los reportes.
- **trabajador**: revisa reportes ciudadanos, cambia estados y registra observaciones de atención. No crea usuarios.
- **usuario**: ciudadano/vecino. Se registra desde `/registro`, ve un resumen y envía reportes. Solo ve sus propios reportes.

## Flujo recomendado

1. El ciudadano se registra desde la pantalla de login.
2. El ciudadano envía reportes de residuos, ambiental o videovigilancia.
3. El trabajador o administrador revisa reportes en `/reportes`.
4. El trabajador o administrador cambia el estado: pendiente, en revisión, atendido o rechazado.
5. El administrador puede crear trabajadores desde `/usuarios`.

## Credencial inicial

- Usuario: `admin`
- Contraseña: valor privado `ADMIN_INITIAL_PASSWORD` de `dashboard/.env`.

## Instalación

Desde la carpeta `dashboard`:

```bash
python -m pip install -r requirements.txt
python app.py
```

## Rutas principales

- `/login`: inicio de sesión.
- `/registro`: registro público de ciudadanos.
- `/`: dashboard.
- `/nuevo-reporte`: solo ciudadanos.
- `/reportes`: ciudadanos ven sus reportes; trabajadores y admins ven todos.
- `/usuarios`: solo administrador.
