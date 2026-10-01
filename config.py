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
#      3. No cambies los nombres que están a la IZQUIERDA del signo igual
#         (SPREADSHEET_ID, APP_VERSION, etc.). Esos son "etiquetas" fijas.
#      4. Guardá el archivo con el mismo nombre: config.py
#      5. Reiniciá la aplicación para que los cambios tomen efecto. Si no sabes
#         cómo hacerlo, simplemente reiniciá el servidor.
#
#  NOTA: si existe un archivo ".env" en la misma carpeta, los valores que
#  estén ahí pisan a los de este archivo. Si no sabés qué es un .env,
#  ignoralo: esta configuración funciona igual.
#
# =============================================================================

import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # Si python-dotenv no está instalado, seguimos sin .env. No es un error.
    pass


def _valor(nombre_env, por_defecto):
    """Devuelve el valor de la variable de entorno si existe; si no,
    el valor por defecto escrito más abajo. No hace falta tocar esto."""
    return os.getenv(nombre_env, por_defecto)


# -----------------------------------------------------------------------------
#  BASE DE DATOS (Google Sheets)
# -----------------------------------------------------------------------------
#
#  Para obtener el ID del archivo de Google Sheets:
#    1. Abrí la hoja de cálculo en el navegador.
#    2. Mirá la dirección (URL). Tiene esta forma:
#
#       https://docs.google.com/spreadsheets/d/1g62nLCsvCV3iO2o8NPcwcpHErdFdpwRDthDFwm-Y1TE/edit
#                                             └──────────────────── ESTO ──────────────────┘
#
#    3. Copiá solamente la parte que está entre "/d/" y "/edit".
#    4. Pegala entre las comillas de abajo.
#
#  IMPORTANTE: la cuenta de servicio (el archivo .json) debe tener permiso
#  de EDICIÓN sobre esta hoja. Si cambiás de hoja, compartila primero con
#  la misma cuenta de servicio.

SPREADSHEET_ID = _valor(
    "SPREADSHEET_ID",
    "1g62nLCsvCV3iO2o8NPcwcpHErdFdpwRDthDFwm-Y1TE"
)

# Nombre "humano" de la planilla. Solo se usa para mostrar en mensajes de
# error o logs. No afecta al funcionamiento.
SPREADSHEET_NOMBRE = _valor("SPREADSHEET_NOMBRE", "Base Asistencia 2026")


# -----------------------------------------------------------------------------
#  IDENTIDAD DE LA APLICACIÓN
# -----------------------------------------------------------------------------
#
#  Estos valores se muestran en la pantalla (barra superior, título).
#  No afectan al funcionamiento, solo a lo que ve el usuario.

# Nombre del centro / institución. Aparece en el título de las páginas.
APP_NOMBRE = _valor("APP_NOMBRE", "C.F.L. Manuel Belgrano")

# Versión actual. Formato recomendado: MAYOR.MENOR.PARCHE
#   - MAYOR: cambia cuando hay cambios grandes que rompen compatibilidad
#   - MENOR: cambia cuando se agregan funcionalidades nuevas
#   - PARCHE: cambia por correcciones chicas
#  Arrancamos con la 1.0.0 (primera versión estable).
APP_VERSION = _valor("APP_VERSION", "1.0.0")


# -----------------------------------------------------------------------------
#  SEGURIDAD
# -----------------------------------------------------------------------------
#
#  Contraseña que se pide para tareas sensibles:
#    - Cargar asistencia de una fecha pasada (atrasada)
#    - Dar de baja a un alumno
#
#  ⚠️  CAMBIÁ ESTA CONTRASEÑA por una propia antes de usar la app en serio.

ADMIN_PASSWORD = _valor("ADMIN_PASSWORD", "1234")

# Clave secreta de Flask (para sesiones, mensajes flash firmados, etc.).
# En producción conviene que sea un texto largo y aleatorio.
SECRET_KEY = _valor("SECRET_KEY", "default_secret_cambiar_en_produccion")


# -----------------------------------------------------------------------------
#  SERVIDOR (avanzado, normalmente no hace falta tocar)
# -----------------------------------------------------------------------------

# Puerto donde corre la aplicación. Si otra app ya usa el 5000, cambialo
# por otro número (por ejemplo 5001, 8000, etc.).
PUERTO = int(_valor("PUERTO", "5000"))

# Activar modo debug (muestra más info de errores, recarga solo al guardar).
# En producción conviene dejarlo en "False".
DEBUG = _valor("DEBUG", "False").lower() in ("1", "true", "yes", "si", "sí")

# -----------------------------------------------------------------------------
#  CACHÉ DE LECTURAS (avanzado)
# -----------------------------------------------------------------------------
#
#  La app lee las hojas de Google Sheets muchas veces. Para no pasarse del
#  límite que impone Google (y para que la app ande más rápido), guardamos
#  los datos en un archivo local durante un rato y los reutilizamos.
#
#  Los valores de abajo son los SEGUNDOS que dura cada caché antes de
#  refrescarse solo desde Google Sheets. Después de ese tiempo, la próxima
#  lectura trae datos frescos automáticamente.
#
#  Si NO querés esperar, hay una pantalla en /configuracion con un botón
#  para forzar la recarga sin reiniciar la app.
#
#  Valores recomendados (podés subirlos o bajarlos, pero pensá que valores
#  muy bajos aumentan las consultas a Google y pueden trabar la app):
#    - Cursos:                  cambia una vez por cuatrimestre
#    - Feriados:                cambian muy rara vez
#    - Alumnos:                 cambian seguido al principio, después poco
#    - Ausencias_Profesores:    se cargan esporádicamente
#    - Asistencias:             se escribe todo el tiempo, corto

TTL_CURSOS = int(_valor("TTL_CURSOS", str(24 * 60 * 60)))        # 24 horas
TTL_FERIADOS = int(_valor("TTL_FERIADOS", str(24 * 60 * 60)))    # 24 horas
TTL_ALUMNOS = int(_valor("TTL_ALUMNOS", str(6 * 60 * 60)))       # 6 horas
TTL_AUSENCIAS = int(_valor("TTL_AUSENCIAS", str(2 * 60 * 60)))   # 2 horas
TTL_ASISTENCIAS = int(_valor("TTL_ASISTENCIAS", str(30)))        # 30 segundos


# =============================================================================
#  FIN DE LA CONFIGURACIÓN EDITABLE
# =============================================================================
#  A partir de acá hay código interno. No hace falta tocarlo.
# =============================================================================

class Config:
    """Clase que Flask usa para cargar la configuración.
    NO EDITAR: solo toma los valores definidos arriba y los expone
    como atributos de la app (app.config['ADMIN_PASSWORD'], etc.)."""

    SECRET_KEY = SECRET_KEY
    ADMIN_PASSWORD = ADMIN_PASSWORD
    APP_VERSION = APP_VERSION
    APP_NOMBRE = APP_NOMBRE
    SPREADSHEET_ID = SPREADSHEET_ID
    SPREADSHEET_NOMBRE = SPREADSHEET_NOMBRE
    DEBUG = DEBUG
    PUERTO = PUERTO
    
    # TTLs del caché (en segundos)
    TTL_CURSOS = TTL_CURSOS
    TTL_FERIADOS = TTL_FERIADOS
    TTL_ALUMNOS = TTL_ALUMNOS
    TTL_AUSENCIAS = TTL_AUSENCIAS
    TTL_ASISTENCIAS = TTL_ASISTENCIAS

    # Compatibilidad con el config viejo (por si algún módulo lo usa)
    GOOGLE_SHEETS_KEY = _valor("GOOGLE_SHEETS_KEY", "")