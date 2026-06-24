# Asistencia Escolar - Flask App

Aplicación web en **Flask** para gestionar asistencia escolar.  
Incluye interfaz responsive (Bootstrap), configuración con variables de entorno y futura integración con Google Sheets.

---

## 🚀 Requisitos

- Python 3.10+
- Entorno virtual (`venv`)
- Librerías:
  - Flask
  - gspread
  - oauth2client
  - python-dotenv

---

## ⚙️ Instalación

1. Clonar el repositorio:
   ```bash
   git clone https://github.com/usuario/asist.git
   cd asist

2. Crear y activar entorno virtual:
    python -m venv venv
    # Windows
    venv\Scripts\activate
    # Linux/Mac
    source venv/bin/activate

3.  Instalar dependencias:
    pip install -r requirements.txt

4. Estructura del proyecto
    Asist/
    ├── app.py
    ├── config.py
    ├── requirements.txt
    ├── .env.example
    ├── templates/
    │   ├── index.html
    │   └── asistencia.html
    └── static/
        └── css/
            └── style.css
