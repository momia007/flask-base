@echo off
REM =============================================================================
REM  update_server.bat
REM
REM  Actualiza la carpeta de producción (C:\Asist) desde desarrollo (E:\...).
REM
REM  Pasos:
REM    1. Detiene el servicio FlaskServer (si existe).
REM    2. Espeja los archivos de origen a destino, respetando las exclusiones.
REM    3. Reinicia el servicio FlaskServer (si existe).
REM
REM  Exclusiones importantes:
REM    - .git, venv, __pycache__ : no son código ni datos que se copien
REM    - instance                : caché y datos locales de producción
REM    - logs                    : logs de despliegue (cada entorno tiene los suyos)
REM    - config.py               : CADA ENTORNO TIENE SU PROPIO config.py
REM    - asistencia-*.json       : credenciales (secretos)
REM    - *.xlsx, *.zip           : planillas y backups
REM    - archivos del editor     : .vscode, .idea
REM =============================================================================

setlocal

REM --- Rutas ---
set ORIGEN=E:\Biblioteca\Documentos\Logos\Martin\Asist
set DESTINO=C:\Asist
set SERVICIO=FlaskServer

REM --- Log con fecha y hora ---
set LOGFILE=%DESTINO%\logs\deploy_%DATE:~6,4%-%DATE:~3,2%-%DATE:~0,2%_%TIME:~0,2%-%TIME:~3,2%.log

REM --- Crear carpeta de logs si no existe ---
if not exist "%DESTINO%\logs" mkdir "%DESTINO%\logs"

echo ============================================================
echo   ACTUALIZACION DE PRODUCCION
echo   Origen : %ORIGEN%
echo   Destino: %DESTINO%
echo   Log    : %LOGFILE%
echo ============================================================
echo.

REM --- 1. Detener servicio (si existe) ---
sc query %SERVICIO% >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo [%TIME%] Deteniendo servicio %SERVICIO%...
    net stop %SERVICIO% >> "%LOGFILE%" 2>&1
) else (
    echo [%TIME%] El servicio %SERVICIO% no esta instalado. Se omite detenerlo.
    echo [%TIME%] El servicio %SERVICIO% no esta instalado. Se omite detenerlo. >> "%LOGFILE%"
)

REM --- 2. Copiar archivos ---
echo [%TIME%] Copiando archivos...
robocopy "%ORIGEN%" "%DESTINO%" /MIR /IS ^
    /XD .git venv env .venv __pycache__ instance logs .vscode .idea .pytest_cache ^
    /XF asistencia-*.json *.xlsx *.xls *.zip *.pyc *.pyo .DS_Store Thumbs.db desktop.ini Eliminar.txt config.py ^
    /R:1 /W:1 /NP /TEE /LOG+:"%LOGFILE%"

REM --- 3. Reiniciar servicio (si existe) ---
sc query %SERVICIO% >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo [%TIME%] Reiniciando servicio %SERVICIO%...
    net start %SERVICIO% >> "%LOGFILE%" 2>&1
) else (
    echo [%TIME%] El servicio %SERVICIO% no esta instalado. Se omite reiniciarlo.
    echo [%TIME%] El servicio %SERVICIO% no esta instalado. Se omite reiniciarlo. >> "%LOGFILE%"
)

echo.
echo ============================================================
echo   ACTUALIZACION COMPLETADA
echo   Log guardado en: %LOGFILE%
echo ============================================================
pause
endlocal