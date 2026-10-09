# services/cache_sheets.py
"""
Caché simple en disco para las lecturas de Google Sheets.

Guarda en instance/cache_sheets.json los registros de cada hoja junto con
la marca de tiempo de cuándo se guardaron. Cuando un módulo pide los
registros de una hoja:

  - Si el caché existe y todavía no venció (según el TTL configurado en
    config.py), devuelve los datos guardados SIN consultar a Google.
  - Si venció o no existe, consulta a Google, guarda el resultado y lo
    devuelve.

La idea es no pasarse del límite de lecturas que impone Google (60 por
minuto) y hacer la app más rápida.

Para forzar una recarga sin esperar al TTL, usar:
    - invalidar("Cursos")          → marca una hoja como vencida
    - invalidar_todo()             → marca todo como vencido
    - borrar_cache()               → borra el archivo entero

O desde la pantalla /configuracion.
"""

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

from services.sheets import abrir_hoja


# --- Ubicación del archivo de caché ---
# Lo guardamos en instance/ (carpeta estándar de Flask). Si no existe, la creamos.
_RUTA_BASE = Path(__file__).resolve().parent.parent  # raíz del proyecto
_RUTA_INSTANCE = _RUTA_BASE / "instance"
_RUTA_CACHE = _RUTA_INSTANCE / "cache_sheets.json"

# Un lock para que dos requests simultáneos no se pisen escribiendo el archivo.
_lock = threading.Lock()


# --- TTLs por hoja (segundos) ---
# Estos valores se pueden sobreescribir desde config.py. Acá dejamos los
# mismos que en config.py por si este módulo se usa sin Flask (por ejemplo
# desde un script suelto). Cuando corre dentro de la app, se leen de app.config.
TTL_POR_DEFECTO = {
    "Cursos": 24 * 60 * 60,
    "Feriados": 24 * 60 * 60,
    "Alumnos": 6 * 60 * 60,
    "Ausencias_Profesores": 2 * 60 * 60,
    "Asistencias": 30,
}


def _ttl_de(hoja):
    """Devuelve el TTL configurado para esa hoja. Primero mira app.config
    (si Flask está corriendo), después config.py, y si no, usa el valor por
    defecto de TTL_POR_DEFECTO."""
    # app.config tiene prioridad (permite override desde .env)
    try:
        from flask import current_app
        if current_app:
            clave = f"TTL_{hoja.upper().replace('_', '')}"
            # Ajuste para nombres con guión bajo: Ausencias_Profesores -> TTL_AUSENCIASPROFESORES
            # Pero en config.py usamos TTL_AUSENCIAS a secas. Mapeamos:
            mapa = {
                "Cursos": "TTL_CURSOS",
                "Feriados": "TTL_FERIADOS",
                "Alumnos": "TTL_ALUMNOS",
                "Ausencias_Profesores": "TTL_AUSENCIAS",
                "Asistencias": "TTL_ASISTENCIAS",
            }
            clave = mapa.get(hoja, clave)
            if clave in current_app.config:
                return current_app.config[clave]
    except Exception:
        pass
    return TTL_POR_DEFECTO.get(hoja, 60)


# --- Lectura y escritura del archivo de caché ---

def _cargar_archivo():
    """Lee el JSON del disco. Si no existe o está corrupto, devuelve {}."""
    if not _RUTA_CACHE.exists():
        return {}
    try:
        with open(_RUTA_CACHE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"⚠️ Caché corrupto, se ignora: {e}")
        return {}


def _guardar_archivo(datos):
    """Escribe el JSON al disco. Crea instance/ si no existe."""
    _RUTA_INSTANCE.mkdir(parents=True, exist_ok=True)
    with _lock:
        with open(_RUTA_CACHE, "w", encoding="utf-8") as f:
            json.dump(datos, f, ensure_ascii=False, indent=2)


# --- API pública ---

def get_records(hoja, forzar_refresco=False):
    """Devuelve los registros de una hoja, usando el caché si está fresco.

    Parámetros:
      - hoja: nombre de la pestaña en Google Sheets (ej: "Cursos").
      - forzar_refresco: si es True, ignora el caché y va a Google.

    Devuelve una lista de diccionarios (igual que worksheet.get_all_records()).
    """
    datos = _cargar_archivo()
    entrada = datos.get(hoja)

    if not forzar_refresco and entrada:
        guardado_en = entrada.get("guardado_en", 0)
        ttl = _ttl_de(hoja)
        ahora = datetime.now(timezone.utc).timestamp()
        if ahora - guardado_en < ttl:
            print(f"📦 Caché: usando '{hoja}' (edad: {int(ahora - guardado_en)}s, ttl: {ttl}s)")
            return entrada.get("registros", [])

    # Caché vencido o forzado: ir a Google
    print(f"🌐 Caché: refrescando '{hoja}' desde Google Sheets...")
    worksheet = abrir_hoja(hoja)
    registros = worksheet.get_all_records()

    datos[hoja] = {
        "guardado_en": datetime.now(timezone.utc).timestamp(),
        "guardado_legible": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "registros": registros,
    }
    _guardar_archivo(datos)
    return registros


def invalidar(hoja):
    """Marca una hoja como vencida (la próxima lectura va a Google)."""
    datos = _cargar_archivo()
    if hoja in datos:
        del datos[hoja]
        _guardar_archivo(datos)
        print(f"🗑️ Caché invalidado: {hoja}")


def invalidar_todo():
    """Marca todas las hojas como vencidas."""
    _guardar_archivo({})
    print("🗑️ Caché invalidado por completo")


def borrar_cache():
    """Borra el archivo de caché del disco."""
    if _RUTA_CACHE.exists():
        _RUTA_CACHE.unlink()
        print("🗑️ Archivo de caché borrado")


def estado():
    """Devuelve un resumen del caché para mostrarlo en /configuracion.
    Lista cada hoja cacheada con: cuándo se guardó, cuántos registros tiene
    y si todavía está fresca o vencida."""
    datos = _cargar_archivo()
    ahora = datetime.now(timezone.utc).timestamp()
    resultado = []

    # Mostramos todas las hojas conocidas, incluso las que todavía no se cachearon
    hojas_conocidas = ["Cursos", "Feriados", "Alumnos", "Ausencias_Profesores", "Asistencias"]

    for hoja in hojas_conocidas:
        entrada = datos.get(hoja)
        ttl = _ttl_de(hoja)
        if entrada:
            guardado_en = entrada.get("guardado_en", 0)
            edad = int(ahora - guardado_en)
            vencido = edad >= ttl
            resultado.append({
                "hoja": hoja,
                "cacheada": True,
                "guardado_legible": entrada.get("guardado_legible", "?"),
                "edad_segundos": edad,
                "ttl_segundos": ttl,
                "vencida": vencido,
                "cantidad_registros": len(entrada.get("registros", [])),
            })
        else:
            resultado.append({
                "hoja": hoja,
                "cacheada": False,
                "guardado_legible": None,
                "edad_segundos": None,
                "ttl_segundos": ttl,
                "vencida": True,
                "cantidad_registros": 0,
            })

    return {
        "ruta_archivo": str(_RUTA_CACHE),
        "existe_archivo": _RUTA_CACHE.exists(),
        "hojas": resultado,
    }