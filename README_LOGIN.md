# Parche de login para Lima Smart Core City

Este ZIP ya incluye autenticación para el dashboard Flask.

## Credenciales iniciales
- Usuario: `admin`
- Contraseña: `admin123`

## Cómo funciona la sesión única
Cuando un usuario inicia sesión, se genera un nuevo `session_token` y se guarda en SQLite en la tabla `usuarios`.
Si ese mismo usuario inicia sesión en otro navegador o dispositivo, el token anterior se reemplaza.
La sesión anterior queda inválida y será enviada al login cuando intente navegar o cuando el dashboard consulte `/api/data`.

## Archivos modificados
- `dashboard/app.py`
- `dashboard/crear_db.py`
- `dashboard/templates/index.html`
- `dashboard/templates/login.html`
- `dashboard/static/style.css`

## Pasos
1. Reemplaza tu carpeta `dashboard` por la de este ZIP, o copia solo los archivos modificados.
2. Instala dependencias si no tienes el entorno virtual:
   ```bash
   pip install -r requirements.txt
   ```
3. Ejecuta:
   ```bash
   python app.py
   ```
4. Abre `http://127.0.0.1:5000` o la IP de tu laptop en la red.

## Importante
Cambia la contraseña inicial antes de usarlo en una red compartida.
