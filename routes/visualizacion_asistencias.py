# routes/visualizacion_asistencias.py

from flask import Blueprint, render_template, request, jsonify, current_app
from services.sheets import abrir_hoja, get_records_cacheado
from services.cache_sheets import invalidar
from services.porcentaje_asistencia import (
    normalizar_claves,
    construir_contexto_asistencia,
    calcular_porcentaje,
)
from datetime import datetime

visualizacion_bp = Blueprint("visualizacion", __name__, url_prefix="/visualizacion")


@visualizacion_bp.route("/")
def index():
    try:
        contexto = construir_contexto_asistencia()
    except Exception as e:
        print("Error construyendo contexto de asistencia:", e)
        contexto = None

    try:
        cursos = get_records_cacheado("Cursos")
    except Exception as e:
        print("Error cargando cursos:", e)
        cursos = []

    try:
        registros_alumnos = get_records_cacheado("Alumnos")
    except Exception as e:
        print("Error cargando alumnos:", e)
        registros_alumnos = []

    alumnos = []
    for r in registros_alumnos:
        keys = normalizar_claves(r)
        dni = keys.get("ID_ALUMNO", "")
        id_curso = keys.get("ID_CURSO", "")

        if not str(dni).strip():
            porcentaje = None
            texto_asistencia = "Sin DNI"
        elif contexto is None:
            porcentaje = None
            texto_asistencia = "N/D"
        else:
            porcentaje = calcular_porcentaje(dni, id_curso, contexto)
            texto_asistencia = "N/D" if porcentaje is None else f"{porcentaje}%"

        alumnos.append({
            "dni": dni,
            "apellido": keys.get("APELLIDOS", ""),
            "nombre": keys.get("NOMBRES", ""),
            "curso": id_curso,
            "cuatrimestre": keys.get("CUAT", ""),
            "anio": keys.get("AÑO", ""),
            "asistencia": texto_asistencia
        })

    return render_template("visualizacion_asistencias.html", cursos=cursos, alumnos=alumnos)


@visualizacion_bp.route("/datos")
def datos():
    curso_id = request.args.get("curso")
    fecha = request.args.get("fecha")

    fecha_formateada = datetime.strptime(fecha, "%Y-%m-%d").strftime("%d/%m/%Y")

    try:
        contexto = construir_contexto_asistencia()
        registros = contexto["asistencias_raw"]
    except Exception as e:
        print("Error construyendo contexto de asistencia:", e)
        contexto = None
        registros = []

    try:
        alumnos = get_records_cacheado("Alumnos")
    except Exception as e:
        print("Error cargando alumnos:", e)
        alumnos = []

    alumnos_curso = [a for a in alumnos if str(a["ID_CURSO"]) == str(curso_id)]

    alumnos_estado = []
    for alumno in alumnos_curso:
        alumno_id = str(alumno.get("ID_ALUMNO", "")).strip()

        if not alumno_id:
            alumnos_estado.append({
                "id": "",
                "nombre": f"{alumno['APELLIDOS']} {alumno['NOMBRES']}",
                "estado": "SIN_DNI",
                "justificacion": "",
                "asistencia": "Sin DNI",
                "sin_id": True
            })
            continue

        registro = next(
            (r for r in registros
             if str(r.get("ID_ALUMNO")) == alumno_id
             and str(r.get("ID_CURSO")) == str(curso_id)
             and r.get("FECHA") == fecha_formateada),
            None
        )
        estado = registro["ESTADO"] if registro else "A"
        detalle = registro.get("DETALLE", "") if registro else ""

        if contexto is None:
            porcentaje = None
        else:
            porcentaje = calcular_porcentaje(alumno_id, curso_id, contexto)

        alumnos_estado.append({
            "id": alumno_id,
            "nombre": f"{alumno['APELLIDOS']} {alumno['NOMBRES']}",
            "estado": estado,
            "justificacion": detalle,
            "asistencia": "N/D" if porcentaje is None else f"{porcentaje}%",
            "sin_id": False
        })

    return jsonify(alumnos_estado)


@visualizacion_bp.route("/fechas")
def fechas():
    curso_id = request.args.get("curso")

    try:
        registros = get_records_cacheado("Asistencias")
    except Exception as e:
        print("Error cargando asistencias:", e)
        registros = []

    fechas = sorted(set(r["FECHA"] for r in registros if str(r["ID_CURSO"]) == str(curso_id)))
    return jsonify(fechas)


@visualizacion_bp.route("/justificar", methods=["POST"])
def justificar():
    alumno_id = request.form.get("alumnoId")
    motivo = request.form.get("motivo")
    curso_id = request.form.get("curso")
    fecha = request.form.get("fecha")

    if not str(alumno_id or "").strip():
        return jsonify({"success": False, "error": "El alumno no tiene DNI cargado; no se puede justificar."}), 400

    fecha_formateada = datetime.strptime(fecha, "%Y-%m-%d").strftime("%d/%m/%Y")

    try:
        abrir_hoja("Asistencias").append_row([fecha_formateada, curso_id, alumno_id, "J", motivo])
        invalidar("Asistencias")
    except Exception as e:
        print("Error insertando justificación:", e)
        return jsonify({"success": False, "error": str(e)}), 500

    return jsonify({"success": True})


@visualizacion_bp.route("/baja", methods=["POST"])
def baja():
    alumno_id = request.form.get("alumnoId")
    curso_id = request.form.get("curso")
    fecha = request.form.get("fecha")
    motivo = request.form.get("motivo", "Baja definitiva")
    password = request.form.get("password")

    if not str(alumno_id or "").strip():
        return jsonify({"success": False, "error": "El alumno no tiene DNI cargado; no se puede dar de baja."}), 400

    if password != current_app.config["ADMIN_PASSWORD"]:
        return jsonify({"success": False, "error": "Contraseña incorrecta"}), 403

    fecha_formateada = datetime.strptime(fecha, "%Y-%m-%d").strftime("%d/%m/%Y")
    try:
        abrir_hoja("Asistencias").append_row([fecha_formateada, curso_id, alumno_id, "B", motivo])
        invalidar("Asistencias")
    except Exception as e:
        print("Error insertando baja:", e)
        return jsonify({"success": False, "error": str(e)}), 500

    return jsonify({"success": True})