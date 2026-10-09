# routes/asistencia.py

from flask import (
    Blueprint, render_template, request, redirect, url_for,
    flash, current_app, jsonify
)
from datetime import datetime
from services.sheets import get_records_cacheado, abrir_hoja, buscar_fila_alumno
from services.cache_sheets import invalidar
from services.porcentaje_asistencia import (
    construir_contexto_asistencia,
    calcular_porcentaje,
    clasificar_riesgo,
    normalizar_claves,
)

asistencia_bp = Blueprint("asistencia", __name__, url_prefix="/asistencia")


# -----------------------------------------------------------------------------
#  Helpers de lectura
# -----------------------------------------------------------------------------

def _estado_de_alumno(keys):
    """Devuelve 'A' o 'B' según la columna ESTADO. Vacío = 'A'."""
    estado = str(keys.get("ESTADO", "")).strip().upper()
    if estado == "B":
        return "B"
    return "A"


def obtener_alumnos(curso_id, filtro_estado="activos"):
    """Devuelve los alumnos de un curso, aplicando filtro de estado.

    filtro_estado:
      - "activos" (default): solo ESTADO != B
      - "bajas": solo ESTADO == B
      - "todos": sin filtro
    """
    registros = get_records_cacheado("Alumnos")
    alumnos = []
    for r in registros:
        keys = normalizar_claves(r)
        if str(keys.get("ID_CURSO", "")).strip() != str(curso_id):
            continue

        estado = _estado_de_alumno(keys)
        if filtro_estado == "activos" and estado == "B":
            continue
        if filtro_estado == "bajas" and estado != "B":
            continue

        alumnos.append({
            "id": keys.get("ID_ALUMNO", ""),
            "apellidos": keys.get("APELLIDOS", ""),
            "nombres": keys.get("NOMBRES", ""),
            "curso": keys.get("ID_CURSO", ""),
            "cuatrimestre": keys.get("CUAT", ""),
            "anio": keys.get("AÑO", ""),
            "estado": estado,           # "A" o "B"
            "es_baja": estado == "B",
        })
    return alumnos


def _presentes_desde_registros(registros, curso, fecha):
    """Filtra en memoria los presentes de un curso en una fecha dada."""
    presentes = []
    fecha_hoy = datetime.strptime(fecha, "%d/%m/%Y").date()

    for r in registros:
        try:
            fecha_registro = datetime.strptime(str(r["FECHA"]), "%d/%m/%Y").date()
            if str(r["ID_CURSO"]) == str(curso) and fecha_registro == fecha_hoy and r["ESTADO"] == "P":
                presentes.append(str(r["ID_ALUMNO"]))
        except Exception as e:
            print("Error parseando registro:", r, e)

    return presentes


# -----------------------------------------------------------------------------
#  Rutas
# -----------------------------------------------------------------------------

@asistencia_bp.route("/<curso>")
def asistencia(curso):
    fecha_param = request.args.get("fecha")  # YYYY-MM-DD
    if fecha_param:
        fecha = datetime.strptime(fecha_param, "%Y-%m-%d").strftime("%d/%m/%Y")
        atrasada = fecha != datetime.now().strftime("%d/%m/%Y")
    else:
        fecha = datetime.now().strftime("%d/%m/%Y")
        atrasada = False

    filtro_estado = request.args.get("estado", "activos")
    if filtro_estado not in ("activos", "bajas", "todos"):
        filtro_estado = "activos"

    registros_asistencias = get_records_cacheado("Asistencias")
    presentes = _presentes_desde_registros(registros_asistencias, curso, fecha)

    alumnos = obtener_alumnos(curso, filtro_estado=filtro_estado)

    # Porcentajes (usa el caché compartido)
    try:
        contexto = construir_contexto_asistencia()
    except Exception as e:
        print("Error construyendo contexto de asistencia:", e)
        contexto = None

    curso_nick = curso
    for alumno in alumnos:
        if not alumno.get("id") or contexto is None:
            alumno["porcentaje_texto"] = None
            alumno["porcentaje_clase"] = "text-muted"
            continue
        porcentaje = calcular_porcentaje(alumno["id"], curso, contexto)
        alumno["porcentaje_texto"] = "N/D" if porcentaje is None else f"{porcentaje}%"
        alumno["porcentaje_clase"] = clasificar_riesgo(porcentaje)

    if contexto is not None:
        curso_row = contexto["cursos_por_id"].get(str(curso))
        if curso_row:
            curso_nick = curso_row.get("NICK", curso)

    return render_template(
        "asistencia.html",
        curso=curso,
        curso_nick=curso_nick,
        fecha=fecha,
        fecha_iso=fecha_param or datetime.now().strftime("%Y-%m-%d"),
        alumnos=alumnos,
        presentes=presentes,
        atrasada=atrasada,
        filtro_estado=filtro_estado,
    )


@asistencia_bp.route("/<curso>/atrasada")
def elegir_fecha_atrasada(curso):
    hoy = datetime.now().strftime("%Y-%m-%d")
    return render_template("asistencia_atrasada.html", curso=curso, hoy=hoy)


@asistencia_bp.route("/<curso>/guardar", methods=["POST"])
def guardar(curso):
    presentes = request.form.getlist("asistencia")
    fecha_hoy = datetime.now().strftime("%d/%m/%Y")
    fecha = request.form.get("fecha", fecha_hoy)

    # Preservamos filtro y fecha para volver a la misma vista
    filtro_estado = request.form.get("filtro_estado", "activos")
    fecha_iso = request.form.get("fecha_iso", "")

    if fecha != fecha_hoy:
        password = request.form.get("password", "")
        if password != current_app.config["ADMIN_PASSWORD"]:
            flash("❌ Contraseña incorrecta. No se guardó la asistencia atrasada.", "danger")
            return redirect(url_for("asistencia.asistencia",
                                    curso=curso,
                                    fecha=fecha_iso,
                                    estado=filtro_estado))

    registros = get_records_cacheado("Asistencias")
    existentes = {
        (str(r.get("ID_CURSO", "")).strip(),
         str(r.get("FECHA", "")).strip(),
         str(r.get("ID_ALUMNO", "")).strip())
        for r in registros
    }

    sheet_asistencias = abrir_hoja("Asistencias")
    agregados = 0
    for alumno_id in presentes:
        clave = (str(curso).strip(), str(fecha).strip(), str(alumno_id).strip())
        if clave in existentes:
            continue
        sheet_asistencias.append_row([fecha, curso, alumno_id, "P", ""])
        agregados += 1

    if agregados > 0:
        invalidar("Asistencias")

    if fecha != fecha_hoy:
        flash(f"✅ Asistencia atrasada del {fecha} guardada correctamente", "success")
    else:
        flash("✅ Asistencia actualizada exitosamente", "success")

    # Volvemos a la MISMA pantalla, preservando fecha y filtro
    return redirect(url_for("asistencia.asistencia",
                            curso=curso,
                            fecha=fecha_iso,
                            estado=filtro_estado))


# -----------------------------------------------------------------------------
#  Baja y reactivación
# -----------------------------------------------------------------------------

@asistencia_bp.route("/<curso>/baja", methods=["POST"])
def dar_de_baja(curso):
    """Marca al alumno como dado de baja (ESTADO = 'B' en Alumnos)."""
    dni = request.form.get("dni", "").strip()
    password = request.form.get("password", "")

    if not dni:
        return jsonify({"success": False, "error": "Falta el DNI del alumno."}), 400

    if password != current_app.config["ADMIN_PASSWORD"]:
        return jsonify({"success": False, "error": "Contraseña incorrecta."}), 403

    try:
        fila, cols = buscar_fila_alumno(dni, curso)
        if not fila:
            return jsonify({"success": False,
                            "error": f"No se encontró al alumno {dni} en el curso {curso}."}), 404
        if "ESTADO" not in cols:
            return jsonify({"success": False,
                            "error": "La hoja Alumnos no tiene la columna ESTADO. Agregala y volvé a intentar."}), 500

        abrir_hoja("Alumnos").update_cell(fila, cols["ESTADO"], "B")
        invalidar("Alumnos")
        return jsonify({"success": True})
    except Exception as e:
        print("Error dando de baja:", e)
        return jsonify({"success": False, "error": str(e)}), 500


@asistencia_bp.route("/<curso>/reactivar", methods=["POST"])
def reactivar(curso):
    """Vuelve a marcar al alumno como activo (ESTADO = 'A' en Alumnos)."""
    dni = request.form.get("dni", "").strip()
    password = request.form.get("password", "")

    if not dni:
        return jsonify({"success": False, "error": "Falta el DNI del alumno."}), 400

    if password != current_app.config["ADMIN_PASSWORD"]:
        return jsonify({"success": False, "error": "Contraseña incorrecta."}), 403

    try:
        fila, cols = buscar_fila_alumno(dni, curso)
        if not fila:
            return jsonify({"success": False,
                            "error": f"No se encontró al alumno {dni} en el curso {curso}."}), 404
        if "ESTADO" not in cols:
            return jsonify({"success": False,
                            "error": "La hoja Alumnos no tiene la columna ESTADO."}), 500

        abrir_hoja("Alumnos").update_cell(fila, cols["ESTADO"], "A")
        invalidar("Alumnos")
        return jsonify({"success": True})
    except Exception as e:
        print("Error reactivando:", e)
        return jsonify({"success": False, "error": str(e)}), 500


# -----------------------------------------------------------------------------
#  Utilidad (usada por turnos.py)
# -----------------------------------------------------------------------------

def cursos_con_lista(fecha):
    registros = get_records_cacheado("Asistencias")
    return set([str(r["ID_CURSO"]) for r in registros if str(r["FECHA"]) == str(fecha)])