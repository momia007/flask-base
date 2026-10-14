# Changelog

Todos los cambios importantes de esta aplicación se documentan acá.
El formato está basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/)
y este proyecto adhiere a [Semantic Versioning](https://semver.org/lang/es/).

## [Sin publicar]



## [1.2.2] - 2026-10-14

### Agregado
- **README.md completo**: documentación del proyecto con
  arquitectura, instalación desde cero, configuración de Google
  Sheets, configuración del servicio NSSM, tarea programada de
  backup, despliegue, mantenimiento, solución de problemas frecuentes,
  estructura del código y detalle del cálculo del porcentaje.

### Cambiado
- `update_server.bat`: agregado el parámetro `/IS` al `robocopy` para
  forzar la copia de archivos aunque las fechas digan que son iguales.
  Esto evita el bug de "archivos no copiados por fechas raras" que se
  detectó durante el despliegue de la v1.2.0.

### Corregido
- Nada (esta versión es de documentación y ajustes menores).

## [1.2.1] - 2026-10-13

### Agregado
- Script `instalar_tarea_backup.bat` para registrar la tarea programada
  del backup diario en Windows (12:00 todos los días).

### Cambiado
- `backup_diario.py`: ahora hace solo un backup por día (si ya existe uno
  con la fecha de hoy, no crea otro).
- Logs de `backup_diario.py` sin emojis ni acentos, para evitar
  problemas de encoding en la consola de Windows.

## [1.2.0] - 2026-10-09

### Agregado
- **Separación de entornos (desarrollo / producción)** con la variable
  `ENTORNO` en `config.py`:
  - `"produccion"` → usa la planilla real (`Asistencia CFL (produccion)`).
  - `"desarrollo"` → usa una copia (`Asistencia CFL (desarrollo)`).
- Nuevas variables en `config.py`:
  - `SPREADSHEET_ID_PRODUCCION` y `SPREADSHEET_ID_DESARROLLO`
  - `SPREADSHEET_NOMBRE_PRODUCCION` y `SPREADSHEET_NOMBRE_DESARROLLO`
- **Sistema de backups automáticos**:
  - `services/backup.py`: hace copia local (CSV por pestaña) + metadata.
  - `backup_diario.py`: script standalone para ejecutar desde el
    Programador de Tareas de Windows. Solo hace 1 backup por día.
  - `backup_diario.bat`: wrapper para llamar al script.
  - Retención configurable (por defecto: 30 backups).
  - Log en `logs/backup_diario.log`.
- **Sección de backups en `/configuracion`**:
  - Botón "Hacer backup ahora".
  - Tabla con los últimos backups (fecha, motivo, tamaño, ubicaciones).
  - Botón para borrar backups puntuales.
- La pantalla `/configuracion` muestra el **entorno activo** con
  distintivo visual (verde = producción, amarillo = desarrollo).
- Mensaje de error mejorado en `services/sheets.py` cuando la cuenta de
  servicio no tiene acceso a una planilla.
- Archivo `PENDIENTES.md` con la lista de mejoras planificadas.

### Cambiado
- El `update_server.bat` ahora excluye del copiado a producción:
  `.git`, `.vscode`, `.idea`, `instance`, `logs`, `__pycache__`,
  `config.py`, planillas Excel, ZIPs, backups y archivos temporales.
- `config.py` ya no depende de `python-dotenv`. El archivo `.env` sigue
  funcionando si existe, pero ya no es necesario.
- Planillas renombradas sin año (para que no queden desactualizadas):
  `Asistencia CFL (produccion)` y `Asistencia CFL (desarrollo)`.
- `requirements.txt` actualizado: agrega `google-api-python-client` y
  `waitress`.

### Corregido
- El nombre de planilla que aparece en `/configuracion` y en los
  mensajes de error ahora cambia según el entorno.

### Notas
- Los backups en Drive (copia nativa de Google Sheets) están
  desactivados por ahora (`BACKUP_EN_DRIVE = False`) porque la cuenta
  de servicio no tiene cuota propia. Los backups son solo locales.
- Si en el futuro se activa Google Drive para Escritorio en el server,
  se puede sincronizar la carpeta `instance/backups/` a la nube.

  
## [1.1.0] - 2026-10-01

### Agregado
- Filtro por estado (activos / bajas / todos) en las pantallas de tomar lista,
  consultas y administración de alumnos.
- Pantalla "Administrar alumnos" (`/admin/alumnos`) con listado, filtros,
  alta de alumnos nuevos, edición de apellidos y nombres, y cambio de estado.
- Funcionalidad de baja y reactivación de alumnos, con contraseña de admin.
- Reactivación automática al marcar presente a un alumno dado de baja (con
  confirmación y contraseña).
- Botón de acceso a "Administrar alumnos" en el home.
- Valores por defecto de cuatrimestre y año en el alta de alumnos.
- Pantalla de configuración (`/configuracion`) con estado del caché y
  herramientas de mantenimiento.
- Sistema de caché en disco (`instance/cache_sheets.json`) para reducir las
  lecturas a Google Sheets.
- Botón de acceso a configuración (⚙️) en la barra superior.

### Cambiado
- Los alumnos dados de baja ya no se "eliminan" de la vista: se filtran.
- El estado del alumno ahora se guarda en la hoja `Alumnos` (columna `ESTADO`)
  en lugar de registrarse como una asistencia con estado "B".
- Al guardar asistencia, la app vuelve a la misma pantalla (con fecha y filtro
  preservados) en lugar de ir al home.
- La barra superior muestra el nombre de la app y la versión.

### Corregido
- Íconos de la barra superior ya no se superponen con el título de la página.
- Bug en `dias_especiales.filtrar()` que intentaba abrir una hoja con un ID
  inválido (`"..."` literal).

### Eliminado
- Botón "Altas/Bajas/Modificaciones de alumnos" del home (la funcionalidad
  se reemplazó por "Administrar alumnos").

## [1.0.0] - 2026-09-28

### Agregado
- Versión inicial estable.
- Toma de asistencia con selector de turnos (mañana, tarde, vespertino).
- Cálculo automático de porcentaje de asistencia.
- Pantalla de consultas y justificaciones.
- Registro de días especiales (feriados y ausencias de profesores).
- Carga de asistencia atrasada con contraseña de administrador.
- Modo oscuro.