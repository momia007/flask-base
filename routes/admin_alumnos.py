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
    return "1"


def _valor_por_defecto_anio():
    """Devuelve el año por defecto para el alta:
       - Si config.py tiene ANIO_FORZADO, usa ese.
       - Si no, usa el año actual del sistema.
    """
    try:
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

def _validar_edad_minima(fecha_nac_iso, cuatrimestre, anio):
    """
    Valida que el alumno tenga 18 años cumplidos al cierre del cuatrimestre.

    Reglas:
      - 1° cuatrimestre: 18 años al 30/06/AAAA
      - 2° cuatrimestre: 18 años al 30/11/AAAA

    Parámetros:
      - fecha_nac_iso: string en formato "AAAA-MM-DD" (viene de <input type="date">)
      - cuatrimestre: "1" o "2"
      - anio: string con el año (ej: "2026")

    Devuelve:
      - (True, "") si cumple.
      - (False, "mensaje de error") si no cumple.
    """
    if not fecha_nac_iso or not cuatrimestre or not anio:
        return (False, "Faltan datos para validar la edad (fecha de nacimiento, cuatrimestre o año).")

    try:
        fecha_nac = datetime.strptime(fecha_nac_iso, "%Y-%m-%d").date()
    except Exception:
        return (False, "La fecha de nacimiento no tiene un formato válido.")

    # Chequeo de rango: año razonable
    anio_actual = datetime.now().year
    if fecha_nac.year < 1900 or fecha_nac.year > anio_actual:
        return (False, "La fecha de nacimiento no es válida (año fuera de rango).")

    try:
        anio_int = int(anio)
    except Exception:
        return (False, "El año debe ser un número de 4 dígitos.")

    cuatrimestre = str(cuatrimestre).strip()

    if cuatrimestre == "1":
        fecha_cierre = datetime(anio_int, 6, 30).date()
        nombre_cuatrimestre = "1°"
    elif cuatrimestre == "2":
        fecha_cierre = datetime(anio_int, 11, 30).date()
        nombre_cuatrimestre = "2°"
    else:
        return (False, "El cuatrimestre debe ser 1 o 2.")

    # ¿Tenía 18 años al cierre del cuatrimestre?
    edad_al_cierre = (
        fecha_cierre.year - fecha_nac.year
        - ((fecha_cierre.month, fecha_cierre.day) < (fecha_nac.month, fecha_nac.day))
    )

    if edad_al_cierre >= 18:
        return (True, "")

    fecha_nac_str = fecha_nac.strftime("%d/%m/%Y")
    fecha_cierre_str = fecha_cierre.strftime("%d/%m/%Y")
    msg = (
        f"El alumno debe tener 18 años cumplidos al {fecha_cierre_str} "
        f"para cursar el {nombre_cuatrimestre} cuatrimestre. "
        f"La fecha de nacimiento ingresada ({fecha_nac_str}) no cumple este requisito."
    )
    return (False, msg)

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


def _cargar_alumnos(filtro_curso="", filtro_estado="activos", filtro_anio="", filtro_cuatrimestre="", busqueda=""):
    """Carga la lista de alumnos aplicando filtros.

    filtro_estado: 'activos' (default) | 'bajas' | 'todos'
    filtro_curso: id de curso, o "" para todos
    filtro_anio: año, o "" para todos
    filtro_cuatrimestre: '1' / '2', o "" para todos
    busqueda: texto libre que matchea DNI, Apellidos o Nombres
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

        # Filtro de año
        if filtro_anio:
            anio_alumno = str(keys.get("AÑO", "")).strip()
            if anio_alumno != str(filtro_anio).strip():
                continue

        # Filtro de cuatrimestre
        if filtro_cuatrimestre:
            cuat_alumno = str(keys.get("CUAT", "")).strip()
            if cuat_alumno != str(filtro_cuatrimestre).strip():
                continue

        dni = str(keys.get("ID_ALUMNO", "")).strip()
        apellidos = str(keys.get("APELLIDOS", "")).strip()
        nombres = str(keys.get("NOMBRES", "")).strip()

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
            # --- Campos nuevos ---
            "fecha_nac": keys.get("FECHA_NAC", ""),
            "genero": keys.get("GENERO", ""),
            "nacionalidad": keys.get("NACIONALIDAD", ""),
            "provincia_nac": keys.get("PROVINCIA_NAC", ""),
            "domicilio": keys.get("DOMICILIO", ""),
            "barrio": keys.get("BARRIO", ""),
            "telefono": keys.get("TELEFONO", ""),
            "email": keys.get("EMAIL", ""),
            "cuil": keys.get("CUIL", ""),
            "estudios": keys.get("ESTUDIOS", ""),
            "estado_laboral": keys.get("ESTADO_LABORAL", ""),
            "discapacidad": keys.get("DISCAPACIDAD", ""),
            "telefono_emergencia": keys.get("TELEFONO_EMERGENCIA", ""),
            "fecha_inscripcion": keys.get("FECHA_INSCRIPCION", ""),
            "origen": keys.get("ORIGEN", ""),
            "observaciones": keys.get("OBSERVACIONES", ""),
        })

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

    filtro_anio = request.args.get("anio", "").strip()
    filtro_cuatrimestre = request.args.get("cuatrimestre", "").strip()

    # Por defecto: año y cuatrimestre actuales
    if not filtro_anio:
        filtro_anio = str(datetime.now().year)
    if not filtro_cuatrimestre:
        mes = datetime.now().month
        filtro_cuatrimestre = "1" if 3 <= mes <= 7 else "2"

    busqueda = request.args.get("q", "").strip()

    cursos = _cargar_cursos()
    alumnos = _cargar_alumnos(
        filtro_curso=filtro_curso,
        filtro_estado=filtro_estado,
        filtro_anio=filtro_anio,
        filtro_cuatrimestre=filtro_cuatrimestre,
        busqueda=busqueda,
    )

    return render_template(
        "admin_alumnos.html",
        cursos=cursos,
        alumnos=alumnos,
        filtro_curso=filtro_curso,
        filtro_estado=filtro_estado,
        filtro_anio=filtro_anio,
        filtro_cuatrimestre=filtro_cuatrimestre,
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
        # --- Campos obligatorios, normalizados ---
        dni = "".join(c for c in request.form.get("dni", "") if c.isdigit())
        apellidos = request.form.get("apellidos", "").strip().upper()
        nombres = request.form.get("nombres", "").strip().upper()
        curso_id = request.form.get("curso", "").strip()
        cuatrimestre = request.form.get("cuatrimestre", "").strip()
        anio = request.form.get("anio", "").strip()

        # --- Fecha de nacimiento ---
        fecha_nac_iso = request.form.get("fecha_nac", "").strip()
        fecha_nac = ""
        if fecha_nac_iso:
            try:
                fecha_nac = datetime.strptime(fecha_nac_iso, "%Y-%m-%d").strftime("%d/%m/%Y")
            except Exception:
                fecha_nac = ""  # si no se pudo parsear, guardar vacío

        # --- Nacionalidad: si es OTRO o país no conocido, tomar el campo de texto ---
        nacionalidad_raw = request.form.get("nacionalidad", "").strip()
        paises_conocidos = [
            "ARGENTINA", "BOLIVIA", "BRASIL", "CHILE", "COLOMBIA", "ECUADOR",
            "PARAGUAY", "PERU", "URUGUAY", "VENEZUELA",
        ]
        if nacionalidad_raw.upper() in paises_conocidos:
            nacionalidad = nacionalidad_raw.upper()
        else:
            # Es OTRO o un país no conocido, tomamos el campo de texto
            nacionalidad = request.form.get("pais_otro", "").strip().upper()

        # --- Resto de campos ---
        genero = request.form.get("genero", "").strip()
        provincia_nac = request.form.get("provincia_nac", "").strip().upper()
        domicilio = request.form.get("domicilio", "").strip().upper()
        barrio = request.form.get("barrio", "").strip().upper()
        telefono = request.form.get("telefono", "").strip()
        email = request.form.get("email", "").strip().lower()
        cuil = "".join(c for c in request.form.get("cuil", "") if c.isdigit())
        estudios = request.form.get("estudios", "").strip()
        estado_laboral = request.form.get("estado_laboral", "").strip()
        discapacidad = request.form.get("discapacidad", "").strip()
        telefono_emergencia = request.form.get("telefono_emergencia", "").strip()
        observaciones = request.form.get("observaciones", "").strip().upper()

        fecha_inscripcion = datetime.now().strftime("%d/%m/%Y")
        origen = "MANUAL"

        # --- Validaciones ---
        errores = []
        if not dni:
            errores.append("El DNI es obligatorio.")
        if not apellidos:
            errores.append("Los apellidos son obligatorios.")
        if not nombres:
            errores.append("Los nombres son obligatorios.")
        if not curso_id:
            errores.append("El curso es obligatorio.")

        # Validar edad mínima
        cumple, msg_error = _validar_edad_minima(fecha_nac_iso, cuatrimestre, anio)
        if not cumple:
            errores.append(msg_error)

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
            hoja.append_row([
                dni, apellidos, nombres, curso_id, cuatrimestre, anio, "A",
                fecha_nac, genero, nacionalidad, provincia_nac, domicilio, barrio,
                telefono, email, cuil, estudios, estado_laboral, discapacidad,
                telefono_emergencia, fecha_inscripcion, origen, observaciones,
            ])
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
#  Edición de alumno 
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
        apellidos = request.form.get("apellidos", "").strip().upper()
        nombres = request.form.get("nombres", "").strip().upper()
        cuatrimestre = request.form.get("cuatrimestre", "").strip()
        anio = request.form.get("anio", "").strip()
        fecha_nac_iso = request.form.get("fecha_nac", "").strip()

        # Fecha de nacimiento: de ISO a dd/mm/aaaa
        fecha_nac = ""
        if fecha_nac_iso:
            try:
                fecha_nac = datetime.strptime(fecha_nac_iso, "%Y-%m-%d").strftime("%d/%m/%Y")
            except Exception:
                fecha_nac = ""

        # Nacionalidad: si es OTRO o país no conocido, tomar el campo de texto
        nacionalidad_raw = request.form.get("nacionalidad", "").strip()
        paises_conocidos = [
            "ARGENTINA", "BOLIVIA", "BRASIL", "CHILE", "COLOMBIA", "ECUADOR",
            "PARAGUAY", "PERU", "URUGUAY", "VENEZUELA",
        ]
        if nacionalidad_raw.upper() in paises_conocidos:
            nacionalidad_final = nacionalidad_raw.upper()
        else:
            nacionalidad_final = request.form.get("pais_otro", "").strip().upper()

        if not apellidos or not nombres:
            flash("Apellidos y nombres son obligatorios.", "danger")
        else:
            # Validar edad mínima
            cumple, msg_error = _validar_edad_minima(fecha_nac_iso, cuatrimestre, anio)
            if not cumple:
                flash(msg_error, "danger")
            else:
                try:
                    hoja = abrir_hoja("Alumnos")

                    campos = {
                        "APELLIDOS": apellidos,
                        "NOMBRES": nombres,
                        "CUAT": cuatrimestre,
                        "AÑO": anio,
                        "FECHA_NAC": fecha_nac,
                        "GENERO": request.form.get("genero", "").strip(),
                        "NACIONALIDAD": nacionalidad_final,
                        "PROVINCIA_NAC": request.form.get("provincia_nac", "").strip().upper(),
                        "DOMICILIO": request.form.get("domicilio", "").strip().upper(),
                        "BARRIO": request.form.get("barrio", "").strip().upper(),
                        "TELEFONO": request.form.get("telefono", "").strip(),
                        "EMAIL": request.form.get("email", "").strip().lower(),
                        "CUIL": "".join(c for c in request.form.get("cuil", "") if c.isdigit()),
                        "ESTUDIOS": request.form.get("estudios", "").strip(),
                        "ESTADO_LABORAL": request.form.get("estado_laboral", "").strip(),
                        "DISCAPACIDAD": request.form.get("discapacidad", "").strip(),
                        "TELEFONO_EMERGENCIA": request.form.get("telefono_emergencia", "").strip(),
                        "FECHA_INSCRIPCION": request.form.get("fecha_inscripcion", "").strip(),
                        "OBSERVACIONES": request.form.get("observaciones", "").strip().upper(),
                    }

                    for nombre_col, valor in campos.items():
                        if nombre_col in cols:
                            hoja.update_cell(fila, cols[nombre_col], valor)

                    invalidar("Alumnos")
                    flash("✅ Datos actualizados correctamente.", "success")
                    return redirect(url_for("admin_alumnos.index"))
                except Exception as e:
                    flash(f"❌ Error al guardar: {e}", "danger")

    # --- GET: cargar datos actuales para el formulario ---
    hoja = abrir_hoja("Alumnos")
    valores = hoja.get_all_values()
    fila_vals = valores[fila - 1]

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
        "cuatrimestre": get_col("CUAT"),
        "anio": get_col("AÑO"),
        "fecha_nac": get_col("FECHA_NAC"),
        "genero": get_col("GENERO"),
        "nacionalidad": get_col("NACIONALIDAD"),
        "provincia_nac": get_col("PROVINCIA_NAC"),
        "domicilio": get_col("DOMICILIO"),
        "barrio": get_col("BARRIO"),
        "telefono": get_col("TELEFONO"),
        "email": get_col("EMAIL"),
        "cuil": get_col("CUIL"),
        "estudios": get_col("ESTUDIOS"),
        "estado_laboral": get_col("ESTADO_LABORAL"),
        "discapacidad": get_col("DISCAPACIDAD"),
        "telefono_emergencia": get_col("TELEFONO_EMERGENCIA"),
        "fecha_inscripcion": get_col("FECHA_INSCRIPCION"),
        "origen": get_col("ORIGEN"),
        "observaciones": get_col("OBSERVACIONES"),
    }

    # Versión ISO de la fecha de nacimiento (para el <input type="date">)
    fecha_nac_valor = alumno.get("fecha_nac", "").strip()
    alumno["fecha_nac_iso"] = ""
    if fecha_nac_valor:
        for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
            try:
                d = datetime.strptime(fecha_nac_valor, fmt)
                alumno["fecha_nac_iso"] = d.strftime("%Y-%m-%d")
                break
            except ValueError:
                continue

    # Campo auxiliar para el "Especificar país" (si la nacionalidad no es de la lista)
    paises_conocidos = [
        "ARGENTINA", "BOLIVIA", "BRASIL", "CHILE", "COLOMBIA", "ECUADOR",
        "PARAGUAY", "PERU", "URUGUAY", "VENEZUELA",
    ]
    nac = alumno["nacionalidad"].strip().upper()
    alumno["pais_otro"] = "" if (not nac or nac in paises_conocidos) else alumno["nacionalidad"]

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