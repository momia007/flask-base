# routes/admin_alumnos.py
"""
Pantalla de administración de alumnos.

Permite:
  - Listar y filtrar alumnos (por curso, estado, búsqueda).
  - Dar de alta un alumno nuevo.
  - Editar Apellidos y Nombres.
  - Cambiar estado (baja / reactivar) — requiere contraseña de admin.

NO permite eliminar filas: el estado 'baja' es el mecanismo para "retirar"
un alumno sin perder el registro histórico.
"""

from flask import (
    Blueprint, render_template, request, redirect, url_for,
    flash, current_app, jsonify
)
from services.sheets import (
    abrir_hoja, get_records_cacheado, buscar_fila_alumno
)
from services.cache_sheets import invalidar
from services.porcentaje_asistencia import normalizar_claves

from datetime import datetime

admin_alumnos_bp = Blueprint(
    "admin_alumnos", __name__, url_prefix="/admin/alumnos"
)


# -----------------------------------------------------------------------------
#  Helpers
# -----------------------------------------------------------------------------

def _valor_por_defecto_cuatrimestre():
    """Devuelve el cuatrimestre por defecto para el alta:
       - Si config.py tiene CUATRIMESTRE_FORZADO, usa ese.
       - Si no, lo calcula según el mes actual:
           marzo a julio -> "1"
           agosto a diciembre -> "2"
           enero/febrero -> "1" (asume el ciclo que empieza)
    """
    try:
        from flask import current_app
        forzado = current_app.config.get("CUATRIMESTRE_FORZADO", "")
        if forzado:
            return str(forzado)
    except Exception:
        pass

    mes = datetime.now().month
    if 3 <= mes <= 7:
        return "1"
    if 8 <= mes <= 12:
        return "2"
    # enero o febrero: todavía no arrancó el ciclo, asumimos 1
    return "1"


def _valor_por_defecto_anio():
    """Devuelve el año por defecto para el alta:
       - Si config.py tiene ANIO_FORZADO, usa ese.
       - Si no, usa el año actual del sistema.
    """
    try:
        from flask import current_app
        forzado = current_app.config.get("ANIO_FORZADO", "")
        if forzado:
            return str(forzado)
    except Exception:
        pass

    return str(datetime.now().year)

def _estado_de_alumno(keys):
    """'A' o 'B' según la columna ESTADO. Vacío = 'A'."""
    estado = str(keys.get("ESTADO", "")).strip().upper()
    if estado == "B":
        return "B"
    return "A"


def _cargar_cursos():
    """Lista de cursos con id + nombre + nick, ordenada por nombre."""
    cursos = []
    for c in get_records_cacheado("Cursos"):
        keys = normalizar_claves(c)
        curso_id = str(keys.get("ID_CURSO", "")).strip()
        if not curso_id:
            continue
        cursos.append({
            "id": curso_id,
            "curso": keys.get("CURSO", ""),
            "nick": keys.get("NICK", ""),
            "turno": keys.get("TURNO", ""),
        })
    cursos.sort(key=lambda x: x["curso"])
    return cursos


def _cargar_alumnos(filtro_curso="", filtro_estado="activos", busqueda=""):
    """Carga la lista de alumnos aplicando filtros.

    filtro_estado: 'activos' (default) | 'bajas' | 'todos'
    filtro_curso: id de curso, o "" para todos
    busqueda: texto libre que matchea DNI, Apellidos o Nombres (case-insensitive)
    """
    cursos_por_id = {c["id"]: c for c in _cargar_cursos()}
    busqueda_norm = busqueda.strip().lower()

    alumnos = []
    for r in get_records_cacheado("Alumnos"):
        keys = normalizar_claves(r)
        curso_id = str(keys.get("ID_CURSO", "")).strip()
        estado = _estado_de_alumno(keys)

        if filtro_curso and curso_id != str(filtro_curso).strip():
            continue
        if filtro_estado == "activos" and estado == "B":
            continue
        if filtro_estado == "bajas" and estado != "B":
            continue

        dni = str(keys.get("ID_ALUMNO", "")).strip()       
        apellidos = str(keys.get("APELLIDOS", "")).strip()
        nombres = str(keys.get("NOMBRES", "")).strip()
        if "GUANCA" in apellidos.upper():
            print(f"[DEBUG GUANCA] keys completas: {keys}")
            print(f"[DEBUG GUANCA] dni crudo: {repr(keys.get('ID_ALUMNO', 'NO_EXISTE'))}")
            print(f"[DEBUG GUANCA] dni después de strip: {repr(dni)}")
            print(f"[DEBUG GUANCA] tipo del valor crudo: {type(keys.get('ID_ALUMNO'))}")
            
        if busqueda_norm:
            texto = f"{dni} {apellidos} {nombres}".lower()
            if busqueda_norm not in texto:
                continue

        curso_info = cursos_por_id.get(curso_id, {})
        alumnos.append({
            "dni": dni,
            "apellidos": apellidos,
            "nombres": nombres,
            "curso_id": curso_id,
            "curso_nombre": curso_info.get("curso", curso_id),
            "curso_nick": curso_info.get("nick", ""),
            "cuatrimestre": keys.get("CUAT", ""),
            "anio": keys.get("AÑO", ""),
            "estado": estado,
            "es_baja": estado == "B",
            "sin_dni": not dni,
        })

    # Orden: por apellido, después nombre
    alumnos.sort(key=lambda a: (a["apellidos"].lower(), a["nombres"].lower()))
    return alumnos


# -----------------------------------------------------------------------------
#  Vistas
# -----------------------------------------------------------------------------

@admin_alumnos_bp.route("/")
def index():
    filtro_curso = request.args.get("curso", "").strip()
    filtro_estado = request.args.get("estado", "activos").strip()
    if filtro_estado not in ("activos", "bajas", "todos"):
        filtro_estado = "activos"
    busqueda = request.args.get("q", "").strip()

    cursos = _cargar_cursos()
    alumnos = _cargar_alumnos(filtro_curso, filtro_estado, busqueda)

    return render_template(
        "admin_alumnos.html",
        cursos=cursos,
        alumnos=alumnos,
        filtro_curso=filtro_curso,
        filtro_estado=filtro_estado,
        busqueda=busqueda,
        total=len(alumnos),
    )


# -----------------------------------------------------------------------------
#  Alta de alumno
# -----------------------------------------------------------------------------

@admin_alumnos_bp.route("/alta", methods=["GET", "POST"])
def alta():
    cursos = _cargar_cursos()

    if request.method == "POST":
        dni = request.form.get("dni", "").strip()
        apellidos = request.form.get("apellidos", "").strip()
        nombres = request.form.get("nombres", "").strip()
        curso_id = request.form.get("curso", "").strip()
        cuatrimestre = request.form.get("cuatrimestre", "").strip()
        anio = request.form.get("anio", "").strip()

        errores = []
        if not dni:
            errores.append("El DNI es obligatorio.")
        if not apellidos:
            errores.append("Los apellidos son obligatorios.")
        if not nombres:
            errores.append("Los nombres son obligatorios.")
        if not curso_id:
            errores.append("El curso es obligatorio.")

        # Chequear que no exista ya (dni + curso)
        if dni and curso_id:
            for a in _cargar_alumnos(filtro_estado="todos"):
                if a["dni"] == dni and a["curso_id"] == curso_id:
                    errores.append(
                        f"Ya existe un alumno con DNI {dni} en el curso seleccionado."
                    )
                    break

        if errores:
            for e in errores:
                flash(e, "danger")
            return render_template(
                "admin_alumnos_alta.html",
                cursos=cursos,
                datos=request.form,
            )

        try:
            hoja = abrir_hoja("Alumnos")
            # Orden de columnas: ID_ALUMNO, APELLIDOS, NOMBRES, ID_CURSO, CUAT., AÑO, ESTADO
            hoja.append_row([dni, apellidos, nombres, curso_id, cuatrimestre, anio, "A"])
            invalidar("Alumnos")
            flash(f"✅ Alumno {apellidos}, {nombres} agregado correctamente.", "success")
            return redirect(url_for("admin_alumnos.index"))
        except Exception as e:
            flash(f"❌ Error al dar de alta: {e}", "danger")
            return render_template(
                "admin_alumnos_alta.html",
                cursos=cursos,
                datos=request.form,
            )

    return render_template(
        "admin_alumnos_alta.html",
        cursos=cursos,
        datos={
            "cuatrimestre": _valor_por_defecto_cuatrimestre(),
            "anio": _valor_por_defecto_anio(),
        },
    )


# -----------------------------------------------------------------------------
#  Edición de alumno (solo Apellidos y Nombres)
# -----------------------------------------------------------------------------

@admin_alumnos_bp.route("/editar", methods=["GET", "POST"])
def editar():
    dni = request.args.get("dni", "").strip() or request.form.get("dni", "").strip()
    curso_id = request.args.get("curso", "").strip() or request.form.get("curso", "").strip()

    if not dni or not curso_id:
        flash("Faltan datos para editar.", "danger")
        return redirect(url_for("admin_alumnos.index"))

    fila, cols = buscar_fila_alumno(dni, curso_id)
    if not fila:
        flash(f"No se encontró al alumno {dni} en el curso {curso_id}.", "danger")
        return redirect(url_for("admin_alumnos.index"))

    if request.method == "POST":
        apellidos = request.form.get("apellidos", "").strip()
        nombres = request.form.get("nombres", "").strip()

        if not apellidos or not nombres:
            flash("Apellidos y nombres son obligatorios.", "danger")
        else:
            try:
                hoja = abrir_hoja("Alumnos")
                hoja.update_cell(fila, cols["APELLIDOS"], apellidos)
                hoja.update_cell(fila, cols["NOMBRES"], nombres)
                invalidar("Alumnos")
                flash("✅ Datos actualizados correctamente.", "success")
                return redirect(url_for("admin_alumnos.index"))
            except Exception as e:
                flash(f"❌ Error al guardar: {e}", "danger")

    # GET: cargar datos actuales para el formulario
    hoja = abrir_hoja("Alumnos")
    valores = hoja.get_all_values()
    fila_vals = valores[fila - 1]  # -1 porque la lista es 0-based

    def get_col(nombre):
        idx = cols.get(nombre)
        if idx is None:
            return ""
        try:
            return fila_vals[idx - 1]
        except IndexError:
            return ""

    alumno = {
        "dni": get_col("ID_ALUMNO"),
        "apellidos": get_col("APELLIDOS"),
        "nombres": get_col("NOMBRES"),
        "curso_id": get_col("ID_CURSO"),
    }

    # Info del curso para mostrar
    cursos_por_id = {c["id"]: c for c in _cargar_cursos()}
    curso_info = cursos_por_id.get(str(curso_id), {})

    return render_template(
        "admin_alumnos_editar.html",
        alumno=alumno,
        curso_info=curso_info,
    )


# -----------------------------------------------------------------------------
#  Baja / reactivación (AJAX, pide contraseña)
# -----------------------------------------------------------------------------

@admin_alumnos_bp.route("/baja", methods=["POST"])
def baja():
    dni = request.form.get("dni", "").strip()
    curso_id = request.form.get("curso", "").strip()
    password = request.form.get("password", "")

    if password != current_app.config["ADMIN_PASSWORD"]:
        return jsonify({"success": False, "error": "Contraseña incorrecta."}), 403

    fila, cols = buscar_fila_alumno(dni, curso_id)
    if not fila:
        return jsonify({"success": False, "error": "Alumno no encontrado."}), 404
    if "ESTADO" not in cols:
        return jsonify({"success": False, "error": "Falta la columna ESTADO en la hoja."}), 500

    try:
        abrir_hoja("Alumnos").update_cell(fila, cols["ESTADO"], "B")
        invalidar("Alumnos")
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@admin_alumnos_bp.route("/reactivar", methods=["POST"])
def reactivar():
    dni = request.form.get("dni", "").strip()
    curso_id = request.form.get("curso", "").strip()
    password = request.form.get("password", "")

    if password != current_app.config["ADMIN_PASSWORD"]:
        return jsonify({"success": False, "error": "Contraseña incorrecta."}), 403

    fila, cols = buscar_fila_alumno(dni, curso_id)
    if not fila:
        return jsonify({"success": False, "error": "Alumno no encontrado."}), 404
    if "ESTADO" not in cols:
        return jsonify({"success": False, "error": "Falta la columna ESTADO en la hoja."}), 500

    try:
        abrir_hoja("Alumnos").update_cell(fila, cols["ESTADO"], "A")
        invalidar("Alumnos")
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500