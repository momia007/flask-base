# routes/dias_especiales.py

from flask import Blueprint, render_template, request, redirect, url_for, flash
from services.sheets import abrir_hoja, get_records_cacheado
from services.cache_sheets import invalidar
from services.porcentaje_asistencia import parsear_fecha, normalizar_claves
from datetime import datetime

dias_especiales_bp = Blueprint("dias_especiales", __name__, url_prefix="/dias_especiales")


# -----------------------------------------------------------------------------
#  Helpers de lectura
# -----------------------------------------------------------------------------

def _formatear_fecha_para_mostrar(valor):
    """Convierte cualquier fecha parseable a dd/mm/aaaa para mostrar en pantalla.
    Si no se puede parsear, devuelve el texto original."""
    fecha = parsear_fecha(valor)
    if not fecha:
        return valor
    return fecha.strftime("%d/%m/%Y")


def _cursos_por_id():
    """Devuelve un dict {id_curso: {nombre, nick, profesor}} a partir de Cursos."""
    resultado = {}
    for c in get_records_cacheado("Cursos"):
        keys = normalizar_claves(c)
        curso_id = str(keys.get("ID_CURSO", "")).strip()
        if curso_id:
            resultado[curso_id] = {
                "id": curso_id,
                "curso": keys.get("CURSO", ""),
                "nick": keys.get("NICK", ""),
                "profesor": keys.get("PROFESOR", ""),
            }
    return resultado


def _cargar_feriados():
    """Lista de feriados ordenada por fecha descendente.
    Cada item tiene: fecha_original, fecha_mostrar, fecha_dt, motivo."""
    registros = get_records_cacheado("Feriados")
    feriados = []
    for r in registros:
        keys = normalizar_claves(r)
        fecha = keys.get("FECHA", "")
        feriados.append({
            "fecha_original": fecha,                        # como está en la hoja
            "fecha_mostrar": _formatear_fecha_para_mostrar(fecha),
            "fecha_dt": parsear_fecha(fecha),               # para ordenar
            "motivo": keys.get("MOTIVO", ""),
        })
    feriados.sort(key=lambda f: f["fecha_dt"] or datetime.min.date(), reverse=True)
    return feriados


def _cargar_ausencias(cursos_por_id=None):
    """Lista de ausencias ordenada por fecha descendente.
    Cada item tiene: fecha_original, fecha_mostrar, fecha_dt, curso_id,
    curso_nombre, profesor, motivo."""
    if cursos_por_id is None:
        cursos_por_id = _cursos_por_id()

    registros = get_records_cacheado("Ausencias_Profesores")
    ausencias = []
    for r in registros:
        keys = normalizar_claves(r)
        fecha = keys.get("FECHA", "")
        curso_id = str(keys.get("ID_CURSO", "")).strip()
        curso_info = cursos_por_id.get(curso_id, {})
        ausencias.append({
            "fecha_original": fecha,
            "fecha_mostrar": _formatear_fecha_para_mostrar(fecha),
            "fecha_dt": parsear_fecha(fecha),
            "curso_id": curso_id,
            "curso_nombre": curso_info.get("curso", curso_id),
            "curso_nick": curso_info.get("nick", ""),
            "profesor": keys.get("PROFESOR", ""),
            "motivo": keys.get("MOTIVO", ""),
        })
    ausencias.sort(key=lambda a: a["fecha_dt"] or datetime.min.date(), reverse=True)
    return ausencias


# -----------------------------------------------------------------------------
#  Helpers de validación (duplicados)
# -----------------------------------------------------------------------------

def _existe_feriado(fecha_iso):
    """¿Ya hay un feriado cargado para esa fecha (aaaa-mm-dd)?"""
    fecha_buscada = parsear_fecha(fecha_iso)
    if not fecha_buscada:
        return False
    for f in _cargar_feriados():
        if f["fecha_dt"] == fecha_buscada:
            return True
    return False


def _existe_ausencia(fecha_iso, curso_id):
    """¿Ya hay una ausencia cargada para ese (curso, fecha)?
    La clave es (fecha, curso), no (fecha, profesor): un mismo profesor
    puede estar ausente en un curso y no en otro."""
    fecha_buscada = parsear_fecha(fecha_iso)
    if not fecha_buscada:
        return False
    for a in _cargar_ausencias():
        if a["fecha_dt"] == fecha_buscada and str(a["curso_id"]).strip() == str(curso_id).strip():
            return True
    return False


# -----------------------------------------------------------------------------
#  Helpers de borrado
# -----------------------------------------------------------------------------

def _indice_fila_feriado(fecha_iso):
    """Devuelve el número de fila (1-based, contando encabezado) del feriado
    con esa fecha, o None si no existe."""
    fecha_buscada = parsear_fecha(fecha_iso)
    if not fecha_buscada:
        return None
    hoja = abrir_hoja("Feriados")
    valores = hoja.get_all_values()  # lista de listas, incluyendo encabezado
    if not valores:
        return None
    encabezados = [str(h).strip().upper() for h in valores[0]]
    try:
        col_fecha = encabezados.index("FECHA")
    except ValueError:
        return None
    for i, fila in enumerate(valores[1:], start=2):  # fila 2 = primer dato
        if len(fila) > col_fecha:
            if parsear_fecha(fila[col_fecha]) == fecha_buscada:
                return i
    return None


def _indice_fila_ausencia(fecha_iso, curso_id):
    """Devuelve el número de fila (1-based) de la ausencia para ese (curso, fecha),
    o None si no existe."""
    fecha_buscada = parsear_fecha(fecha_iso)
    if not fecha_buscada:
        return None
    hoja = abrir_hoja("Ausencias_Profesores")
    valores = hoja.get_all_values()
    if not valores:
        return None
    encabezados = [str(h).strip().upper() for h in valores[0]]
    try:
        col_fecha = encabezados.index("FECHA")
        col_curso = encabezados.index("ID_CURSO")
    except ValueError:
        return None
    for i, fila in enumerate(valores[1:], start=2):
        if len(fila) > max(col_fecha, col_curso):
            if (parsear_fecha(fila[col_fecha]) == fecha_buscada
                    and str(fila[col_curso]).strip() == str(curso_id).strip()):
                return i
    return None


# -----------------------------------------------------------------------------
#  Rutas
# -----------------------------------------------------------------------------

@dias_especiales_bp.route("/")
def index():
    cursos = get_records_cacheado("Cursos")

    # Filtros (vienen por query string, así se pueden compartir los links)
    filtro_feriado_fecha = request.args.get("feriado_fecha", "").strip()
    filtro_ausencia_fecha = request.args.get("ausencia_fecha", "").strip()
    filtro_ausencia_curso = request.args.get("ausencia_curso", "").strip()

    cursos_por_id = _cursos_por_id()

    # Feriados, con filtro opcional
    feriados = _cargar_feriados()
    total_feriados = len(feriados)
    if filtro_feriado_fecha:
        fecha_filtro = parsear_fecha(filtro_feriado_fecha)
        if fecha_filtro:
            feriados = [f for f in feriados if f["fecha_dt"] == fecha_filtro]

    # Ausencias, con filtros opcionales
    ausencias = _cargar_ausencias(cursos_por_id)
    total_ausencias = len(ausencias)
    if filtro_ausencia_fecha:
        fecha_filtro = parsear_fecha(filtro_ausencia_fecha)
        if fecha_filtro:
            ausencias = [a for a in ausencias if a["fecha_dt"] == fecha_filtro]
    if filtro_ausencia_curso:
        ausencias = [a for a in ausencias if str(a["curso_id"]) == str(filtro_ausencia_curso)]

    return render_template(
        "dias_especiales.html",
        cursos=cursos,
        feriados=feriados,
        ausencias=ausencias,
        total_feriados=total_feriados,
        total_ausencias=total_ausencias,
        filtro_feriado_fecha=filtro_feriado_fecha,
        filtro_ausencia_fecha=filtro_ausencia_fecha,
        filtro_ausencia_curso=filtro_ausencia_curso,
    )


@dias_especiales_bp.route("/filtrar", methods=["POST"])
def filtrar():
    """Este endpoint existía para filtrar cursos por día de la semana al cargar
    una ausencia. Lo dejamos por compatibilidad, pero ahora el filtrado de las
    tablas se hace por query string en index()."""
    fecha = request.form["fecha"]
    dt = datetime.strptime(fecha, "%Y-%m-%d")
    dia_semana = ["LU", "MA", "MI", "JU", "VI"][dt.weekday()]
    cursos = get_records_cacheado("Cursos")
    cursos_filtrados = [
        c for c in cursos
        if str(c.get(dia_semana, "0")).strip() == "1"
    ]
    return render_template(
        "dias_especiales.html",
        cursos=cursos_filtrados,
        fecha=fecha,
        feriados=_cargar_feriados(),
        ausencias=_cargar_ausencias(),
        total_feriados=len(_cargar_feriados()),
        total_ausencias=len(_cargar_ausencias()),
        filtro_feriado_fecha="",
        filtro_ausencia_fecha="",
        filtro_ausencia_curso="",
    )


@dias_especiales_bp.route("/guardar", methods=["POST"])
def guardar():
    tipo = request.form["tipo"]
    fecha = request.form["fecha"]      # formato aaaa-mm-dd (input date HTML)
    motivo = request.form["motivo"]

    if tipo == "feriado":
        if _existe_feriado(fecha):
            flash(f"⚠️ Ya hay un feriado registrado para el {fecha}. No se guardó de nuevo.", "warning")
            return redirect(url_for("dias_especiales.index"))

        # Guardamos como aaaa-mm-dd (igual que ya está en la hoja)
        abrir_hoja("Feriados").append_row([fecha, motivo])
        invalidar("Feriados")
        flash(f"✅ Feriado del {fecha} registrado correctamente.", "success")

    elif tipo == "ausencia":
        curso_id = request.form["curso"].strip()
        if not curso_id:
            flash("⚠️ Tenés que elegir un curso.", "warning")
            return redirect(url_for("dias_especiales.index"))

        if _existe_ausencia(fecha, curso_id):
            flash(f"⚠️ Ya hay una ausencia registrada para el curso seleccionado en la fecha {fecha}. No se guardó de nuevo.", "warning")
            return redirect(url_for("dias_especiales.index"))

        # El profesor se toma SIEMPRE de la hoja Cursos (fuente de verdad).
        # Lo que venga del formulario se ignora, así no hay forma de guardar
        # un profesor que no corresponda a ese curso.
        cursos_por_id = _cursos_por_id()
        profesor = cursos_por_id.get(curso_id, {}).get("profesor", "")
        if not profesor:
            flash(f"⚠️ No se encontró el profesor del curso {curso_id} en la hoja Cursos.", "warning")
            return redirect(url_for("dias_especiales.index"))

        abrir_hoja("Ausencias_Profesores").append_row([fecha, curso_id, profesor, motivo])
        invalidar("Ausencias_Profesores")
        flash(f"✅ Ausencia del profesor registrada para el curso seleccionado el {fecha}.", "success")

    return redirect(url_for("dias_especiales.index"))


@dias_especiales_bp.route("/borrar/feriado", methods=["POST"])
def borrar_feriado():
    fecha = request.form["fecha"]        # aaaa-mm-dd
    motivo = request.form.get("motivo", "")

    fila = _indice_fila_feriado(fecha)
    if not fila:
        flash(f"⚠️ No se encontró el feriado del {fecha} en la hoja.", "warning")
        return redirect(url_for("dias_especiales.index"))

    try:
        abrir_hoja("Feriados").delete_rows(fila)
        invalidar("Feriados")
        flash(f"🗑️ Feriado del {fecha} eliminado.", "success")
    except Exception as e:
        flash(f"❌ Error al eliminar: {e}", "danger")

    return redirect(url_for("dias_especiales.index"))


@dias_especiales_bp.route("/borrar/ausencia", methods=["POST"])
def borrar_ausencia():
    fecha = request.form["fecha"]        # aaaa-mm-dd
    curso_id = request.form["curso_id"]

    fila = _indice_fila_ausencia(fecha, curso_id)
    if not fila:
        flash(f"⚠️ No se encontró la ausencia del curso seleccionado para el {fecha}.", "warning")
        return redirect(url_for("dias_especiales.index"))

    try:
        abrir_hoja("Ausencias_Profesores").delete_rows(fila)
        invalidar("Ausencias_Profesores")
        flash(f"🗑️ Ausencia del curso seleccionado para el {fecha} eliminada.", "success")
    except Exception as e:
        flash(f"❌ Error al eliminar: {e}", "danger")

    return redirect(url_for("dias_especiales.index"))