# routes/asistencia.py

from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from datetime import datetime
from services.sheets import get_records_cacheado, abrir_hoja
from services.cache_sheets import invalidar
from services.porcentaje_asistencia import (
    construir_contexto_asistencia,
    calcular_porcentaje,
    clasificar_riesgo,
)

# Definir el blueprint
asistencia_bp = Blueprint("asistencia", __name__, url_prefix="/asistencia")


def _normalizar_claves(registro):
    """Normaliza encabezados: quita espacios y un punto final, pasa a mayúsculas.
    Así 'CUAT.', 'cuat', ' CUAT ' etc. terminan todos como 'CUAT'."""
    normalizado = {}
    for k, v in registro.items():
        clave = k.strip().upper()
        if clave.endswith("."):
            clave = clave[:-1].strip()
        normalizado[clave] = v
    return normalizado


def obtener_alumnos(curso_id):
    """Alumnos de un curso, desde el caché."""
    registros = get_records_cacheado("Alumnos")
    alumnos = []
    for r in registros:
        keys = _normalizar_claves(r)
        if str(keys.get("ID_CURSO", "")).strip() == str(curso_id):
            alumnos.append({
                "id": keys.get("ID_ALUMNO", ""),
                "apellidos": keys.get("APELLIDOS", ""),
                "nombres": keys.get("NOMBRES", ""),
                "curso": keys.get("ID_CURSO", ""),
                "cuatrimestre": keys.get("CUAT", ""),
                "anio": keys.get("AÑO", "")
            })
    return alumnos


def _presentes_desde_registros(registros, curso, fecha):
    """Filtra en memoria los presentes de un curso en una fecha dada.
    Recibe los registros ya leídos (de la hoja Asistencias) para no volver
    a golpear la API."""
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


@asistencia_bp.route("/<curso>")
def asistencia(curso):
    fecha_param = request.args.get("fecha")  # formato YYYY-MM-DD (de un <input type="date">)
    if fecha_param:
        fecha = datetime.strptime(fecha_param, "%Y-%m-%d").strftime("%d/%m/%Y")
        atrasada = fecha != datetime.now().strftime("%d/%m/%Y")
    else:
        fecha = datetime.now().strftime("%d/%m/%Y")
        atrasada = False

    # Leemos las asistencias UNA sola vez (cacheada) y la reutilizamos
    registros_asistencias = get_records_cacheado("Asistencias")

    alumnos = obtener_alumnos(curso)
    presentes = _presentes_desde_registros(registros_asistencias, curso, fecha)

    # Filtramos alumnos dados de baja, usando los mismos registros ya leídos
    alumnos_filtrados = []
    for alumno in alumnos:
        baja = next(
            (r for r in registros_asistencias
             if str(r["ID_ALUMNO"]) == str(alumno["id"])
             and str(r["ID_CURSO"]) == str(curso)
             and r["ESTADO"] == "B"),
            None
        )
        if baja:
            continue
        alumnos_filtrados.append(alumno)

    # Calculamos el porcentaje de cada alumno (mismo criterio y misma fuente
    # que la pantalla de Consultas, via el módulo compartido)
    try:
        contexto = construir_contexto_asistencia()
    except Exception as e:
        print("Error construyendo contexto de asistencia:", e)
        contexto = None

    curso_nick = curso  # fallback si no encontramos el curso en Cursos
    for alumno in alumnos_filtrados:
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

    return render_template("asistencia.html",
                           curso=curso,
                           curso_nick=curso_nick,
                           fecha=fecha,
                           alumnos=alumnos_filtrados,
                           presentes=presentes,
                           atrasada=atrasada)


@asistencia_bp.route("/<curso>/atrasada")
def elegir_fecha_atrasada(curso):
    """Pantalla simple para elegir qué fecha pasada se quiere cargar/revisar.
    No requiere contraseña: elegir una fecha no modifica nada todavía."""
    hoy = datetime.now().strftime("%Y-%m-%d")
    return render_template("asistencia_atrasada.html", curso=curso, hoy=hoy)


@asistencia_bp.route("/<curso>/guardar", methods=["POST"])
def guardar(curso):
    presentes = request.form.getlist("asistencia")
    fecha_hoy = datetime.now().strftime("%d/%m/%Y")
    fecha = request.form.get("fecha", fecha_hoy)  # viene de un hidden input; si no está, es hoy

    if fecha != fecha_hoy:
        # Carga atrasada: exigimos contraseña de administrador antes de guardar
        password = request.form.get("password", "")
        if password != current_app.config["ADMIN_PASSWORD"]:
            flash("❌ Contraseña incorrecta. No se guardó la asistencia atrasada.", "danger")
            return redirect(url_for("asistencia.asistencia", curso=curso, fecha=datetime.strptime(fecha, "%d/%m/%Y").strftime("%Y-%m-%d")))

    # Leemos una sola vez (cacheado) y chequeamos duplicados en memoria.
    registros = get_records_cacheado("Asistencias")

    # Set con (ID_CURSO, FECHA, ID_ALUMNO) ya existentes, para consultar rápido.
    # OJO: en el caché los valores pueden venir como string o número; normalizamos a str.
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

    # Si escribimos algo, invalidamos el caché de Asistencias para que la
    # próxima lectura traiga datos frescos (no los viejos).
    if agregados > 0:
        invalidar("Asistencias")

    if fecha != fecha_hoy:
        flash(f"✅ Asistencia atrasada del {fecha} guardada correctamente", "success")
    else:
        flash("✅ Asistencia actualizada exitosamente", "success")
    return redirect(url_for("index"))


def cursos_con_lista(fecha):
    """Cursos que ya tienen asistencia cargada para esa fecha."""
    registros = get_records_cacheado("Asistencias")
    return set([str(r["ID_CURSO"]) for r in registros if str(r["FECHA"]) == str(fecha)])