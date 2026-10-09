# Proyecto Flask Base

Plantilla mínima para iniciar proyectos con **Flask**.  
Incluye estructura de carpetas, configuración con variables de entorno y documentación inicial.

---

## 🚀 Requisitos

- Python 3.10+
- Entorno virtual (`venv`)
- Librerías:
  - Flask
  - python-dotenv

---

## ⚙️ Instalación

1. Clonar el repositorio:
    ```bash
    git clone https://github.com/usuario/    proyecto-flask-base.git
    cd proyecto-flask-base


2.  Crear y activar entorno virtual:
    python -m venv venv
    # Windows
    venv\Scripts\activate
    # Linux/Mac
    source venv/bin/activate


3.  Instalar dependencias:
    bash
    pip install -r requirements.txt


##  📂 Estructura del proyecto

ProyectoBase/
├── app.py
├── config.py
├── requirements.txt
├── .env.example
├── README.md
│
├── templates/
│   ├── base.html
│   └── index.html
│
└── static/
    ├── css/
    │   └── style.css
    └── js/
        └── script.js

##  🔑 Configuración

1.  Copiar .env.example a .env:

    cp .env.example .env

2.  Completar las claves reales:

    SECRET_KEY=clave_secreta


##  ▶️ Ejecución

1.  Activar entorno virtual.

2.  Ejecutar la aplicación:

    set FLASK_DEBUG=1 "para ver logs en consola exploto la variable de entorno"
    flask run  (solo en la pc y en local)
    flask run --host=0.0.0.0  (accesible desde lan si se pone la ip del serv. ej:  http://192.168.0.10:5000)
    
3.  Abrir en navegador:

    Inicio: http://127.0.0.1:5000/

    ## para pruebas
    set FLASK_DEBUG=1
    flask run --host=0.0.0.0 --port=5001


##  📌 Próximos pasos

Agregar rutas y vistas según el proyecto.

Extender config.py con más variables de entorno.

Incorporar librerías adicionales en requirements.txt.