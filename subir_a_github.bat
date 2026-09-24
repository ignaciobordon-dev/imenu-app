@echo off
REM ============================================================
REM  iMenu App - subir el codigo a GitHub
REM  Doble clic en este archivo. Te va guiando y hace todo solo.
REM ============================================================
setlocal enabledelayedexpansion
cd /d "%~dp0"
title Subir iMenu App a GitHub
color 0F

echo.
echo  ============================================================
echo    SUBIR iMenu App A GITHUB
echo  ============================================================
echo.

REM ---------- 1. Git instalado? -------------------------------
git --version >nul 2>nul
if errorlevel 1 (
    echo  [X] No encuentro Git en esta computadora.
    echo.
    echo      Instalalo desde https://git-scm.com/download/win
    echo      Si lo acabas de instalar, CERRA esta ventana y volve
    echo      a hacer doble clic: Git recien aparece en ventanas nuevas.
    echo.
    pause
    exit /b 1
)
for /f "tokens=*" %%v in ('git --version') do echo  [OK] %%v
echo.

REM ---------- 2. Identidad (una sola vez) ---------------------
set "GITNAME="
for /f "tokens=*" %%n in ('git config --global user.name 2^>nul') do set "GITNAME=%%n"
if not defined GITNAME (
    echo  Es la primera vez que usas Git en esta maquina.
    set /p "GITNAME=  Tu nombre y apellido: "
    git config --global user.name "!GITNAME!"
)
set "GITMAIL="
for /f "tokens=*" %%e in ('git config --global user.email 2^>nul') do set "GITMAIL=%%e"
if not defined GITMAIL (
    set /p "GITMAIL=  El correo de tu cuenta de GitHub: "
    git config --global user.email "!GITMAIL!"
)
echo  [OK] Identidad: !GITNAME! ^<!GITMAIL!^>
echo.

REM ---------- 3. Usuario de GitHub ----------------------------
set "GHUSER="
for /f "tokens=*" %%u in ('git config --global imenu.ghuser 2^>nul') do set "GHUSER=%%u"
if not defined GHUSER (
    echo  Tu usuario de GitHub es lo que va despues de github.com/
    echo  en la direccion de tu perfil. NO es el correo.
    set /p "GHUSER=  Usuario de GitHub: "
    git config --global imenu.ghuser "!GHUSER!"
)
set "REPO=imenu-app"
echo  [OK] Repositorio destino: https://github.com/!GHUSER!/!REPO!
echo.

REM ---------- 4. El repositorio existe en GitHub? -------------
set "YACREADO="
set /p "YACREADO=  Ya creaste el repositorio vacio en GitHub? (s/n): "
if /i not "!YACREADO!"=="s" (
    echo.
    echo  Te abro la pagina. Completa asi:
    echo     Repository name . . imenu-app
    echo     Visibility  . . . . Private
    echo     NO marques nada en "Initialize this repository"
    echo     ^(ni README, ni .gitignore, ni licencia^)
    echo.
    start "" "https://github.com/new"
    echo  Cuando le hayas dado a "Create repository", volve aca.
    pause
)

REM ---------- 5. Repositorio local ----------------------------
if not exist ".git" (
    echo  Inicializando el repositorio local...
    git init >nul 2>nul
)
git branch -M main >nul 2>nul
git add -A >nul 2>nul

REM ---------- 6. CHEQUEO DE SEGURIDAD -------------------------
echo.
echo  Revisando que no se suba nada sensible...
set "LISTA=%TEMP%\imenu_por_subir.txt"
git diff --cached --name-only > "%LISTA%" 2>nul

set "PELIGRO="
findstr /i /c:"secrets.toml" "%LISTA%" >nul
if not errorlevel 1 set "PELIGRO=las credenciales de Supabase (secrets.toml)"
findstr /i /c:"Mix " "%LISTA%" >nul
if not errorlevel 1 set "PELIGRO=planillas con datos reales de tu restaurante"
findstr /i /c:".venv/" "%LISTA%" >nul
if not errorlevel 1 set "PELIGRO=la carpeta .venv del entorno de Python"

if defined PELIGRO (
    echo.
    echo  [X] FRENO: en la lista para subir aparecen !PELIGRO!.
    echo      No subi nada. Avisale a Claude y revisen el .gitignore.
    echo.
    pause
    exit /b 1
)
echo  [OK] No aparecen credenciales ni datos reales.
echo.
echo  --- Archivos que se van a subir -----------------------------
type "%LISTA%"
echo  -------------------------------------------------------------
echo.
set "SEGUIR="
set /p "SEGUIR=  Continuo con la subida? (s/n): "
if /i not "!SEGUIR!"=="s" (
    echo  Cancelado. No se subio nada.
    pause
    exit /b 0
)

REM ---------- 7. Guardar el cambio ----------------------------
git commit -m "Actualizacion de iMenu App" >nul 2>nul
if errorlevel 1 echo  (no habia cambios nuevos que guardar)

REM ---------- 8. Conectar con GitHub --------------------------
git remote get-url origin >nul 2>nul
if errorlevel 1 (
    git remote add origin "https://github.com/!GHUSER!/!REPO!.git"
) else (
    git remote set-url origin "https://github.com/!GHUSER!/!REPO!.git"
)

REM ---------- 9. Subir ----------------------------------------
echo.
echo  Subiendo a GitHub...
echo  Puede abrirse una ventana del navegador para que inicies sesion.
echo  Aprobala ahi y volve a esta ventana. NO escribas tu contrasena aca.
echo.
git push -u origin main
if errorlevel 1 (
    echo.
    echo  [X] La subida fallo. Lo mas comun:
    echo      - El repositorio todavia no existe en GitHub
    echo        ^(https://github.com/!GHUSER!/!REPO!^)
    echo      - Cerraste la ventana de inicio de sesion sin aprobar
    echo      - El nombre de usuario esta mal escrito
    echo.
    echo      Para corregir el usuario: git config --global --unset imenu.ghuser
    echo      y volve a ejecutar este archivo.
    echo.
    pause
    exit /b 1
)

echo.
echo  ============================================================
echo    LISTO. Tu codigo esta en:
echo    https://github.com/!GHUSER!/!REPO!
echo  ============================================================
echo.
echo  De ahora en adelante, cada vez que quieras guardar cambios
echo  en GitHub, volve a hacer doble clic en este mismo archivo.
echo.
pause
