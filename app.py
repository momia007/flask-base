from flask import Flask, render_template, request, redirect, url_for
from config import Config

app = Flask(__name__)
app.config.from_object(Config)

# Ruta principal: muestra la página de inicio
@app.route("/")
def index():
    return render_template("index.html")

# Ruta de asistencia: formulario simple
@app.route("/asistencia", methods=["GET", "POST"])
def asistencia():
    if request.method == "POST":
        alumno = request.form.get("alumno")
        estado = request.form.get("estado")
        # Aquí luego se integrará la lógica para guardar en Google Sheets
        print(f"Asistencia registrada: {alumno} - {estado}")
        return redirect(url_for("index"))
    return render_template("asistencia.html")

if __name__ == "__main__":
    app.run(debug=True)
