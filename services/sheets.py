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

# Exponemos las credenciales para que otros módulos las puedan reutilizar.
# (Por ejemplo, services/backup.py las usa para la API de Drive.)
creds_publicas = creds

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

def buscar_fila_alumno(dni, curso_id):
    """Busca la fila (número 1-based, contando el encabezado) de un alumno
    en la hoja Alumnos, identificado por (ID_ALUMNO, ID_CURSO).

    Devuelve (fila, encabezados) o (None, None) si no se encuentra.

    Uso típico:
        fila, cols = buscar_fila_alumno("12345678", "22")
        if fila:
            hoja.update_cell(fila, cols["ESTADO"], "B")
    """
    hoja = abrir_hoja("Alumnos")
    valores = hoja.get_all_values()
    if not valores:
        return None, None

    # Normalizamos encabezados: strip + upper + sin punto final
    encabezados = [str(h).strip().upper().rstrip(".") for h in valores[0]]
    try:
        col_dni = encabezados.index("ID_ALUMNO") + 1     # +1 porque gspread cuenta desde 1
        col_curso = encabezados.index("ID_CURSO") + 1
    except ValueError:
        return None, None

    dni = str(dni).strip()
    curso_id = str(curso_id).strip()

    for i, fila_vals in enumerate(valores[1:], start=2):  # fila 2 = primer dato
        # Rellenamos por si la fila es más corta
        while len(fila_vals) < len(encabezados):
            fila_vals.append("")
        if (str(fila_vals[col_dni - 1]).strip() == dni
                and str(fila_vals[col_curso - 1]).strip() == curso_id):
            # Devolvemos también un dict {nombre_columna: índice} para
            # que el llamador pueda pedir columnas por nombre.
            cols = {nombre: idx + 1 for idx, nombre in enumerate(encabezados)}
            return i, cols

    return None, None