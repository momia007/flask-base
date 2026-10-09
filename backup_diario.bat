@echo off
REM =============================================================================
REM  backup_diario.bat
REM
REM  Ejecuta el backup diario de la planilla de asistencia.
REM  Pensado para ser llamado por el Programador de Tareas de Windows.
REM =============================================================================

setlocal

REM --- Rutas ---
set PROYECTO=E:\Biblioteca\Documentos\Logos\Martin\Asist
set VENV_PYTHON=%PROYECTO%\venv\Scripts\python.exe
set SCRIPT=%PROYECTO%\backup_diario.py

REM --- Ejecutar ---
cd /d "%PROYECTO%"
"%VENV_PYTHON%" "%SCRIPT%"

REM --- Código de salida ---
REM  0 = backup exitoso
REM  1 = el backup falló (ver backup_diario.log)
REM  2 = error inesperado (ver backup_diario.log)

exit /b %ERRORLEVEL%