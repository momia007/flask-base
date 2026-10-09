# config.py
# =============================================================================
#  CONFIGURACIÓN DE LA APLICACIÓN
# =============================================================================
#
#  Este archivo se puede editar con el Bloc de notas (o cualquier editor de
#  texto simple). NO hace falta saber programar: solo cambiar lo que está
#  entre comillas (") a la derecha del signo igual (=).
#
#  ⚠️  REGLAS BÁSICAS PARA NO ROMPER NADA:
#      1. Cambiá SOLO el texto que está entre comillas. No borres las comillas.
#      2. No borres las comas (,) al final de cada línea.
#      3. No cambies los nombres que están a la IZQUIERDA del signo igual.
#      4. Guardá el archivo con el mismo nombre: config.py
#      5. Reiniciá la aplicación para que los cambios tomen efecto.
#
# =============================================================================

import os


def _valor(nombre_env, por_defecto):
    """Devuelve el valor de la variable de entorno si existe; si no,
    el valor por defecto. No hace falta tocar esto."""
    return os.getenv(nombre_env, por_defecto)


# -----------------------------------------------------------------------------
#  ENTORNO: ¿ESTE EQUIPO ES DE DESARROLLO O DE PRODUCCIÓN?
# -----------------------------------------------------------------------------
#
#  ⚠️  IMPORTANTE: este es el valor que tenés que cambiar en cada equipo.
#
#  Opciones:
#    "produccion" → usa la planilla REAL (la que ven los alumnos)
#    "desarrollo" → usa una COPIA de la planilla (para probar sin riesgo)
#
#  En cada equipo (C: y E:) este archivo tiene el valor que corresponde.
#  El .bat NO copia este archivo, así que no se pisan entre sí.
#
#  ¿Cómo hago la copia de la planilla para desarrollo?
#    1. Abrí la planilla real en Google Sheets.
#    2. Archivo → Hacer una copia.
#    3. Renombrala "Base Asistencia 2026 - DEV".
#    4. Copiá su ID de la URL (lo que está entre /d/ y /edit).
#    5. Pegalo abajo, en SPREADSHEET_ID_DESARROLLO.
#    6. Compartila con la misma cuenta de servicio (la del .json).

ENTORNO = _valor("ENTORNO", "desarrollo")   # "produccion" o "desarrollo"


# -----------------------------------------------------------------------------
#  IDs DE LAS PLANILLAS
# -----------------------------------------------------------------------------
#
#  ID de la planilla REAL (la que usan los alumnos).
SPREADSHEET_ID_PRODUCCION = _valor(
    "SPREADSHEET_ID_PRODUCCION",
    "1g62nLCsvCV3iO2o8NPcwcpHErdFdpwRDthDFwm-Y1TE"
)

# ID de la planilla de DESARROLLO (una copia).
# Completalo cuando crees la copia. Mientras esté con el mismo ID que la
# de producción, es porque todavía no hiciste la copia.
SPREADSHEET_ID_DESARROLLO = _valor(
    "SPREADSHEET_ID_DESARROLLO",
    "1gt1MI9Y8vF3L7zT_X4yURo9FtFGFz_Bf8B-xY2aJG9k"
)

# -----------------------------------------------------------------------------
#  NOMBRES DE LAS PLANILLAS
# -----------------------------------------------------------------------------
#
#  Nombre "humano" de cada planilla. Solo se usa para mostrar en logs y
#  mensajes de error. No afecta al funcionamiento.

SPREADSHEET_NOMBRE_PRODUCCION = _valor(
    "SPREADSHEET_NOMBRE_PRODUCCION",
    "Asistencia CFL (produccion)"
)

SPREADSHEET_NOMBRE_DESARROLLO = _valor(
    "SPREADSHEET_NOMBRE_DESARROLLO",
    "Asistencia CFL (desarrollo)"
)


def _spreadsheet_nombre_activo():
    """Devuelve el nombre de planilla que corresponde según ENTORNO.
    No hace falta tocar esto."""
    if ENTORNO == "desarrollo":
        return SPREADSHEET_NOMBRE_DESARROLLO
    return SPREADSHEET_NOMBRE_PRODUCCION


SPREADSHEET_NOMBRE = _spreadsheet_nombre_activo()


def _spreadsheet_id_activo():
    """Devuelve el ID de planilla que corresponde según ENTORNO.
    No hace falta tocar esto."""
    if ENTORNO == "desarrollo":
        return SPREADSHEET_ID_DESARROLLO
    return SPREADSHEET_ID_PRODUCCION


SPREADSHEET_ID = _spreadsheet_id_activo()


# -----------------------------------------------------------------------------
#  IDENTIDAD DE LA APLICACIÓN
# -----------------------------------------------------------------------------
#
#  Estos valores se muestran en la pantalla (barra superior, título).
#  No afectan al funcionamiento, solo a lo que ve el usuario.

APP_NOMBRE = _valor("APP_NOMBRE", "Centro de Formación")
APP_VERSION = _valor("APP_VERSION", "1.2.0")


# -----------------------------------------------------------------------------
#  SEGURIDAD
# -----------------------------------------------------------------------------
#
#  Contraseña que se pide para tareas sensibles.
#  ⚠️  CAMBIÁ ESTA CONTRASEÑA antes de usar la app en serio.

ADMIN_PASSWORD = _valor("ADMIN_PASSWORD", "1234")

# Clave secreta de Flask (para sesiones y mensajes flash firmados).
SECRET_KEY = _valor("SECRET_KEY", "default_secret_cambiar_en_produccion")


# -----------------------------------------------------------------------------
#  SERVIDOR
# -----------------------------------------------------------------------------

PUERTO = int(_valor("PUERTO", "5000"))

DEBUG = _valor("DEBUG", "False").lower() in ("1", "true", "yes", "si", "sí")


# -----------------------------------------------------------------------------
#  CACHÉ DE LECTURAS
# -----------------------------------------------------------------------------
#
#  Segundos que dura cada caché antes de refrescarse desde Google Sheets.
#  (Ver /configuracion para forzar refrescos manuales.)

TTL_CURSOS = int(_valor("TTL_CURSOS", str(24 * 60 * 60)))        # 24 horas
TTL_FERIADOS = int(_valor("TTL_FERIADOS", str(24 * 60 * 60)))    # 24 horas
TTL_ALUMNOS = int(_valor("TTL_ALUMNOS", str(6 * 60 * 60)))       # 6 horas
TTL_AUSENCIAS = int(_valor("TTL_AUSENCIAS", str(2 * 60 * 60)))   # 2 horas
TTL_ASISTENCIAS = int(_valor("TTL_ASISTENCIAS", str(30)))        # 30 segundos

# -----------------------------------------------------------------------------
#  BACKUPS AUTOMÁTICOS
# -----------------------------------------------------------------------------
#
#  El sistema puede hacer copias de seguridad de la planilla activa:
#    - Una copia nativa de Google Sheets en una carpeta de Drive
#      (para restaurar con un clic).
#    - Una copia en CSV local en la carpeta instance/backups/
#      (para emergencias si Drive falla).
#
#  ¿Cada cuánto? Se puede hacer manual desde /configuracion, o automático
#  antes de operaciones peligrosas (importaciones masivas, archivado, etc.).
#
#  Los backups viejos se borran automáticamente para no llenar el Drive
#  ni el disco.

# ¿Activar backups? Poné False para desactivar todo.
BACKUP_ACTIVO = _valor("BACKUP_ACTIVO", "True").lower() in ("1", "true", "yes", "si", "sí")

# ¿Guardar copia nativa en Drive?
BACKUP_EN_DRIVE = _valor("BACKUP_EN_DRIVE", "False").lower() in ("1", "true", "yes", "si", "sí")

# ¿Guardar copia en CSV local (instance/backups/)?
BACKUP_EN_LOCAL = _valor("BACKUP_EN_LOCAL", "True").lower() in ("1", "true", "yes", "si", "sí")

# ID de la carpeta de Drive donde se guardan los backups.
# Dentro de esta carpeta, el sistema crea subcarpetas por entorno
# ("produccion" / "desarrollo") y una subcarpeta "metadata".
BACKUP_DRIVE_CARPETA_ID = _valor(
    "BACKUP_DRIVE_CARPETA_ID",
    "1RXRtZ47iU9_LJnfqWapQ1f4EeRJyUwDz"
)

# Carpeta local (relativa a la raíz del proyecto) donde se guardan los CSV.
BACKUP_CARPETA_LOCAL = _valor("BACKUP_CARPETA_LOCAL", "instance/backups")

# ¿Cuántos backups mantener? Al superar este número, se borran los más
# viejos automáticamente (tanto en Drive como en local).
BACKUP_RETENCION = int(_valor("BACKUP_RETENCION", "30"))


# =============================================================================
#  FIN DE LA CONFIGURACIÓN EDITABLE
# =============================================================================
#  A partir de acá hay código interno. No hace falta tocarlo.
# =============================================================================

class Config:
    """Clase que Flask usa para cargar la configuración.
    NO EDITAR: solo toma los valores definidos arriba."""

    SECRET_KEY = SECRET_KEY
    ADMIN_PASSWORD = ADMIN_PASSWORD
    APP_VERSION = APP_VERSION
    APP_NOMBRE = APP_NOMBRE
    SPREADSHEET_ID = SPREADSHEET_ID
    SPREADSHEET_NOMBRE = SPREADSHEET_NOMBRE
    ENTORNO = ENTORNO
    DEBUG = DEBUG
    PUERTO = PUERTO

    TTL_CURSOS = TTL_CURSOS
    TTL_FERIADOS = TTL_FERIADOS
    TTL_ALUMNOS = TTL_ALUMNOS
    TTL_AUSENCIAS = TTL_AUSENCIAS
    TTL_ASISTENCIAS = TTL_ASISTENCIAS

    # Compatibilidad con config viejo
    GOOGLE_SHEETS_KEY = _valor("GOOGLE_SHEETS_KEY", "")

    # Backups
    BACKUP_ACTIVO = BACKUP_ACTIVO
    BACKUP_EN_DRIVE = BACKUP_EN_DRIVE
    BACKUP_EN_LOCAL = BACKUP_EN_LOCAL
    BACKUP_DRIVE_CARPETA_ID = BACKUP_DRIVE_CARPETA_ID
    BACKUP_CARPETA_LOCAL = BACKUP_CARPETA_LOCAL
    BACKUP_RETENCION = BACKUP_RETENCION