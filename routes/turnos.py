# routes/turnos.py

from flask import Blueprint, render_template
from datetime import datetime
from services.sheets import get_records_cacheado

turnos_bp = Blueprint("turnos", __name__)


def cursos_con_lista(fecha):
    """Cursos que ya tienen asistencia cargada para esa fecha."""
    registros = get_records_cacheado("Asistencias")
    cursos_ids = set([str(r["ID_CURSO"]) for r in registros if str(r["FECHA"]) == str(fecha)])
    return cursos_ids


def _parse_hora(valor):
    """Convierte '8:00', '08:00', '10:40', etc. (como llegan desde Sheets,
    con o sin cero adelante) a un objeto time real, para comparar horas
    correctamente sin depender del formato exacto del texto."""
    return datetime.strptime(str(valor).strip(), "%H:%M").time()


def obtener_cursos(turno):
    """Cursos del turno que están EN HORARIO en este momento (uso normal, para tomar lista hoy)."""
    registros = get_records_cacheado("Cursos")
    cursos_filtrados = []
    ahora = datetime.now()
    dia_semana = ["LU", "MA", "MI", "JU", "VI"][ahora.weekday()]
    hora_actual = ahora.time()

    for r in registros:
        if r["TURNO"] == turno:
            if r[dia_semana] == 1:
                try:
                    inicio = _parse_hora(r["INICIO"])
                    fin = _parse_hora(r["FIN"])
                except Exception as e:
                    print(f"Error parseando horario del curso {r.get('ID_CURSO')}:", e)
                    continue
                if inicio <= hora_actual <= fin:
                    cursos_filtrados.append({
                        "id": str(r["ID_CURSO"]),
                        "nick": r["NICK"],
                        "profesor": r["PROFESOR"],
                        "inicio": r["INICIO"],
                        "fin": r["FIN"]
                    })
    return cursos_filtrados


def obtener_todos_los_cursos_del_turno(turno):
    """TODOS los cursos del turno, sin importar día/horario actual.
    Se usa solo para poder acceder a la carga de asistencia atrasada
    de un curso que ahora mismo no está en horario."""
    registros = get_records_cacheado("Cursos")
    cursos = []
    for r in registros:
        if r["TURNO"] == turno:
            cursos.append({
                "id": str(r["ID_CURSO"]),
                "nick": r["NICK"],
                "profesor": r["PROFESOR"],
                "inicio": r["INICIO"],
                "fin": r["FIN"]
            })
    return cursos


@turnos_bp.route("/turnos")
def turnos():
    return render_template("turnos.html")


@turnos_bp.route("/turno_manana")
def turno_manana():
    cursos = obtener_cursos(turno="M")
    fecha = datetime.now().strftime("%d/%m/%Y")
    cursos_con_asistencia = cursos_con_lista(fecha)
    return render_template("turno_manana.html", cursos=cursos, cursos_con_asistencia=cursos_con_asistencia)


@turnos_bp.route("/turno_tarde")
def turno_tarde():
    cursos = obtener_cursos(turno="T")
    fecha = datetime.now().strftime("%d/%m/%Y")
    cursos_con_asistencia = cursos_con_lista(fecha)
    return render_template("turno_tarde.html", cursos=cursos, cursos_con_asistencia=cursos_con_asistencia)


@turnos_bp.route("/turno_vespertino")
def turno_vespertino():
    cursos = obtener_cursos(turno="V")
    fecha = datetime.now().strftime("%d/%m/%Y")
    cursos_con_asistencia = cursos_con_lista(fecha)
    return render_template("turno_vespertino.html", cursos=cursos, cursos_con_asistencia=cursos_con_asistencia)


@turnos_bp.route("/turno_atrasada/<turno>")
def turno_atrasada(turno):
    """Lista TODOS los cursos del turno (sin filtro de horario), para poder
    llegar a la carga de asistencia atrasada de cualquier curso, esté o no
    en horario en este momento."""
    nombres_turno = {"M": "Mañana", "T": "Tarde", "V": "Vespertino"}
    cursos = obtener_todos_los_cursos_del_turno(turno)
    return render_template("turno_atrasada.html",
                           turno=turno,
                           nombre_turno=nombres_turno.get(turno, turno),
                           cursos=cursos)