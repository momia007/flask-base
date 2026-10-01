# routes/configuracion.py
"""
Pantalla de configuración / mantenimiento.

Muestra:
  - Info de la app (nombre, versión, ID de la planilla).
  - Estado del caché: qué hojas están cacheadas, cuándo, si están vencidas.
  - Botones para forzar el refresco (todo o por hoja) y para borrar el caché.

No requiere login (decisión de diseño: refrescar el caché no rompe nada).
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from services import cache_sheets

configuracion_bp = Blueprint("configuracion", __name__, url_prefix="/configuracion")


@configuracion_bp.route("/")
def index():
    estado_cache = cache_sheets.estado()

    info_app = {
        "nombre": current_app.config.get("APP_NOMBRE", "?"),
        "version": current_app.config.get("APP_VERSION", "?"),
        "spreadsheet_id": current_app.config.get("SPREADSHEET_ID", "?"),
        "spreadsheet_nombre": current_app.config.get("SPREADSHEET_NOMBRE", "?"),
    }

    return render_template("configuracion.html",
                           info_app=info_app,
                           estado_cache=estado_cache)


@configuracion_bp.route("/cache/refrescar", methods=["POST"])
def refrescar_todo():
    """Fuerza la recarga de TODAS las hojas la próxima vez que se lean."""
    cache_sheets.invalidar_todo()
    flash("✅ Caché invalidado por completo. La próxima lectura va a traer datos frescos de Google Sheets.", "success")
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
def borrar():
    """Borra el archivo de caché del disco (por si se corrompe o querés
    empezar de cero)."""
    cache_sheets.borrar_cache()
    flash("✅ Archivo de caché borrado. Se va a regenerar en la próxima lectura.", "success")
    return redirect(url_for("configuracion.index"))