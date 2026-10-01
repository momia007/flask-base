# services/sheets.py
"""
Cliente centralizado de Google Sheets.

Este es el ÚNICO lugar de la aplicación donde se abre la planilla de cálculo.
Todos los módulos que necesiten una hoja deben importar desde acá.

El ID de la planilla se lee de config.py, así que para cambiar de planilla
basta con editar ese archivo (no hace falta tocar este código).

Para lecturas frecuentes, usar `get_records_cacheado("Hoja")` en vez de
`abrir_hoja("Hoja").get_all_records()`. El caché vive en
instance/cache_sheets.json y se controla desde /configuracion.
"""

import gspread
from oauth2client.service_account import ServiceAccountCredentials

from config import SPREADSHEET_ID, SPREADSHEET_NOMBRE


scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

creds = ServiceAccountCredentials.from_json_keyfile_name(
    "asistencia-501122-f1cc5a8edf80.json", scope
)
client = gspread.authorize(creds)


def abrir_hoja(nombre_hoja):
    """Abre una pestaña (worksheet) de la planilla configurada.

    Uso:
        from services.sheets import abrir_hoja
        hoja = abrir_hoja("Alumnos")

    Devuelve el objeto worksheet de gspread, listo para usar con
    get_all_records(), append_row(), etc.

    Para lecturas que se repiten seguido, preferí `get_records_cacheado("Alumnos")`.
    """
    try:
        return client.open_by_key(SPREADSHEET_ID).worksheet(nombre_hoja)
    except Exception as e:
        raise RuntimeError(
            f"No se pudo abrir la hoja '{nombre_hoja}' de la planilla "
            f"'{SPREADSHEET_NOMBRE}' (ID: {SPREADSHEET_ID}). "
            f"Verificá que el ID en config.py sea correcto y que la cuenta "
            f"de servicio tenga acceso. Error original: {e}"
        ) from e


def abrir_planilla():
    """Devuelve el objeto spreadsheet completo (por si hace falta listar
    pestañas, por ejemplo). Normalmente conviene usar abrir_hoja()."""
    return client.open_by_key(SPREADSHEET_ID)


def get_records_cacheado(nombre_hoja, forzar_refresco=False):
    """Devuelve los registros de una hoja, usando el caché en disco.

    Es el reemplazo directo de:
        abrir_hoja("X").get_all_records()
    pero con caché automático.

    Si `forzar_refresco=True`, ignora el caché y va a Google directamente.
    """
    # Import acá adentro para evitar dependencia circular con cache_sheets.py
    from services.cache_sheets import get_records
    return get_records(nombre_hoja, forzar_refresco=forzar_refresco)