@echo off
REM =============================================================================
REM  instalar_tarea_backup.bat
REM
REM  Registra una tarea programada de Windows que ejecuta backup_diario.bat
REM  todos los días a las 12:00 del mediodía.
REM
REM  Requiere ejecutarse como Administrador.
REM =============================================================================

setlocal

set NOMBRE_TAREA=Backup diario Asistencia CFL
set RUTA_BAT=C:\Asist\backup_diario.bat
set HORA=12:00

net session >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Este script requiere permisos de Administrador.
    echo Cerra esta ventana, y volve a ejecutarlo con clic derecho
    echo -^> "Ejecutar como administrador".
    echo.
    pause
    exit /b 1
)

echo Creando tarea "%NOMBRE_TAREA%"...
schtasks /Create ^
    /TN "%NOMBRE_TAREA%" ^
    /TR "\"%RUTA_BAT%\"" ^
    /SC DAILY ^
    /ST %HORA% ^
    /RL HIGHEST ^
    /F

if %ERRORLEVEL% NEQ 0 (
    echo Error al crear la tarea programada.
    pause
    exit /b 1
)

echo.
echo Tarea creada. Se ejecutara todos los dias a las %HORA%.
echo.
pause
endlocal