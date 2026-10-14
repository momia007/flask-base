# Sistema de Asistencia CFL

Aplicación web para tomar asistencia, gestionar alumnos y consultar
porcentajes de asistencia en el Centro de Formación Laboral (CFL).

Reemplaza el manejo manual de planillas de Excel y las múltiples copias
descoordinadas por una única base de datos en Google Sheets, con una
interfaz web accesible desde cualquier equipo de la red local.

---

## Índice

1. [¿Qué es esta app?](#1-qué-es-esta-app)
2. [Arquitectura general](#2-arquitectura-general)
3. [Instalación desde cero](#3-instalación-desde-cero)
4. [Configuración de Google Sheets](#4-configuración-de-google-sheets)
5. [Configuración del servicio NSSM](#5-configuración-del-servicio-nssm)
6. [Tarea programada de backup](#6-tarea-programada-de-backup)
7. [Despliegue (dev → prod)](#7-despliegue-dev--prod)
8. [Mantenimiento](#8-mantenimiento)
9. [Solución de problemas frecuentes](#9-solución-de-problemas-frecuentes)
10. [Estructura del código](#10-estructura-del-código)
11. [Cálculo del porcentaje de asistencia](#11-cálculo-del-porcentaje-de-asistencia)
12. [Changelog y versionado](#12-changelog-y-versionado)

---

## 1. ¿Qué es esta app?

Sistema web que permite a los profesores y al personal administrativo
del CFL:

- **Tomar asistencia** de cada curso desde cualquier dispositivo de la
  red (PC, tablet, celular).
- **Consultar y justificar** asistencias por fecha y curso.
- **Registrar feriados** y **ausencias de profesores**.
- **Administrar alumnos**: alta, edición, baja y reactivación.
- **Calcular automáticamente** el porcentaje de asistencia de cada
  alumno, según criterios configurables.
- **Hacer backups** de toda la base de datos.

La base de datos es una **planilla de Google Sheets**. La app lee y
escribe en ella usando la API de Google Sheets.

---

## 2. Arquitectura general

### Stack

- **Backend**: Python 3.10+, Flask
- **Base de datos**: Google Sheets (vía `gspread` + `google-api-python-client`)
- **Servidor de producción**: Waitress (WSGI)
- **Servicio de Windows**: NSSM (envuelve el arranque de la app como servicio)
- **Frontend**: HTML + Bootstrap 5 + Jinja2

### Flujo de datos

```
Usuario (navegador)
       │
       ▼
App Flask (routes/)
       │
       ├──► services/sheets.py ──► Google Sheets (API)
       │
       ├──► services/cache_sheets.py ──► instance/cache_sheets.json
       │                                  (caché en disco)
       │
       └──► services/backup.py ──► instance/backups/  (CSVs locales)
```

### Caché

Para no superar la cuota de la API de Google Sheets (60 lecturas por
minuto), las hojas se cachean en disco en `instance/cache_sheets.json`.

- **Cursos, Feriados**: se cachean por 24 horas.
- **Alumnos, Ausencias_Profesores**: 6 y 2 horas respectivamente.
- **Asistencias**: 30 segundos (se escribe seguido).

Se puede forzar un refresco desde `/configuracion`.

### Backups

Dos tipos:

- **Manual**: botón "💾 Hacer backup ahora" en `/configuracion`.
- **Automático**: tarea programada de Windows que corre todos los días
  a las 12:00 del mediodía.

Los backups se guardan como CSVs (uno por pestaña) en
`instance/backups/<entorno>/<fecha>/`. Se conservan los últimos 30.

### Entornos

La app puede correr en dos modos, controlados por la variable `ENTORNO`
en `config.py`:

- **`"produccion"`** → usa la planilla real (`Asistencia CFL (produccion)`).
- **`"desarrollo"`** → usa una copia (`Asistencia CFL (desarrollo)`), para
  probar sin riesgo.

**Cada PC (producción vs desarrollo) tiene su propio `config.py`** con el
valor correcto. El script de despliegue (`update_server.bat`) **no copia
`config.py`** entre entornos.

---

## 3. Instalación desde cero

### Requisitos previos

- **Windows 10** o superior.
- **Python 3.10+** instalado (probado con 3.13).
- **Git** instalado.
- **Cuenta de servicio de Google Cloud** con acceso a Google Sheets y
  Drive (ver sección 4).
- **NSSM** (Non-Sucking Service Manager) descargado en `C:\nssm\win64\`.
  Se baja desde https://nssm.cc/download.

### Paso 1: clonar el repositorio

```bash
git clone https://github.com/momia007/flask-base.git C:\Asist
cd C:\Asist
```

> El nombre del repo sigue siendo `flask-base` por razones históricas. El
> contenido es el sistema de asistencia completo.

### Paso 2: crear el entorno virtual

**Importante**: el `venv` **NO se versiona** y **NO se copia** entre
entornos. Cada PC tiene el suyo.

```bash
cd C:\Asist
python -m venv venv
venv\Scripts\activate
```

### Paso 3: instalar dependencias

```bash
pip install -r requirements.txt
```

Verificar que queden instaladas las dependencias críticas:

```bash
pip show google-api-python-client
pip show waitress
pip show gspread
```

Los tres comandos deben mostrar `Location: C:\Asist\venv\Lib\site-packages`.

> **Ojo**: si `pip show` muestra una ruta de otra carpeta (por ejemplo
> `E:\...`), significa que estás usando el pip de otro venv. Volvé a
> activar el correcto.

### Paso 4: crear el `config.py`

El repo **ya incluye** un `config.py` funcional. Si querés cambiarlo:

1. Copiá el archivo `config.py` a `config.py.bak` (por las dudas).
2. Editá `config.py` con el Bloc de Notas.
3. Cambiá solo lo que está entre comillas. Ver la sección 4 para el ID
   de planilla y la sección "Entornos" en el punto 2.

### Paso 5: verificar que arranca a mano

```bash
cd C:\Asist
venv\Scripts\activate
python app.py
```

Debería decir algo así:

```
Serving on http://0.0.0.0:5000
```

**Probar en el navegador**:

- `http://127.0.0.1:5000` → debe cargar el panel.
- `http://192.168.0.10:5000` → debe cargar desde otra PC de la red.

Si las dos funcionan, cerrá el proceso (Ctrl+C) y seguí con la sección 5.

---

## 4. Configuración de Google Sheets

### Estructura de la carpeta en Google Drive

Toda la información del sistema vive dentro de una carpeta en Google
Drive llamada `sistema_asistencia`:

```
Mi unidad/
├── sistema_asistencia/
│   └── base_datos/
│       ├── Asistencia CFL (produccion)     ← planilla real
│       ├── Asistencia CFL (desarrollo)     ← copia para pruebas
│       └── archivos_historicos/            ← datos viejos archivados
│
└── sistema_asistencia_backups/             ← carpeta SEPARADA
    ├── archivos_historicos/
    ├── produccion/
    │   └── metadata/
    └── desarrollo/
        └── metadata/
```

**Por qué `sistema_asistencia_backups` está separada**: si alguien borra
por error la carpeta `sistema_asistencia`, los backups siguen a salvo.

### Cuenta de servicio de Google

La app usa una **cuenta de servicio** (Service Account) para acceder a
las planillas. Esta cuenta tiene su propio email y sus propias
credenciales.

**¿Cómo crearla?**

1. Entrar a https://console.cloud.google.com/ con la cuenta de Google
   del CFL.
2. Crear un proyecto nuevo (o usar uno existente).
3. Habilitar las APIs:
   - **Google Sheets API**
   - **Google Drive API**
4. Ir a "Credenciales" → "Crear credenciales" → "Cuenta de servicio".
5. Ponerle un nombre (por ejemplo `asistencia-cfl`) y crearla.
6. Una vez creada, ir a la cuenta de servicio, pestaña "Claves" →
   "Agregar clave" → "Crear clave nueva" → tipo **JSON**.
7. Se descarga un archivo `.json`. **Renombrarlo a
   `asistencia-501122-f1cc5a8edf80.json`** y ponerlo en la raíz del
   proyecto (`C:\Asist\`).

> **CRÍTICO**: ese archivo `.json` es la llave de acceso. **NO debe
> subirse a Git nunca** (ya está en el `.gitignore`). Si se pierde, hay
> que generar uno nuevo.

**¿Cómo compartir planillas con la cuenta de servicio?**

La cuenta de servicio tiene un email (algo como
`asistencia-501122@asistencia-501122.iam.gserviceaccount.com`). Se
obtiene del archivo `.json`, en el campo `client_email`.

Para que la app pueda leer y escribir en una planilla:

1. Abrir la planilla en Google Sheets.
2. Botón "Compartir".
3. Pegar el email de la cuenta de servicio.
4. Permiso: **Editor**.
5. Destildar "Notificar a las personas".
6. Enviar.

**Recomendación**: compartir **la carpeta `base_datos/` completa** con
la cuenta de servicio. Así todas las planillas y backups dentro heredan
el permiso automáticamente.

### Estructura de las hojas

La planilla `Asistencia CFL` tiene estas pestañas:

**Cursos**
```
ID_CURSO | CURSO | NICK | TURNO | LU | MA | MI | JU | VI |
INICIO | FIN | PROFESOR | INICIO_CICLO
```

- `ID_CURSO`: número único.
- `CURSO`: nombre completo (ej: "ASISTENTE DE OFICINA A").
- `NICK`: nombre corto para mostrar en pantalla.
- `TURNO`: `M` (mañana), `T` (tarde), `V` (vespertino).
- `LU`..`VI`: `1` si el curso tiene clase ese día, `0` si no.
- `INICIO`, `FIN`: hora de inicio y fin (`HH:MM`).
- `PROFESOR`: nombre del profesor a cargo.
- `INICIO_CICLO`: fecha de inicio del ciclo del curso (`dd/mm/aaaa`).

**Alumnos**
```
ID_ALUMNO | APELLIDOS | NOMBRES | ID_CURSO | CUAT. | AÑO | ESTADO
```

- `ID_ALUMNO`: DNI del alumno.
- `ID_CURSO`: curso al que pertenece.
- `CUAT.`: cuatrimestre (`1` o `2`).
- `AÑO`: año lectivo.
- `ESTADO`: `A` (activo) o `B` (baja). Vacío = `A`.

**Asistencias**
```
FECHA | ID_CURSO | ID_ALUMNO | ESTADO | DETALLE
```

- `FECHA`: `dd/mm/aaaa`.
- `ESTADO`: `P` (presente), `J` (justificado), `B` (baja histórica,
  ya no se usa).
- `DETALLE`: motivo, solo para `J`.

**Feriados**
```
FECHA | MOTIVO
```

- `FECHA`: `aaaa-mm-dd`.
- `MOTIVO`: texto libre.

**Ausencias_Profesores**
```
FECHA | ID_CURSO | PROFESOR | MOTIVO
```

- `FECHA`: `aaaa-mm-dd`.

---

## 5. Configuración del servicio NSSM

La app corre como **servicio de Windows** usando **NSSM**. Eso permite
que arranque sola con el sistema, corra en segundo plano y no dependa
de que alguien abra una consola.

### ¿Qué es NSSM?

NSSM (Non-Sucking Service Manager) es un programa que envuelve
cualquier ejecutable y lo hace correr como servicio de Windows.
Descargarlo de https://nssm.cc/download y descomprimirlo en
`C:\nssm\win64\`.

### Instalación del servicio

**Requisito**: tener `start_server.bat` en la raíz del proyecto.

**Contenido de `start_server.bat`**:

```bat
@echo off
cd /d "%~dp0"
"%~dp0venv\Scripts\python.exe" "%~dp0app.py"
```

**Pasos** (con consola **como administrador**):

```bat
C:\nssm\win64\nssm.exe install FlaskServer "C:\Asist\start_server.bat"
C:\nssm\win64\nssm.exe set FlaskServer AppDirectory "C:\Asist"
C:\nssm\win64\nssm.exe set FlaskServer Start SERVICE_AUTO_START
C:\nssm\win64\nssm.exe set FlaskServer AppStdout "C:\Asist\logs\service_stdout.log"
C:\nssm\win64\nssm.exe set FlaskServer AppStderr "C:\Asist\logs\service_stderr.log"
C:\nssm\win64\nssm.exe set FlaskServer AppRotateFiles 1
C:\nssm\win64\nssm.exe set FlaskServer AppRotateBytes 1048576
C:\nssm\win64\nssm.exe set FlaskServer AppExit Default Restart
C:\nssm\win64\nssm.exe set FlaskServer AppRestartDelay 5000
```

Eso configura:

- El servicio se llama `FlaskServer`.
- Arranca automáticamente con Windows.
- Guarda los logs de la app en `C:\Asist\logs\`.
- Rota los logs al llegar a 1 MB.
- Si el proceso se cae, NSSM lo reinicia a los 5 segundos.

**Arrancar el servicio**:

```bat
net start FlaskServer
```

**Verificar**:

```bat
sc query FlaskServer
```

Debe decir `RUNNING`.

```bat
netstat -ano | findstr :5000 | findstr LISTENING
```

Debe mostrar algo como:

```
TCP    0.0.0.0:5000    0.0.0.0:0    LISTENING    12345
```

`0.0.0.0:5000` significa que acepta conexiones de cualquier interfaz
de red. Eso es lo correcto.

### Cambiar el comando que ejecuta el servicio

Si en algún momento hay que cambiar el `start_server.bat` o el
ejecutable:

```bat
C:\nssm\win64\nssm.exe set FlaskServer Application "NUEVA_RUTA"
```

### Ver los errores del servicio

Si el servicio arranca pero la app no responde, mirar:

```bat
type C:\Asist\logs\service_stderr.log
```

Ahí van a estar los errores de Python.

---

## 6. Tarea programada de backup

Un backup automático corre todos los días a las 12:00 del mediodía
mediante el Programador de Tareas de Windows.

### Archivos involucrados

- **`backup_diario.py`**: script standalone que hace el backup.
- **`backup_diario.bat`**: wrapper para llamarlo desde el Programador.
- **`instalar_tarea_backup.bat`**: registra la tarea en Windows.

### Registrar la tarea

**Clic derecho** sobre `C:\Asist\instalar_tarea_backup.bat` →
**"Ejecutar como administrador"**.

El script crea la tarea **"Backup diario Asistencia CFL"** que se
ejecuta todos los días a las 12:00.

### Verificar

**Desde consola**:

```bat
schtasks /Query /TN "Backup diario Asistencia CFL"
```

**Desde la interfaz**: abrir `taskschd.msc` y buscar la tarea.

### Ejecutar la tarea manualmente (para probar)

```bat
schtasks /Run /TN "Backup diario Asistencia CFL"
```

### Ver el log

```bat
type C:\Asist\logs\backup_diario.log
```

### Reglas del backup

- **Solo hace un backup por día**. Si ya existe uno con la fecha de
  hoy, no crea otro.
- Los backups se guardan en `C:\Asist\instance\backups\produccion\`.
- Se conservan los **últimos 30 backups** (los más viejos se borran
  automáticamente).

---

## 7. Despliegue (dev → prod)

El flujo de trabajo normal es:

1. **Desarrollar en E:** (`E:\Biblioteca\Documentos\Logos\Martin\Asist`).
   - Ahí se usa la planilla de desarrollo.
   - Se prueba todo sin riesgo.
2. **Cuando está probado, desplegar a producción** con el script
   `update_server.bat`.
3. **Commitear los cambios a Git** desde E:.

### Estructura de entornos

| | Producción | Desarrollo |
|---|---|---|
| **Ruta** | `C:\Asist` | `E:\Biblioteca\Documentos\Logos\Martin\Asist` |
| **Planilla** | Asistencia CFL (produccion) | Asistencia CFL (desarrollo) |
| **ENTORNO** | `"produccion"` | `"desarrollo"` |
| **Arranque** | Servicio NSSM | `flask run` o `python app.py` |
| **Git** | No (solo E:) | Sí |

### Cómo desplegar

**En E:**, doble clic sobre `update_server.bat` (o clic derecho →
Ejecutar como administrador).

El script:

1. Detiene el servicio `FlaskServer` en C:.
2. Copia los archivos de E: a C:, respetando exclusiones.
3. Reinicia el servicio `FlaskServer`.

**Exclusiones del `robocopy`** (lo que NO se copia):

- `.git`, `venv`, `__pycache__`, `instance`, `logs`, `.vscode`, `.idea`.
- `config.py` (cada entorno tiene el suyo).
- `asistencia-*.json` (credenciales).
- `*.xlsx`, `*.zip`, `*.pyc`, `*.pyo`, `Eliminar.txt`.
- `.DS_Store`, `Thumbs.db`, `desktop.ini`.

**Parámetro `/IS`**: fuerza la copia incluso si las fechas dicen que
los archivos son iguales. Evita el bug de "archivos no copiados por
fechas raras".

**Parámetro `/MIR`**: hace que C: sea un espejo exacto de E: (borra en
C: lo que no está en E:). **Cuidado**: si borraste algo en E: sin
querer, se borra también en C:.

### Antes de desplegar

1. **Verificar que todo anda en E:** (probar las pantallas principales).
2. **Commitear** los cambios a Git (por las dudas).
3. **Hacer un backup manual** de la carpeta `C:\Asist` a otra ubicación
   (por si algo sale mal).
4. Recién ahí correr `update_server.bat`.

### Después de desplegar

1. **Verificar** que el servicio esté corriendo:
   ```bat
   sc query FlaskServer
   ```
2. **Verificar** que la app responda: entrar a
   `http://192.168.0.10:5000/configuracion` y confirmar que diga:
   - Entorno: **Producción**.
   - Versión: la correcta.
3. **Probar** una operación simple (tomar lista de un curso, entrar a
   `/admin/alumnos`).

---

## 8. Mantenimiento

### Forzar refresco del caché

Si la app muestra datos viejos (por ejemplo, un alumno nuevo no
aparece), se puede forzar la recarga:

1. Ir a `/configuracion`.
2. En la tarjeta "Caché de lecturas", apretar **🔄 Refrescar TODO el
   caché**.
3. Volver a la pantalla donde se veía el dato viejo.

También se puede refrescar **una sola hoja** con el botón 🔄 de cada
fila, o forzar la lectura inmediata con el botón ⬇️.

### Hacer un backup manual

1. Ir a `/configuracion`.
2. En la tarjeta "Backups", apretar **💾 Hacer backup ahora**.
3. El backup se guarda en `instance/backups/<entorno>/<fecha>/`.

### Borrar un backup puntual

En la tarjeta "Backups" de `/configuracion`, apretar el botón 🗑️ de la
fila que se quiere borrar. Se pide confirmación.

### Cambiar la contraseña de admin

La contraseña se usa para:

- Dar de baja a un alumno.
- Reactivar a un alumno.
- Cargar asistencia de una fecha atrasada.

**Para cambiarla**:

1. Abrir `config.py` con el Bloc de Notas.
2. Buscar la línea:
   ```python
   ADMIN_PASSWORD = _valor("ADMIN_PASSWORD", "1234")
   ```
3. Cambiar `"1234"` por la contraseña nueva. **Importante**: usar la
   misma contraseña en `C:\Asist\config.py` y en
   `E:\...\Asist\config.py`.
4. Guardar.
5. Reiniciar el servicio:
   ```bat
   net stop FlaskServer
   net start FlaskServer
   ```

### Cambiar la clave secreta de Flask (`SECRET_KEY`)

La `SECRET_KEY` se usa para firmar sesiones y mensajes flash. **Si se
cambia, las sesiones activas se invalidan** (los usuarios van a tener
que volver a loguearse, aunque en esta app no hay login). No es crítico
en este proyecto, pero es buena práctica.

Para generarla:

```bat
python -c "import secrets; print(secrets.token_hex(32))"
```

Copiar el resultado, pegarlo en `config.py` en la línea de `SECRET_KEY`
(en ambos entornos), guardar y reiniciar el servicio.

### Actualizar dependencias

**⚠️ Cuidado**: actualizar dependencias puede romper cosas. Hacerlo
solo si:

- Hay un bug conocido que se arregla con la versión nueva.
- Hay una vulnerabilidad de seguridad reportada.

**Procedimiento**:

1. **En E: (desarrollo) primero**:
   ```bat
   venv\Scripts\activate
   pip install --upgrade <paquete>
   pip freeze > requirements.txt
   ```
2. **Probar** que la app funcione bien.
3. **Commitear** el `requirements.txt` actualizado.
4. **Desplegar** con `update_server.bat`.
5. **En C: (producción)**, actualizar el venv:
   ```bat
   venv\Scripts\activate
   pip install -r requirements.txt
   ```
6. **Reiniciar** el servicio:
   ```bat
   net stop FlaskServer
   net start FlaskServer
   ```

### Recrear el venv de C: desde cero

Si por algún motivo el venv de C: queda corrupto (por ejemplo, si
muestra rutas de E: en `pip show`), hay que recrearlo.

```bat
cd /d C:\Asist
ren venv venv_viejo
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

**Verificar** que `pip show` apunte a `C:\Asist\venv\...`:

```bat
pip show waitress
```

Una vez confirmado, borrar el venv viejo:

```bat
rmdir /s /q C:\Asist\venv_viejo
```

### Limpiar el log del backup

El log del backup (`C:\Asist\logs\backup_diario.log`) crece con el
tiempo. Se puede borrar cada tantos meses:

```bat
del C:\Asist\logs\backup_diario.log
```

Se regenera solo en el próximo backup.

---

## 9. Solución de problemas frecuentes

### "The caller does not have permission" (Error 403)

**Síntoma**: la app no puede leer ni escribir en Google Sheets.
Aparece en el log con un mensaje tipo:

```
gspread.exceptions.APIError: APIError: [403]: The caller does not have permission
```

**Causa**: la cuenta de servicio no tiene permiso sobre la planilla (o
sobre la carpeta donde está la planilla).

**Solución**:

1. Abrir la planilla (o la carpeta) en Google Drive.
2. Botón "Compartir".
3. Pegar el email de la cuenta de servicio.
4. Permiso: **Editor**.
5. Enviar.

**Tip**: si compartís la **carpeta** `base_datos/` (no la planilla), las
planillas de adentro heredan el permiso automáticamente.

### "ModuleNotFoundError: No module named 'X'"

**Síntoma**: al arrancar la app, tira:

```
ModuleNotFoundError: No module named 'waitress'
```

(o `googleapiclient`, `gspread`, etc.)

**Causa**: falta instalar una dependencia en el venv.

**Solución**:

```bat
cd /d C:\Asist
venv\Scripts\activate
pip install -r requirements.txt
```

**Verificar**:

```bat
pip show waitress
pip show google-api-python-client
```

### El servicio arranca pero la app no responde

**Síntoma**: `sc query FlaskServer` dice `RUNNING`, pero la app no
carga en el navegador.

**Causas posibles**:

1. **El proceso Python se cayó**. Verificar:
   ```bat
   tasklist /FI "SERVICES eq FlaskServer"
   ```
   Debe aparecer `nssm.exe` **y** `python.exe`. Si solo aparece
   `nssm.exe`, Python murió.

2. **La app tira error al arrancar**. Ver el log:
   ```bat
   type C:\Asist\logs\service_stderr.log
   ```
   El error de Python va a estar ahí.

3. **El puerto 5000 está ocupado por otro proceso**. Verificar:
   ```bat
   netstat -ano | findstr :5000
   ```
   Si hay dos procesos escuchando, matar el sobrante con
   `taskkill /PID <pid> /F`.

**Solución**:

- Si es error de Python: revisar el log y arreglar el código.
- Si el puerto está ocupado: identificar el proceso y detenerlo.
- Si nada funciona: reiniciar el servicio:
  ```bat
  net stop FlaskServer
  net start FlaskServer
  ```

### El servicio arranca y se cae inmediatamente

**Síntoma**: `net start FlaskServer` dice "se ha iniciado
correctamente", pero segundos después `sc query FlaskServer` dice
`STOPPED`.

**Causa**: el proceso Python falla al arrancar. NSSM intenta
reiniciarlo y vuelve a fallar en bucle.

**Solución**:

1. Ver el log de errores:
   ```bat
   type C:\Asist\logs\service_stderr.log
   ```
2. Copiar el error y buscar la causa (probablemente un
   `ModuleNotFoundError`, un error de sintaxis, o una credencial
   inválida).

### El servicio no arranca solo con Windows

**Síntoma**: después de reiniciar la PC, el servicio no está corriendo.

**Causa**: el tipo de inicio del servicio no está en "Automático".

**Solución**:

```bat
C:\nssm\win64\nssm.exe set FlaskServer Start SERVICE_AUTO_START
```

O desde la interfaz gráfica de servicios (`services.msc`): buscar
`FlaskServer`, doble clic, y cambiar "Tipo de inicio" a "Automático".

### La app no acepta conexiones desde la red (solo desde localhost)

**Síntoma**: `http://127.0.0.1:5000` funciona, `http://192.168.0.10:5000`
no.

**Causa**: la app está escuchando solo en `127.0.0.1`, no en `0.0.0.0`.

**Verificar**:

```bat
netstat -ano | findstr :5000 | findstr LISTENING
```

- Si dice `127.0.0.1:5000` → mal, solo acepta local.
- Si dice `0.0.0.0:5000` → bien, acepta de cualquier interfaz.

**Solución**: revisar el `app.py` en la última línea:

```python
if __name__ == "__main__":
    from waitress import serve
    serve(app, host="0.0.0.0", port=app.config["PUERTO"])
```

El `host="0.0.0.0"` es fundamental.

### El navegador muestra "No se puede acceder al sitio"

**Causas posibles**:

1. **El servicio está parado**. Verificar con `sc query FlaskServer`.
2. **El firewall de Windows bloquea el puerto**. Abrir el puerto 5000:
   ```bat
   netsh advfirewall firewall add rule name="FlaskServer 5000" dir=in action=allow protocol=TCP localport=5000
   ```
3. **Estás accediendo desde otra red** (por ejemplo, la tablet está
   conectada al WiFi de invitados, y el server está en la red interna).
   Verificar que ambos estén en la misma subred (`192.168.0.x`).

### "Ya existe un backup de hoy. No se hace otro."

**Síntoma**: cuando corrés manualmente la tarea del backup, el log dice
esto y no crea un backup nuevo.

**Causa**: **no es un error**, es el comportamiento esperado. El script
está diseñado para hacer **solo un backup por día**. Si ya se hizo uno,
no hace otro.

**Solución**: si querés forzar un backup nuevo, borrar la carpeta del
backup actual:

```bat
rmdir /s /q C:\Asist\instance\backups\produccion\<fecha_del_backup>
```

Y volver a correr la tarea.

---

## 10. Estructura del código

### Raíz del proyecto

| Archivo | Descripción |
|---|---|
| `app.py` | Punto de entrada. Registra blueprints, arranca waitress. |
| `config.py` | Configuración. **Cada entorno tiene el suyo**. |
| `backup_diario.py` | Script de backup para el Programador de Tareas. |
| `backup_diario.bat` | Wrapper para ejecutar el script de backup. |
| `instalar_tarea_backup.bat` | Registra la tarea programada en Windows. |
| `update_server.bat` | Script de despliegue E: → C:. |
| `start_server.bat` | Arranca la app (usado por el servicio NSSM). |
| `requirements.txt` | Dependencias de Python. |
| `CHANGELOG.md` | Historial de versiones. |
| `PENDIENTES.md` | Lista de mejoras planificadas. |
| `README.md` | Este archivo. |

### `routes/`

Cada archivo agrupa las rutas de un módulo:

| Archivo | Descripción |
|---|---|
| `turnos.py` | Pantallas de selección de turno y curso. |
| `asistencia.py` | Tomar lista, baja y reactivación de alumnos. |
| `dias_especiales.py` | Feriados y ausencias de profesores. |
| `visualizacion_asistencias.py` | Consultas y justificaciones. |
| `admin_alumnos.py` | Administración de alumnos (ABM). |
| `configuracion.py` | Pantalla de configuración, caché, backups. |
| `altas_bajas_modificaciones_alumnos.py` | Módulo viejo (parcialmente reemplazado por `admin_alumnos.py`). |

### `services/`

Lógica de negocio y acceso a datos:

| Archivo | Descripción |
|---|---|
| `sheets.py` | Cliente de Google Sheets. Punto único de acceso. |
| `cache_sheets.py` | Caché en disco de las hojas. |
| `porcentaje_asistencia.py` | Cálculo del porcentaje (ver sección 11). |
| `backup.py` | Sistema de backups locales. |

### `templates/`

Vistas HTML (Jinja2):

| Archivo | Descripción |
|---|---|
| `layout.html` | Plantilla base (barra superior, modos, scripts). |
| `index.html` | Panel principal. |
| `turnos.html`, `turno_*.html` | Selección de turno. |
| `asistencia.html` | Pantalla de tomar lista. |
| `asistencia_atrasada.html` | Selector de fecha atrasada. |
| `dias_especiales.html` | Feriados y ausencias. |
| `visualizacion_asistencias.html` | Consultas. |
| `admin_alumnos*.html` | Administración de alumnos. |
| `configuracion.html` | Pantalla de configuración. |

### `static/`

Archivos estáticos:

| Archivo | Descripción |
|---|---|
| `css/style.css` | Estilos personalizados. |
| `img/favicon.png` | Ícono de la app. |

### Carpetas generadas automáticamente

| Carpeta | Descripción |
|---|---|
| `instance/` | Datos locales: caché y backups. **No se versiona**. |
| `logs/` | Logs del servicio y del backup. **No se versiona**. |
| `venv/` | Entorno virtual de Python. **No se versiona**. |
| `__pycache__/` | Archivos compilados de Python. **No se versiona**. |

---

## 11. Cálculo del porcentaje de asistencia

El porcentaje de asistencia de cada alumno se calcula día por día, no
simplemente contando registros sueltos. La lógica es la siguiente:

### 1. Días totales considerados (denominador)

Se recorre, día por día, el rango que va desde **`INICIO_CICLO`** del
curso (columna en la hoja `Cursos`) hasta una **fecha tope**, que es la
más chica entre:

- la fecha de hoy, o
- el último día en el que se tomó asistencia para ese curso (última
  fecha con algún registro en la hoja `Asistencias` para ese
  `ID_CURSO`).

Usar esta fecha tope (en vez de "hoy" a secas) es lo que evita que el
porcentaje siga bajando artificialmente después de que el curso
terminó y ya no se carga más asistencia: una vez que el curso finaliza,
la fecha tope queda "congelada" en el último día real de clase.

De ese rango de días solo se cuentan los que:

- Coinciden con un día de la semana en que el curso dicta clase, según
  las columnas `LU`, `MA`, `MI`, `JU`, `VI` de la hoja `Cursos` (cada
  curso tiene su propio patrón semanal).
- **No** son feriado (hoja `Feriados`). Los feriados se descuentan del
  total: ese día no cuenta para nadie, ni a favor ni en contra.

### 2. Días asistidos (numerador)

Un día del rango anterior cuenta como "asistido" para un alumno si se
cumple **alguna** de estas dos condiciones:

- El alumno tiene un registro con estado `P` (presente) o `J`
  (justificado) ese día, en la hoja `Asistencias`.
- Ese día el profesor del curso estuvo ausente (hoja
  `Ausencias_Profesores`, filtrado por `ID_CURSO` y fecha).

**Criterio de las ausencias de profesor**: a diferencia de los
feriados, un día de ausencia del profesor **no se resta del total de
días** — sigue contando como un día de clase programado. En cambio, se
le da al alumno el beneficio de la duda y **se cuenta como si hubiera
asistido**, ya que no es su responsabilidad que el profesor no haya
podido dar clase, y no hay forma de saber si el alumno habría asistido
o no ese día.

Cada día se evalúa una sola vez: si por algún motivo coinciden ambas
condiciones el mismo día (por ejemplo, el alumno tiene un `P` cargado
y además ese día el profesor figura ausente), el día suma una sola vez
al numerador, no dos.

### 3. Fórmula final

```
Porcentaje = (días asistidos / días totales considerados) × 100
```

### 4. Clasificación por color

En las pantallas, el porcentaje se muestra con color según el valor:

- **Verde** (`text-success`): >= 90%
- **Amarillo** (`text-warning`): 80% a 89.9%
- **Rojo** (`text-danger`): < 80%

### 5. Casos sin datos suficientes

El cálculo devuelve **"N/D"** (no disponible), en vez de 0%, cuando:

- El curso todavía no tiene `INICIO_CICLO` cargado en la hoja `Cursos`.
- El curso todavía no tiene ningún día de asistencia tomado (recién
  arrancó).
- El alumno no tiene DNI cargado (se muestra "Sin DNI" en ese caso
  particular).

Esto evita mostrar un 0% engañoso que en realidad significa "todavía no
hay información para calcular nada", que es una situación distinta a
"el alumno faltó siempre".

---

## 12. Changelog y versionado

### Versionado

El proyecto usa **Semantic Versioning** (SemVer):

```
MAYOR.MENOR.PARCHE
  ↑     ↑      ↑
  │     │      └── Correcciones chicas (bugs)
  │     └──────── Funcionalidades nuevas (compatible con lo anterior)
  └────────────── Cambios grandes que rompen compatibilidad
```

La versión actual se define en `config.py`:

```python
APP_VERSION = _valor("APP_VERSION", "1.2.1")
```

Y se muestra en la barra superior de la app y en `/configuracion`.

### Changelog

Los cambios importantes se documentan en `CHANGELOG.md`, ordenados de
más nuevo a más viejo. El formato es:

```markdown
## [X.Y.Z] - AAAA-MM-DD

### Agregado
- Cosas nuevas.

### Cambiado
- Cosas que cambiaron de comportamiento.

### Corregido
- Bugs que se arreglaron.

### Eliminado
- Cosas que se sacaron.
```

### Git

El repositorio está en GitHub:
https://github.com/momia007/flask-base

**Flujo de trabajo**:

1. Desarrollar en E:.
2. Probar todo.
3. Commitear:
   ```bat
   git add .
   git status
   git commit -m "vX.Y.Z - Descripción corta"
   git tag -a vX.Y.Z -m "Versión X.Y.Z"
   git push origin main
   git push origin vX.Y.Z
   ```

### Archivos que NO se versionan

Ver `.gitignore`. Los importantes:

- `venv/`, `__pycache__/`
- `instance/` (caché y backups)
- `logs/`
- `config.py` (a futuro, cuando tenga credenciales reales)
- `asistencia-*.json` (credenciales de Google)
- `*.xlsx`, `*.zip`
- `.env`

---

**Fin del README.**