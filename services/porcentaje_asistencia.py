# services/porcentaje_asistencia.py
"""
Lógica compartida para calcular el porcentaje de asistencia de un alumno.
Usada tanto por la pantalla de Tomar Lista (routes/asistencia.py) como por
la de Consultas (routes/visualizacion_asistencias.py), para que el número
sea siempre el mismo sin importar desde dónde se lo consulte.

Ver README.md para el detalle completo del criterio de cálculo.

Las lecturas a Google Sheets pasan por services.cache_sheets, así que se
reutilizan entre requests según el TTL configurado en config.py.
"""

from datetime import datetime, date, timedelta
from services.sheets import get_records_cacheado

DIAS_SEMANA = ["LU", "MA", "MI", "JU", "VI"]  # índice 0=lunes ... 4=viernes, igual que date.weekday()


def normalizar_claves(registro):
    """Normaliza encabezados: quita espacios y un punto final, pasa a mayúsculas.
    Así 'CUAT.', 'cuat', ' CUAT ' etc. terminan todos como 'CUAT'."""
    normalizado = {}
    for k, v in registro.items():
        clave = k.strip().upper()
        if clave.endswith("."):
            clave = clave[:-1].strip()
        normalizado[clave] = v
    return normalizado


def parsear_fecha(valor):
    """Acepta fechas en formato dd/mm/aaaa (como usa la hoja Asistencias) o
    aaaa-mm-dd (como usan Feriados, Ausencias_Profesores y a veces Cursos).
    Devuelve un date, o None si no se pudo interpretar."""
    if valor is None or valor == "":
        return None
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    s = str(valor).strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _dia_habilitado(curso_row, fecha):
    """¿Ese curso dicta clase ese día de la semana, según las columnas LU..VI?
    Sábados y domingos nunca cuentan (no existen esas columnas)."""
    idx = fecha.weekday()  # 0=lunes ... 6=domingo
    if idx > 4:
        return False
    columna = DIAS_SEMANA[idx]
    return str(curso_row.get(columna, "0")).strip() == "1"


def construir_contexto_asistencia():
    """Carga UNA sola vez todo lo necesario (cursos, feriados, ausencias de
    profesores y asistencias) para poder calcular el porcentaje de cualquier
    alumno sin volver a golpear la API de Sheets por cada uno. Se arma una
    vez por request y se reutiliza para todos los alumnos de esa request.

    Las lecturas a Sheets usan el caché en disco (services.cache_sheets),
    así que si el caché está fresco ni siquiera toca la API de Google."""

    cursos_por_id = {}
    for c in get_records_cacheado("Cursos"):
        keys = normalizar_claves(c)
        curso_id = str(keys.get("ID_CURSO", "")).strip()
        if curso_id:
            cursos_por_id[curso_id] = keys

    feriados_set = set()
    for f in get_records_cacheado("Feriados"):
        fecha = parsear_fecha(f.get("FECHA"))
        if fecha:
            feriados_set.add(fecha)

    ausencias_por_curso = {}
    for a in get_records_cacheado("Ausencias_Profesores"):
        curso_id = str(a.get("ID_CURSO", "")).strip()
        fecha = parsear_fecha(a.get("FECHA"))
        if curso_id and fecha:
            ausencias_por_curso.setdefault(curso_id, set()).add(fecha)

    asistencias_raw = get_records_cacheado("Asistencias")

    presentes_por_alumno = {}       # (curso_id, alumno_id) -> set de fechas con P o J
    ultima_fecha_por_curso = {}     # curso_id -> fecha más reciente con CUALQUIER registro
    for r in asistencias_raw:
        curso_id = str(r.get("ID_CURSO", "")).strip()
        alumno_id = str(r.get("ID_ALUMNO", "")).strip()
        fecha = parsear_fecha(r.get("FECHA"))
        estado = r.get("ESTADO")
        if not curso_id or not fecha:
            continue
        if fecha > ultima_fecha_por_curso.get(curso_id, date.min):
            ultima_fecha_por_curso[curso_id] = fecha
        if alumno_id and estado in ("P", "J"):
            presentes_por_alumno.setdefault((curso_id, alumno_id), set()).add(fecha)

    return {
        "cursos_por_id": cursos_por_id,
        "feriados_set": feriados_set,
        "ausencias_por_curso": ausencias_por_curso,
        "presentes_por_alumno": presentes_por_alumno,
        "ultima_fecha_por_curso": ultima_fecha_por_curso,
        "asistencias_raw": asistencias_raw,
        "cache_dias_efectivos": {},   # cache interno, vive solo durante este request
    }


def _dias_efectivos_del_curso(curso_id, contexto):
    """Lista de fechas 'de clase' de un curso: desde INICIO_CICLO hasta la
    fecha tope (hoy, o el último día con asistencia tomada, lo que sea antes),
    respetando el patrón semanal del curso y excluyendo feriados.
    Se calcula una sola vez por curso por request (cache interno)."""
    cache = contexto["cache_dias_efectivos"]
    if curso_id in cache:
        return cache[curso_id]

    curso_row = contexto["cursos_por_id"].get(curso_id)
    if not curso_row:
        cache[curso_id] = []
        return []

    fecha_inicio = parsear_fecha(curso_row.get("INICIO_CICLO"))
    ultima_fecha_asistencia = contexto["ultima_fecha_por_curso"].get(curso_id)

    if not fecha_inicio or not ultima_fecha_asistencia:
        cache[curso_id] = []
        return []

    hoy = datetime.now().date()
    fecha_tope = min(hoy, ultima_fecha_asistencia)

    dias = []
    fecha_actual = fecha_inicio
    while fecha_actual <= fecha_tope:
        if _dia_habilitado(curso_row, fecha_actual) and fecha_actual not in contexto["feriados_set"]:
            dias.append(fecha_actual)
        fecha_actual += timedelta(days=1)

    cache[curso_id] = dias
    return dias


def calcular_porcentaje(alumno_id, curso_id, contexto):
    """Porcentaje de asistencia de un alumno en un curso.

    Criterio (ver README.md para el detalle completo):
    - Días totales = días de clase programados (según LU..VI del curso) desde
      INICIO_CICLO hasta la fecha tope, MENOS los feriados.
    - Un día cuenta como "asistido" si el alumno tiene P o J ese día, O si ese
      día el profesor estuvo ausente (beneficio de la duda). Cada día se
      evalúa una sola vez, sin duplicar el conteo.

    Devuelve None si no se puede calcular todavía (alumno sin DNI, curso sin
    INICIO_CICLO, o curso sin ningún día de asistencia tomado aún).
    """
    alumno_id = str(alumno_id).strip()
    curso_id = str(curso_id).strip()
    if not alumno_id or not curso_id:
        return None

    dias_efectivos = _dias_efectivos_del_curso(curso_id, contexto)
    if not dias_efectivos:
        return None

    fechas_presente = contexto["presentes_por_alumno"].get((curso_id, alumno_id), set())
    fechas_ausencia_profesor = contexto["ausencias_por_curso"].get(curso_id, set())

    asistidos = sum(
        1 for d in dias_efectivos
        if d in fechas_presente or d in fechas_ausencia_profesor
    )
    return round((asistidos / len(dias_efectivos)) * 100, 2)


def clasificar_riesgo(porcentaje):
    """Devuelve una clase CSS de Bootstrap según el porcentaje, para pintar
    el número de riesgo de perder la regularidad:
    - None (sin datos aún) -> texto neutro
    - >= 90              -> verde (text-success)
    - 80 a 89.9...        -> amarillo (text-warning)
    - < 80                -> rojo (text-danger)
    """
    if porcentaje is None:
        return "text-muted"
    if porcentaje >= 90:
        return "text-success"
    if porcentaje >= 80:
        return "text-warning"
    return "text-danger"