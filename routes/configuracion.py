# routes/configuracion.py
"""
Pantalla de configuración / mantenimiento.

Muestra:
  - Info de la app (nombre, versión, entorno, ID de la planilla).
  - Estado del caché: qué hojas están cacheadas, cuándo, si están vencidas.
  - Botones para forzar el refresco (todo o por hoja) y para borrar el caché.
  - Backups: botón para hacer uno ahora, tabla con los últimos.

No requiere login (decisión de diseño: estas acciones no rompen nada).
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from services import cache_sheets
from services import backup

configuracion_bp = Blueprint("configuracion", __name__, url_prefix="/configuracion")


@configuracion_bp.route("/")
def index():
    estado_cache = cache_sheets.estado()

    info_app = {
        "nombre": current_app.config.get("APP_NOMBRE", "?"),
        "version": current_app.config.get("APP_VERSION", "?"),
        "entorno": current_app.config.get("ENTORNO", "?"),
        "spreadsheet_id": current_app.config.get("SPREADSHEET_ID", "?"),
        "spreadsheet_nombre": current_app.config.get("SPREADSHEET_NOMBRE", "?"),
    }

    info_backup = {
        "activo": current_app.config.get("BACKUP_ACTIVO", False),
        "en_drive": current_app.config.get("BACKUP_EN_DRIVE", False),
        "en_local": current_app.config.get("BACKUP_EN_LOCAL", False),
        "retencion": current_app.config.get("BACKUP_RETENCION", 30),
        "carpeta_local": current_app.config.get("BACKUP_CARPETA_LOCAL", "?"),
    }

    lista_backups = backup.listar_backups(limite=15)

    return render_template(
        "configuracion.html",
        info_app=info_app,
        info_backup=info_backup,
        estado_cache=estado_cache,
        backups=lista_backups,
    )


# -----------------------------------------------------------------------------
#  Caché
# -----------------------------------------------------------------------------

@configuracion_bp.route("/cache/refrescar", methods=["POST"])
def refrescar_todo():
    """Fuerza la recarga de TODAS las hojas la próxima vez que se lean."""
    cache_sheets.invalidar_todo()
    flash("✅ Caché invalidado por completo. La próxima lectura va a traer datos frescos.", "success")
    return redirect(url_for("configuracion.index"))


@configuracion_bp.route("/cache/refrescar/<hoja>", methods=["POST"])
def refrescar_hoja(hoja):
    """Fuerza la recarga de UNA hoja puntual."""
    cache_sheets.invalidar(hoja)
    flash(f"✅ Caché de '{hoja}' invalidado. La próxima lectura va a traer datos frescos.", "success")
    return redirect(url_for("configuracion.index"))


@configuracion_bp.route("/cache/leer/<hoja>", methods=["POST"])
def leer_ahora(hoja):
    """Fuerza la lectura inmediata de una hoja (la cachea en el momento)."""
    try:
        from services.sheets import get_records_cacheado
        registros = get_records_cacheado(hoja, forzar_refresco=True)
        flash(f"✅ '{hoja}' leída y cacheada ({len(registros)} registros).", "success")
    except Exception as e:
        flash(f"❌ Error leyendo '{hoja}': {e}", "danger")
    return redirect(url_for("configuracion.index"))


@configuracion_bp.route("/cache/borrar", methods=["POST"])
def borrar_cache():
    """Borra el archivo de caché del disco."""
    cache_sheets.borrar_cache()
    flash("✅ Archivo de caché borrado. Se va a regenerar en la próxima lectura.", "success")
    return redirect(url_for("configuracion.index"))


# -----------------------------------------------------------------------------
#  Backups
# -----------------------------------------------------------------------------

@configuracion_bp.route("/backup/hacer", methods=["POST"])
def hacer_backup_ahora():
    """Hace un backup manual de la planilla activa."""
    try:
        resultado = backup.hacer_backup(motivo="manual")
        if resultado["ok"]:
            detalles = []
            if resultado["local_path"]:
                detalles.append(f"local: {resultado['local_path']}")
            if resultado["drive_link"]:
                detalles.append(f"drive: {resultado['drive_link']}")
            detalle = " · ".join(detalles) if detalles else "(sin ubicaciones)"
            flash(f"✅ Backup completado. {detalle}", "success")
        else:
            errores = " | ".join(resultado["errores"]) or "sin detalle"
            flash(f"❌ El backup falló: {errores}", "danger")
    except Exception as e:
        flash(f"❌ Error inesperado haciendo backup: {e}", "danger")

    return redirect(url_for("configuracion.index"))


@configuracion_bp.route("/backup/borrar/<nombre>", methods=["POST"])
def borrar_backup(nombre):
    """Borra un backup puntual (local y/o Drive)."""
    try:
        resultado = backup.borrar_backup(nombre)
        detalles = []
        if resultado["borrado_local"]:
            detalles.append("local")
        if resultado["borrado_drive"]:
            detalles.append("drive")
        if detalles:
            flash(f"🗑️ Backup '{nombre}' borrado ({', '.join(detalles)}).", "success")
        else:
            flash(f"⚠️ No se encontró el backup '{nombre}'.", "warning")
    except Exception as e:
        flash(f"❌ Error borrando backup: {e}", "danger")

    return redirect(url_for("configuracion.index"))