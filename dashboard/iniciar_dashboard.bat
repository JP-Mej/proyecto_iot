@echo off
REM ============================================================
REM LIMA SMART CORE CITY — Iniciador Dashboard Fase 1
REM Ejecutar desde la carpeta del dashboard
REM ============================================================

echo.
echo  Lima Smart Core City — Dashboard Fase 1
echo  =========================================

REM La aplicación carga su configuración privada desde dashboard\.env
if not exist .env (
    echo  [ERROR] No se encontro dashboard\.env
    echo  [INFO]  Copia .env.example como .env y completa sus valores.
    pause
    exit /b 1
)

REM Verificar que la DB existe
if not exist lscc.db (
    echo.
    echo  [ERROR] No se encontro lscc.db
    echo  [INFO]  Ejecuta primero: python crear_db.py
    echo.
    pause
    exit /b 1
)

REM Verificar entorno virtual
if exist venv\Scripts\activate.bat (
    call venv\Scripts\activate.bat
    echo  [ENV] Entorno virtual activado
) else (
    echo  [INFO] No se encontro venv, usando Python del sistema
)

echo  [ENV]  Configuracion cargada desde .env
echo  [WEB]  Dashboard en http://localhost:5000
echo.

python app.py
pause
