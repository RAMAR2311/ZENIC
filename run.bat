@echo off
title Zenic Master Control
echo ===================================================
echo     Iniciando Zenic Master Control (Local)
echo ===================================================
echo.
cd /d "%~dp0"

if not exist "venv\Scripts\python.exe" (
    echo [ERROR] No se encontro el entorno virtual en .\venv
    pause
    exit /b 1
)

if not exist "zenic_master.db" (
    echo Inicializando base de datos...
    venv\Scripts\python.exe reset_db.py
)

echo.
echo Servidor listo en: http://127.0.0.1:5050
echo Usuario: admin@zenic.co
echo Clave:   Zenic2026!
echo.
echo Presiona Ctrl+C para detener el servidor.
echo ===================================================
echo.
venv\Scripts\python.exe app.py
pause
