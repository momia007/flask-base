@echo off
set LOGFILE=C:\Asist\logs\deploy_%DATE:~6,4%-%DATE:~3,2%-%DATE:~0,2%_%TIME:~0,2%-%TIME:~3,2%.log

echo Deteniendo servicio FlaskServer...
net stop FlaskServer >> "%LOGFILE%" 2>&1

echo Actualizando archivos de produccion... >> "%LOGFILE%"
robocopy "E:\Biblioteca\Documentos\Logos\Martin\Asist" "C:\Asist" /MIR /XD venv /XF asistencia-501122-f1cc5a8edf80.json /LOG:"%LOGFILE%" /TEE

echo Reiniciando servicio FlaskServer... >> "%LOGFILE%"
net start FlaskServer >> "%LOGFILE%" 2>&1

echo Actualizacion completada. >> "%LOGFILE%"
echo Log guardado en: %LOGFILE%
pause
