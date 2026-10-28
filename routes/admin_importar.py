# routes/admin_importar.py
"""
Módulo de importación de inscripciones desde Google Forms.

Permite al admin:
  1. Pegar el ID o URL de la planilla de respuestas del Forms.
  2. Elegir el curso, cuatrimestre y año destino.
  3. Ver un preview de los alumnos que se van a importar, con sus
     validaciones (DNI válido, edad mínima, certificación, duplicados).
  4. Elegir cuáles importar (checkbox por fila).
  5. Confirmar la importación.

La importación:
  - Hace un backup automático antes de escribir (si BACKUP_ACTIVO).
  - Agrega las filas a la hoja `Alumnos` con ESTADO = "A" y ORIGEN = "IMPORT".
  - Guarda la "Marca temporal" del Forms como FECHA_INSCRIPCION.
  - Invalida el caché de `Alumnos` al finalizar.
"""

import json
from datetime import datetime

from flask import (
    Blueprint, render_template, request, redirect, url_for,
    flash, current_app, session
)

from services.sheets import abrir_hoja, get_records_cacheado
from services.cache_sheets import invalidar
from services.porcentaje_asistencia import normalizar_claves
from services import importar_forms
from services import backup


admin_importar_bp = Blueprint(
    "admin_importar", __name__, url_prefix="/admin/importar"
)


# -----------------------------------------------------------------------------
#  Helpers
# -----------------------------------------------------------------------------

def _cargar_cursos():
    """Lista de cursos con id + nombre + nick."""
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


def _valor_por_defecto_cuatrimestre():
    """Cuatrimestre por defecto según el mes actual."""
    try:
        forzado = current_app.config.get("CUATRIMESTRE_FORZADO", "")
        if forzado:
            return str(forzado)
    except Exception:
        pass
    mes = datetime.now().month
    return "1" if 3 <= mes <= 7 else "2"


def _valor_por_defecto_anio():
    """Año por defecto: el actual."""
    try:
        forzado = current_app.config.get("ANIO_FORZADO", "")
        if forzado:
            return str(forzado)
    except Exception:
        pass
    return str(datetime.now().year)


def _dnies_existentes_en_curso(curso_id):
    """Set de DNIs que ya están cargados en el curso destino (sin importar estado)."""
    resultado = set()
    for r in get_records_cacheado("Alumnos"):
        keys = normalizar_claves(r)
        if str(keys.get("ID_CURSO", "")).strip() == str(curso_id).strip():
            dni = str(keys.get("ID_ALUMNO", "")).strip()
            if dni:
                resultado.add(dni)
    return resultado


# -----------------------------------------------------------------------------
#  Rutas
# -----------------------------------------------------------------------------

@admin_importar_bp.route("/", methods=["GET"])
def index():
    """Pantalla principal: formulario para cargar el ID de la planilla y
    elegir el curso. Si se mandan parámetros por GET, muestra el preview."""
    cursos = _cargar_cursos()

    # Leer parámetros del GET (para volver al preview después de errores)
    id_planilla = request.args.get("id_planilla", "").strip()
    curso_id = request.args.get("curso", "").strip()
    cuatrimestre = request.args.get("cuatrimestre", "").strip()
    anio = request.args.get("anio", "").strip()

    preview = None
    error = None

    if id_planilla and curso_id and cuatrimestre and anio:
        # Hay parámetros: intentar analizar
        try:
            id_limpio = importar_forms.extraer_id_planilla(id_planilla)
            alumnos_existentes = _dnies_existentes_en_curso(curso_id)

            preview = importar_forms.analizar_planilla(
                id_planilla=id_limpio,
                curso_id=curso_id,
                cuatrimestre=cuatrimestre,
                anio=anio,
                alumnos_existentes=alumnos_existentes,
            )

            # Guardamos el contexto en sesión para usarlo en el POST de confirmar
            session["import_contexto"] = {
                "id_planilla": id_limpio,
                "curso_id": curso_id,
                "cuatrimestre": cuatrimestre,
                "anio": anio,
            }

            # Info del curso para mostrar
            cursos_por_id = {c["id"]: c for c in cursos}
            preview["curso_info"] = cursos_por_id.get(str(curso_id), {})

        except Exception as e:
            error = str(e)

    return render_template(
        "admin_importar.html",
        cursos=cursos,
        id_planilla=id_planilla,
        curso_id=curso_id,
        cuatrimestre=cuatrimestre or _valor_por_defecto_cuatrimestre(),
        anio=anio or _valor_por_defecto_anio(),
        preview=preview,
        error=error,
    )


@admin_importar_bp.route("/confirmar", methods=["POST"])
def confirmar():
    contexto = session.get("import_contexto")
    if not contexto:
        flash("❌ Contexto de importación no encontrado. Volvé a empezar.", "danger")
        return redirect(url_for("admin_importar.index"))

    id_planilla = contexto["id_planilla"]
    curso_id = contexto["curso_id"]
    cuatrimestre = contexto["cuatrimestre"]
    anio = contexto["anio"]

    filas_seleccionadas = request.form.getlist("filas")
    if not filas_seleccionadas:
        flash("⚠️ No seleccionaste ninguna fila para importar.", "warning")
        return redirect(url_for("admin_importar.index", id_planilla=id_planilla, curso=curso_id, cuatrimestre=cuatrimestre, anio=anio))

    indices = set()
    for f in filas_seleccionadas:
        try:
            indices.add(int(f))
        except (ValueError, TypeError):
            continue

    if not indices:
        flash("⚠️ Los índices de fila no son válidos.", "warning")
        return redirect(url_for("admin_importar.index"))

    # --- Backup automático antes de escribir ---
    backup_ok = True
    backup_mensaje = ""
    nombre_backup = ""
    
    if current_app.config.get("BACKUP_ACTIVO", True):
        try:
            resultado_backup = backup.hacer_backup(motivo="pre-importacion")
            if resultado_backup["ok"]:
                nombre_backup = resultado_backup['nombre_backup']
                backup_mensaje = f"Backup automático creado: {nombre_backup}"
            else:
                backup_ok = False
                backup_mensaje = "Backup falló: " + " | ".join(resultado_backup["errores"])
        except Exception as e:
            backup_ok = False
            backup_mensaje = f"Error haciendo backup: {e}"

    if not backup_ok:
        flash(f"❌ No se pudo hacer el backup automático. No se importó nada. {backup_mensaje}", "danger")
        return redirect(url_for("admin_importar.index", id_planilla=id_planilla, curso=curso_id, cuatrimestre=cuatrimestre, anio=anio))

    # --- Releer y re-validar la planilla del Forms ---
    try:
        alumnos_existentes = _dnies_existentes_en_curso(curso_id)
        preview = importar_forms.analizar_planilla(
            id_planilla=id_planilla,
            curso_id=curso_id,
            cuatrimestre=cuatrimestre,
            anio=anio,
            alumnos_existentes=alumnos_existentes,
        )
    except Exception as e:
        flash(f"❌ Error releyendo la planilla del Forms: {e}", "danger")
        return redirect(url_for("admin_importar.index"))

    # --- Escribir en la hoja `Alumnos` ---
    hoja = abrir_hoja("Alumnos")
    importados = 0
    filas_pendientes_log = []
    
    # Nombre del curso para el log
    cursos = _cargar_cursos()
    curso_info = next((c for c in cursos if c["id"] == str(curso_id)), {})
    curso_nombre = curso_info.get("curso", curso_id)

    # ID de importación único
    id_import = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

    for fila in preview["filas"]:
        # Si no fue seleccionada, o si tiene errores, la guardamos como pendiente
        if fila["nro_fila"] not in indices or not fila["valido"]:
            # Solo la guardamos como pendiente si realmente tiene datos (para no llenar de filas vacías)
            if fila["datos"]["dni"] or fila["datos"]["apellidos"]:
                filas_pendientes_log.append(fila)
            continue

        d = fila["datos"]
        try:
            hoja.append_row([
                d["dni"], d["apellidos"], d["nombres"], curso_id, cuatrimestre, anio, "A",
                d["fecha_nac"], d["genero"], d["nacionalidad"], d["provincia_nac"], d["domicilio"], d["barrio"],
                d["telefono"], d["email"], d["cuil"], d["estudios"], d["estado_laboral"], d["discapacidad"],
                d["telefono_emergencia"], d["fecha_inscripcion"], "IMPORT", "",
            ])
            importados += 1
        except Exception as e:
            # Si falla la escritura, lo mandamos a pendientes
            fila["errores"].append(f"Error al escribir en Sheets: {e}")
            filas_pendientes_log.append(fila)

    # --- Guardar Log ---
    try:
        # 1. Guardar cabecera
        importar_forms.guardar_log_importacion(
            id_import=id_import,
            id_planilla=id_planilla,
            curso_id=curso_id,
            curso_nombre=curso_nombre,
            cuatrimestre=cuatrimestre,
            anio=anio,
            total_form=preview["total"],
            importados=importados,
            pendientes=len(filas_pendientes_log),
            nombre_backup=nombre_backup
        )
        # 2. Guardar pendientes
        importar_forms.guardar_log_pendientes(id_import, filas_pendientes_log)
    except Exception as e:
        flash(f"⚠️ La importación se realizó, pero hubo un error guardando el log: {e}", "warning")

    invalidar("Alumnos")
    session.pop("import_contexto", None)

    return render_template(
        "admin_importar_resultado.html",
        importados=importados,
        salteados=len(filas_pendientes_log),
        errores=[],
        backup_mensaje=backup_mensaje,
        curso_id=curso_id,
        id_import=id_import,  # Pasamos el ID para mostrarlo en la pantalla
        tiene_pendientes=len(filas_pendientes_log) > 0
    )

# -----------------------------------------------------------------------------
#  Log de importaciones
# -----------------------------------------------------------------------------

@admin_importar_bp.route("/log", methods=["GET"])
def log_index():
    """Lista todas las importaciones hechas, con su resumen."""
    try:
        hoja = abrir_hoja("Importaciones")
        registros = hoja.get_all_records()
    except Exception as e:
        flash(f"❌ Error leyendo el log de importaciones: {e}", "danger")
        registros = []

    # Ordenar por fecha/hora descendente (las más nuevas primero)
    importaciones = []
    for r in registros:
        keys = normalizar_claves(r)
        importaciones.append({
            "id_import": keys.get("ID_IMPORT", ""),
            "fecha_hora": keys.get("FECHA_HORA", ""),
            "curso_id": keys.get("CURSO_ID", ""),
            "curso_nombre": keys.get("CURSO_NOMBRE", ""),
            "cuatrimestre": keys.get("CUATRIMESTRE", ""),
            "anio": keys.get("ANIO", ""),
            "total_form": keys.get("TOTAL_FORM", ""),
            "importados": keys.get("IMPORTADOS", ""),
            "pendientes": keys.get("PENDIENTES", ""),
            "estado": keys.get("ESTADO", ""),
            "nombre_backup": keys.get("NOMBRE_BACKUP", ""),
        })

    importaciones.sort(key=lambda x: x["fecha_hora"], reverse=True)

    return render_template("admin_importar_log.html", importaciones=importaciones)


@admin_importar_bp.route("/log/<id_import>", methods=["GET"])
def log_detalle(id_import):
    """Detalle de una importación: los pendientes, con opción de editarlos
    y reintentar la importación."""
    try:
        hoja_cab = abrir_hoja("Importaciones")
        cab_registros = hoja_cab.get_all_records()

        hoja_pend = abrir_hoja("Importaciones_Pendientes")
        pend_registros = hoja_pend.get_all_records()
    except Exception as e:
        flash(f"❌ Error leyendo el log: {e}", "danger")
        return redirect(url_for("admin_importar.log_index"))

    # Buscar la cabecera
    cabecera = None
    for r in cab_registros:
        keys = normalizar_claves(r)
        if keys.get("ID_IMPORT") == id_import:
            cabecera = {
                "id_import": id_import,
                "fecha_hora": keys.get("FECHA_HORA", ""),
                "curso_id": keys.get("CURSO_ID", ""),
                "curso_nombre": keys.get("CURSO_NOMBRE", ""),
                "cuatrimestre": keys.get("CUATRIMESTRE", ""),
                "anio": keys.get("ANIO", ""),
                "total_form": keys.get("TOTAL_FORM", ""),
                "importados": keys.get("IMPORTADOS", ""),
                "pendientes": keys.get("PENDIENTES", ""),
                "estado": keys.get("ESTADO", ""),
            }
            break

    if not cabecera:
        flash(f"❌ No se encontró la importación {id_import}.", "danger")
        return redirect(url_for("admin_importar.log_index"))

    # Filtrar pendientes
    pendientes = []
    for r in pend_registros:
        keys = normalizar_claves(r)
        if keys.get("ID_IMPORT") == id_import:
            pendientes.append({
                "nro_fila": keys.get("NRO_FILA", ""),
                "dni": keys.get("DNI", ""),
                "apellidos": keys.get("APELLIDOS", ""),
                "nombres": keys.get("NOMBRES", ""),
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
                "errores": keys.get("ERRORES", ""),
                "advertencias": keys.get("ADVERTENCIAS", ""),
            })

    return render_template(
        "admin_importar_log_detalle.html",
        cabecera=cabecera,
        pendientes=pendientes,
    )


@admin_importar_bp.route("/log/<id_import>/reintentar", methods=["POST"])
def log_reintentar(id_import):
    """Reintenta importar las filas pendientes de un log.
    Recibe los datos editados desde el formulario del detalle.
    """
    try:
        hoja_cab = abrir_hoja("Importaciones")
        cab_registros = hoja_cab.get_all_records()

        hoja_pend = abrir_hoja("Importaciones_Pendientes")
        pend_registros = hoja_pend.get_all_records()
    except Exception as e:
        flash(f"❌ Error leyendo el log: {e}", "danger")
        return redirect(url_for("admin_importar.log_index"))

    # Buscar la cabecera
    cabecera = None
    for r in cab_registros:
        keys = normalizar_claves(r)
        if keys.get("ID_IMPORT") == id_import:
            cabecera = keys
            break

    if not cabecera:
        flash(f"❌ No se encontró la importación {id_import}.", "danger")
        return redirect(url_for("admin_importar.log_index"))

    curso_id = str(cabecera.get("CURSO_ID", "")).strip()
    cuatrimestre = str(cabecera.get("CUATRIMESTRE", "")).strip()
    anio = str(cabecera.get("ANIO", "")).strip()

    # Filas seleccionadas (checkbox)
    filas_seleccionadas = request.form.getlist("reintentar_filas")
    if not filas_seleccionadas:
        flash("⚠️ No seleccionaste ninguna fila para reintentar.", "warning")
        return redirect(url_for("admin_importar.log_detalle", id_import=id_import))

    # Mapear los pendientes originales por nro_fila
    pendientes_por_fila = {}
    for r in pend_registros:
        keys = normalizar_claves(r)
        if keys.get("ID_IMPORT") == id_import:
            nro = str(keys.get("NRO_FILA", "")).strip()
            pendientes_por_fila[nro] = keys

    # Recolectar los datos editados de cada fila seleccionada
    filas_a_importar = []
    for nro_fila in filas_seleccionadas:
        # Buscar el registro original
        original = pendientes_por_fila.get(nro_fila)
        if not original:
            continue

        # Recolectar los campos del formulario (tienen prefijo "fila_NRO_...")
        prefijo = f"fila_{nro_fila}_"

        def get_form(campo):
            return request.form.get(prefijo + campo, "").strip()

        # Empezamos con los datos ORIGINALES guardados en el log
        # (así no perdemos los campos que no están en el formulario de edición)
        datos = {
            "dni": str(original.get("DNI", "")).strip(),
            "apellidos": str(original.get("APELLIDOS", "")).strip(),
            "nombres": str(original.get("NOMBRES", "")).strip(),
            "fecha_nac": str(original.get("FECHA_NAC", "")).strip(),
            "genero": str(original.get("GENERO", "")).strip(),
            "nacionalidad": str(original.get("NACIONALIDAD", "")).strip(),
            "provincia_nac": str(original.get("PROVINCIA_NAC", "")).strip(),
            "domicilio": str(original.get("DOMICILIO", "")).strip(),
            "barrio": str(original.get("BARRIO", "")).strip(),
            "telefono": str(original.get("TELEFONO", "")).strip(),
            "email": str(original.get("EMAIL", "")).strip(),
            "cuil": str(original.get("CUIL", "")).strip(),
            "estudios": str(original.get("ESTUDIOS", "")).strip(),
            "estado_laboral": str(original.get("ESTADO_LABORAL", "")).strip(),
            "discapacidad": str(original.get("DISCAPACIDAD", "")).strip(),
            "telefono_emergencia": str(original.get("TELEFONO_EMERGENCIA", "")).strip(),
            "fecha_inscripcion": str(original.get("FECHA_INSCRIPCION", "")).strip(),
            "certificacion_valor": "",
        }

        # Sobreescribir SOLO los campos que el admin pudo editar en el formulario
        # (los únicos que el formulario HTML envía)
        dni_form = "".join(c for c in get_form("dni") if c.isdigit())
        if dni_form:
            datos["dni"] = dni_form

        apellidos_form = get_form("apellidos").upper()
        if apellidos_form:
            datos["apellidos"] = apellidos_form

        nombres_form = get_form("nombres").upper()
        if nombres_form:
            datos["nombres"] = nombres_form

        fecha_nac_form = get_form("fecha_nac")
        if fecha_nac_form:
            datos["fecha_nac"] = fecha_nac_form

        cuil_form = "".join(c for c in get_form("cuil") if c.isdigit())
        if cuil_form:
            datos["cuil"] = cuil_form


        # Validar
        alumnos_existentes = _dnies_existentes_en_curso(curso_id)
        # No contar duplicados dentro del Forms (porque ya se corrigió)
        validacion = importar_forms.validar_fila(
            datos, cuatrimestre, anio, alumnos_existentes, {}
        )

        filas_a_importar.append({
            "nro_fila": nro_fila,
            "datos": datos,
            "errores": validacion["errores"],
            "advertencias": validacion["advertencias"],
            "valido": len(validacion["errores"]) == 0,
        })

    # Separar válidos de inválidos
    validos = [f for f in filas_a_importar if f["valido"]]
    invalidos = [f for f in filas_a_importar if not f["valido"]]

    if not validos:
        errores_txt = "\n".join([
            f"Fila {f['nro_fila']}: {' | '.join(f['errores'])}"
            for f in invalidos
        ])
        flash(f"❌ Ninguna fila es válida todavía:\n{errores_txt}", "danger")
        return redirect(url_for("admin_importar.log_detalle", id_import=id_import))

    # Backup antes de escribir
    backup_ok = True
    backup_mensaje = ""
    if current_app.config.get("BACKUP_ACTIVO", True):
        try:
            resultado_backup = backup.hacer_backup(motivo="pre-reintento-importacion")
            if resultado_backup["ok"]:
                backup_mensaje = f"Backup creado: {resultado_backup['nombre_backup']}"
            else:
                backup_ok = False
                backup_mensaje = "Backup falló: " + " | ".join(resultado_backup["errores"])
        except Exception as e:
            backup_ok = False
            backup_mensaje = f"Error haciendo backup: {e}"

    if not backup_ok:
        flash(f"❌ No se pudo hacer el backup automático. No se importó nada. {backup_mensaje}", "danger")
        return redirect(url_for("admin_importar.log_detalle", id_import=id_import))

    # Escribir en Alumnos
    hoja_alumnos = abrir_hoja("Alumnos")
    importados = 0
    errores_escritura = []

    for f in validos:
        d = f["datos"]
        try:
            hoja_alumnos.append_row([
                d["dni"], d["apellidos"], d["nombres"], curso_id, cuatrimestre, anio, "A",
                d["fecha_nac"], d["genero"], d["nacionalidad"], d["provincia_nac"],
                d["domicilio"], d["barrio"], d["telefono"], d["email"], d["cuil"],
                d["estudios"], d["estado_laboral"], d["discapacidad"],
                d["telefono_emergencia"], d["fecha_inscripcion"], "IMPORT", "",
            ])
            importados += 1
        except Exception as e:
            errores_escritura.append(f"Fila {f['nro_fila']}: {e}")

    # Actualizar el estado de los pendientes (marcar los importados como resueltos)
    # Estrategia simple: borrar de la hoja los que se importaron.
    # Requiere encontrar el índice de cada fila. Lo hacemos de abajo hacia arriba
    # para no descolocar índices.
    try:
        valores_pend = hoja_pend.get_all_values()
        indices_a_borrar = []
        for i, fila_vals in enumerate(valores_pend[1:], start=2):  # fila 2 en adelante
            # Columnas: A=ID_IMPORT, B=NRO_FILA
            if len(fila_vals) >= 2:
                id_imp_celda = str(fila_vals[0]).strip()
                nro_fila_celda = str(fila_vals[1]).strip()
                if id_imp_celda == id_import and nro_fila_celda in [f["nro_fila"] for f in validos]:
                    indices_a_borrar.append(i)

        # Borrar de abajo hacia arriba
        for i in sorted(indices_a_borrar, reverse=True):
            hoja_pend.delete_rows(i)
    except Exception as e:
        print(f"⚠️ Error actualizando pendientes en el log: {e}")

    # Actualizar la cabecera: restar los importados de los pendientes
    try:
        valores_cab = hoja_cab.get_all_values()
        for i, fila_vals in enumerate(valores_cab[1:], start=2):
            if len(fila_vals) >= 1 and str(fila_vals[0]).strip() == id_import:
                # Columnas: J = PENDIENTES, I = IMPORTADOS
                try:
                    pendientes_prev = int(str(fila_vals[9]).strip() or "0")
                    importados_prev = int(str(fila_vals[8]).strip() or "0")
                    nuevos_pendientes = max(0, pendientes_prev - importados)
                    nuevos_importados = importados_prev + importados
                    hoja_cab.update_cell(i, 9, nuevos_importados)   # columna I
                    hoja_cab.update_cell(i, 10, nuevos_pendientes)  # columna J
                    # Si ya no hay pendientes, cambiar estado
                    if nuevos_pendientes == 0:
                        hoja_cab.update_cell(i, 12, "COMPLETADO")   # columna L
                except (ValueError, IndexError):
                    pass
                break
    except Exception as e:
        print(f"⚠️ Error actualizando cabecera del log: {e}")

    invalidar("Alumnos")

    mensaje = f"✅ Reimportación completada. {importados} alumnos importados."
    if errores_escritura:
        mensaje += f" ({len(errores_escritura)} fallaron)"
    if invalidos:
        mensaje += f" {len(invalidos)} filas siguen con errores y quedaron pendientes."
    flash(mensaje, "success" if not errores_escritura else "warning")

    return redirect(url_for("admin_importar.log_detalle", id_import=id_import))

@admin_importar_bp.route("/log/<id_import>/descartar/<nro_fila>", methods=["POST"])
def log_descartar_fila(id_import, nro_fila):
    """Descarta (borra) UNA fila pendiente específica, sin importarla."""
    try:
        hoja_cab = abrir_hoja("Importaciones")
        hoja_pend = abrir_hoja("Importaciones_Pendientes")
    except Exception as e:
        flash(f"❌ Error accediendo al log: {e}", "danger")
        return redirect(url_for("admin_importar.log_index"))

    # Borrar la fila específica de Importaciones_Pendientes
    borrada = False
    try:
        valores_pend = hoja_pend.get_all_values()
        for i, fila_vals in enumerate(valores_pend[1:], start=2):
            if len(fila_vals) >= 2:
                id_imp_celda = str(fila_vals[0]).strip()
                nro_fila_celda = str(fila_vals[1]).strip()
                if id_imp_celda == id_import and nro_fila_celda == str(nro_fila).strip():
                    hoja_pend.delete_rows(i)
                    borrada = True
                    break
    except Exception as e:
        flash(f"❌ Error borrando pendiente: {e}", "danger")
        return redirect(url_for("admin_importar.log_detalle", id_import=id_import))

    if not borrada:
        flash(f"⚠️ No se encontró la fila {nro_fila} en el log.", "warning")
        return redirect(url_for("admin_importar.log_detalle", id_import=id_import))

    # Actualizar la cabecera (restar 1 de PENDIENTES)
    try:
        valores_cab = hoja_cab.get_all_values()
        for i, fila_vals in enumerate(valores_cab[1:], start=2):
            if len(fila_vals) >= 1 and str(fila_vals[0]).strip() == id_import:
                try:
                    pendientes_prev = int(str(fila_vals[9]).strip() or "0")
                    nuevos_pendientes = max(0, pendientes_prev - 1)
                    hoja_cab.update_cell(i, 10, nuevos_pendientes)  # columna J
                    if nuevos_pendientes == 0:
                        hoja_cab.update_cell(i, 12, "COMPLETADO")  # columna L
                except (ValueError, IndexError):
                    pass
                break
    except Exception as e:
        print(f"⚠️ Error actualizando cabecera: {e}")

    flash(f"🗑️ Fila {nro_fila} descartada.", "success")
    return redirect(url_for("admin_importar.log_detalle", id_import=id_import))

@admin_importar_bp.route("/log/<id_import>/imprimir", methods=["GET"])
def log_imprimir(id_import):
    """Pantalla imprimible con los pendientes de una importación."""
    try:
        hoja_cab = abrir_hoja("Importaciones")
        cab_registros = hoja_cab.get_all_records()

        hoja_pend = abrir_hoja("Importaciones_Pendientes")
        pend_registros = hoja_pend.get_all_records()
    except Exception as e:
        flash(f"❌ Error leyendo el log: {e}", "danger")
        return redirect(url_for("admin_importar.log_index"))

    # Buscar la cabecera
    cabecera = None
    for r in cab_registros:
        keys = normalizar_claves(r)
        if keys.get("ID_IMPORT") == id_import:
            cabecera = {
                "id_import": id_import,
                "fecha_hora": keys.get("FECHA_HORA", ""),
                "curso_nombre": keys.get("CURSO_NOMBRE", ""),
                "cuatrimestre": keys.get("CUATRIMESTRE", ""),
                "anio": keys.get("ANIO", ""),
            }
            break

    if not cabecera:
        flash(f"❌ No se encontró la importación {id_import}.", "danger")
        return redirect(url_for("admin_importar.log_index"))

    # Filtrar pendientes
    pendientes = []
    for r in pend_registros:
        keys = normalizar_claves(r)
        if keys.get("ID_IMPORT") == id_import:
            pendientes.append({
                "nro_fila": keys.get("NRO_FILA", ""),
                "dni": keys.get("DNI", ""),
                "apellidos": keys.get("APELLIDOS", ""),
                "nombres": keys.get("NOMBRES", ""),
                "fecha_nac": keys.get("FECHA_NAC", ""),
                "telefono": keys.get("TELEFONO", ""),
                "telefono_emergencia": keys.get("TELEFONO_EMERGENCIA", ""),  # ← nuevo
                "email": keys.get("EMAIL", ""),
                "domicilio": keys.get("DOMICILIO", ""),
                "errores": keys.get("ERRORES", ""),
                "advertencias": keys.get("ADVERTENCIAS", ""),  # ← nuevo
            })

    return render_template(
        "admin_importar_imprimir.html",
        cabecera=cabecera,
        pendientes=pendientes,
    )