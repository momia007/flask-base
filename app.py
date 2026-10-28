# app.py

from flask import Flask, render_template
from config import Config

# Inicialización de la app
app = Flask(__name__)
app.config.from_object(Config)
app.config["TEMPLATES_AUTO_RELOAD"] = True


# --- Context processor: variables disponibles en TODOS los templates ---
# Así cualquier HTML que herede de layout.html puede usar {{ app_version }},
# {{ app_nombre }}, etc. sin que cada ruta tenga que pasarlas.
@app.context_processor
def inyectar_variables_globales():
    return {
        "app_version": app.config["APP_VERSION"],
        "app_nombre": app.config["APP_NOMBRE"],
    }


# Importar y registrar Blueprints
from routes.asistencia import asistencia_bp
from routes.turnos import turnos_bp
from routes.dias_especiales import dias_especiales_bp
from routes.visualizacion_asistencias import visualizacion_bp
from routes.altas_bajas_modificaciones_alumnos import alumnos_bp
from routes.configuracion import configuracion_bp
from routes.admin_alumnos import admin_alumnos_bp
from routes.admin_importar import admin_importar_bp

app.register_blueprint(alumnos_bp)
app.register_blueprint(dias_especiales_bp)
app.register_blueprint(asistencia_bp)
app.register_blueprint(turnos_bp)
app.register_blueprint(visualizacion_bp)
app.register_blueprint(configuracion_bp)
app.register_blueprint(admin_alumnos_bp)
app.register_blueprint(admin_importar_bp)

# Ruta principal
@app.route("/")
def index():
    return render_template("index.html")


if __name__ == "__main__":
    from waitress import serve
    serve(app, host="0.0.0.0", port=app.config["PUERTO"])