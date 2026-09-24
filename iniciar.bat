@echo off
REM ============================================================
REM  iMenu App - arranque para Windows
REM  Doble clic en este archivo para instalar todo y abrir la app.
REM ============================================================
setlocal
cd /d "%~dp0"
title iMenu App

where py >nul 2>nul
if %errorlevel%==0 (set "PY=py") else (set "PY=python")

if not exist ".venv\Scripts\python.exe" (
    echo [1/3] Creando el entorno virtual...
    %PY% -m venv .venv
    if errorlevel 1 (
        echo.
        echo  No se pudo crear el entorno virtual.
        echo  Probablemente Python no este instalado.
        echo  Descargalo de https://www.python.org/downloads/
        echo  y marca la casilla "Add python.exe to PATH" al instalar.
        echo.
        pause
        exit /b 1
    )
) else (
    echo [1/3] Entorno virtual ya existe.
)

echo [2/3] Instalando librerias ^(la primera vez tarda unos minutos^)...
call ".venv\Scripts\activate.bat"
python -m pip install --upgrade pip --quiet
pip install -r requirements.txt --quiet
if errorlevel 1 (
    echo.
    echo  Fallo la instalacion de librerias. Revisa tu conexion a internet.
    pause
    exit /b 1
)

echo [3/3] Iniciando iMenu App en el navegador...
echo.
echo  Para detener la app: volve a esta ventana y presiona Ctrl+C
echo.
streamlit run app.py
pause
