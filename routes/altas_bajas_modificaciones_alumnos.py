# routes/altas_bajas_modificaciones_alumnos.py

from flask import Blueprint, render_template, request
from services.sheets import abrir_hoja

alumnos_bp = Blueprint("altas_bajas_modificaciones_alumnos", __name__, url_prefix="/alumnos")


@alumnos_bp.route("/", methods=["GET", "POST"])
def index():
    alumnos = []
    buscado = False

    if request.method == "POST":
        buscado = True
        dni = request.form.get("dni").strip()
        cuatrimestre = request.form.get("cuatrimestre")

        try:
            # Hoja de alumnos
            sheet_alumnos = abrir_hoja("Alumnos")
            registros = sheet_alumnos.get_all_records()
            print(f"Se leyeron {len(registros)} registros de Alumnos")

            # Hoja de cursos
            sheet_cursos = abrir_hoja("Cursos")
            cursos = sheet_cursos.get_all_records()
            print(f"Se leyeron {len(cursos)} registros de Cursos")

            cursos_dict = {}
            for c in cursos:
                # normalizamos encabezados
                keys = {k.strip().upper(): v for k, v in c.items()}
                if "ID_CURSO" in keys and "CURSO" in keys:
                    cursos_dict[str(keys["ID_CURSO"]).strip()] = keys["CURSO"]

            if cursos:
                print("Claves detectadas en Cursos:", list(cursos[0].keys()))

            for r in registros:
                keys = {k.strip().upper(): v for k, v in r.items()}
                if str(keys.get("ID_ALUMNO", "")).strip() == dni:
                    if cuatrimestre and str(keys.get("CUAT", "")).strip() != cuatrimestre:
                        continue

                    curso_nombre = cursos_dict.get(str(keys.get("ID_CURSO", "")).strip(), keys.get("ID_CURSO", ""))
                    alumnos.append({
                        "dni": keys.get("ID_ALUMNO", ""),
                        "apellido": keys.get("APELLIDOS", ""),
                        "nombre": keys.get("NOMBRES", ""),
                        "curso": curso_nombre,
                        "cuatrimestre": keys.get("CUAT", ""),
                        "anio": keys.get("AÑO", ""),
                        "asistencia": ""  # columna aún no existe
                    })

        except Exception as e:
            print("⚠️ Error en index:", e)

    return render_template("alumnos.html", alumnos=alumnos, buscado=buscado)


# Rutas placeholder para acciones
@alumnos_bp.route("/alta", methods=["GET", "POST"])
def alta():
    if request.method == "POST":
        dni = request.form.get("dni").strip()
        apellido = request.form.get("apellido").strip()
        nombre = request.form.get("nombre").strip()
        curso = request.form.get("curso").strip()
        cuatrimestre = request.form.get("cuatrimestre").strip()
        anio = request.form.get("anio").strip()

        try:
            sheet_alumnos = abrir_hoja("Alumnos")
            # Agregamos la nueva fila al final
            sheet_alumnos.append_row([dni, apellido, nombre, curso, cuatrimestre, anio])
            mensaje = f"Alumno {apellido}, {nombre} agregado correctamente."
        except Exception as e:
            mensaje = f"Error al dar de alta: {e}"

        return render_template("alta_resultado.html", mensaje=mensaje)

    # GET → mostrar formulario con cursos filtrados
    cuatrimestre = request.args.get("cuatrimestre", "")
    sheet_cursos = abrir_hoja("Cursos")
    cursos = sheet_cursos.get_all_records()

    cursos_filtrados = []
    for c in cursos:
        keys = {k.strip().upper(): v for k, v in c.items()}
        if cuatrimestre and str(keys.get("TURNO", "")).strip() != cuatrimestre:
            continue
        cursos_filtrados.append({
            "id": str(keys["ID_CURSO"]).strip(),
            "nombre": keys["CURSO"]
        })

    return render_template("alta_form.html", cursos=cursos_filtrados)


@alumnos_bp.route("/modificar/<dni>")
def modificar(dni):
    return f"Modificar alumno con DNI {dni} (en construcción)"


@alumnos_bp.route("/baja/<dni>")
def baja(dni):
    return f"Dar de baja alumno con DNI {dni} (en construcción)"