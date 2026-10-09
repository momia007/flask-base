# services/backup.py
"""
Sistema de backups de la planilla de Google Sheets.

Hace dos tipos de copia:
  1. Copia NATIVA en Drive (una planilla de Google Sheets idéntica).
     Sirve para restaurar con un clic.
  2. Copia en CSV LOCAL (una carpeta con un CSV por pestaña).
     Sirve como respaldo de emergencia si Drive falla.

Además copia los archivos históricos (los que se van sacando de la
planilla activa) solo si son nuevos, sin sobreescribir.

Los backups viejos se rotan automáticamente (se borran los más antiguos
al superar BACKUP_RETENCION).
"""

import csv
import json
import os
import shutil
from datetime import datetime
from pathlib import Path

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from services.sheets import client, creds_publicas
from services.cache_sheets import invalidar_todo


# -----------------------------------------------------------------------------
#  Utilidades internas
# -----------------------------------------------------------------------------

def _drive_service():
    """Devuelve un cliente autenticado de la API de Google Drive,
    reutilizando las credenciales de gspread."""
    return build("drive", "v3", credentials=creds_publicas)


def _nombre_backup():
    """Genera el nombre base de un backup con fecha y hora."""
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")


def _raiz_proyecto():
    """Devuelve la ruta absoluta de la raíz del proyecto."""
    return Path(__file__).resolve().parent.parent


def _entorno_actual():
    """Devuelve el entorno activo ('produccion' o 'desarrollo')."""
    try:
        from flask import current_app
        return current_app.config.get("ENTORNO", "produccion")
    except Exception:
        # Fuera de un request (por ejemplo, desde un script), leemos de config.
        from config import ENTORNO
        return ENTORNO


def _config(clave, por_defecto=None):
    """Lee una variable de configuración, con fallback a config.py."""
    try:
        from flask import current_app
        if current_app:
            return current_app.config.get(clave, por_defecto)
    except Exception:
        pass
    import config
    return getattr(config, clave, por_defecto)


# -----------------------------------------------------------------------------
#  Backup en Drive (copia nativa de Google Sheets)
# -----------------------------------------------------------------------------

def _backup_drive(spreadsheet_id, nombre_backup, entorno):
    """
    Hace una copia nativa de la planilla en la carpeta de Drive configurada.

    Devuelve el ID del archivo copiado, o None si no se pudo.
    """
    carpeta_raiz_id = _config("BACKUP_DRIVE_CARPETA_ID")
    if not carpeta_raiz_id:
        raise RuntimeError("Falta BACKUP_DRIVE_CARPETA_ID en config.py")

    drive = _drive_service()

    # 1. Verificar/crear la subcarpeta del entorno ("produccion" / "desarrollo")
    nombre_carpeta_entorno = entorno
    carpeta_entorno_id = _buscar_o_crear_carpeta(
        drive, nombre_carpeta_entorno, carpeta_raiz_id
    )

    # 2. Copiar la planilla a esa carpeta
    nombre_archivo = f"backup_{nombre_backup}"

    cuerpo = {
        "name": nombre_archivo,
        "parents": [carpeta_entorno_id],
    }

    try:
        copia = drive.files().copy(
            fileId=spreadsheet_id,
            body=cuerpo,
            fields="id, name, webViewLink",
        ).execute()
    except HttpError as e:
        raise RuntimeError(
            f"❌ Drive rechazó la copia: {e}\n\n"
            f"Verificá que:\n"
            f"  1. La cuenta de servicio tenga acceso de Editor a la carpeta "
            f"de backups (ID: {carpeta_raiz_id}).\n"
            f"  2. La planilla activa siga existiendo (ID: {spreadsheet_id}).\n"
            f"  3. Haya espacio disponible en el Drive."
        ) from e

    return copia["id"], copia["name"], copia.get("webViewLink", "")


def _buscar_o_crear_carpeta(drive, nombre, padre_id):
    """Busca una carpeta por nombre dentro de un padre. Si no existe, la crea."""
    consulta = (
        f"name = '{nombre}' and "
        f"'{padre_id}' in parents and "
        f"mimeType = 'application/vnd.google-apps.folder' and "
        f"trashed = false"
    )
    resultado = drive.files().list(
        q=consulta, fields="files(id, name)", pageSize=1
    ).execute()

    archivos = resultado.get("files", [])
    if archivos:
        return archivos[0]["id"]

    # No existe → crear
    metadata = {
        "name": nombre,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [padre_id],
    }
    nueva = drive.files().create(body=metadata, fields="id").execute()
    return nueva["id"]


def _borrar_backups_viejos_drive(drive, carpeta_id, retencion):
    """Borra los backups más viejos de una carpeta de Drive para no superar
    el número de retención."""
    consulta = (
        f"'{carpeta_id}' in parents and "
        f"trashed = false and "
        f"mimeType != 'application/vnd.google-apps.folder'"
    )
    resultado = drive.files().list(
        q=consulta,
        fields="files(id, name, createdTime)",
        orderBy="createdTime desc",
        pageSize=1000,
    ).execute()

    archivos = resultado.get("files", [])
    if len(archivos) <= retencion:
        return 0

    # Los que sobran (los más viejos)
    sobrantes = archivos[retencion:]
    for f in sobrantes:
        drive.files().delete(fileId=f["id"]).execute()

    return len(sobrantes)


# -----------------------------------------------------------------------------
#  Backup local (CSV por pestaña)
# -----------------------------------------------------------------------------

def _backup_local(nombre_backup, entorno):
    """
    Exporta todas las pestañas de la planilla activa como CSV en una
    carpeta local.

    Estructura:
      instance/backups/<entorno>/<nombre_backup>/
        Cursos.csv
        Alumnos.csv
        Asistencias.csv
        ...
        metadata.json

    Devuelve la ruta absoluta de la carpeta creada.
    """
    from services.sheets import SPREADSHEET_ID  # del config, no de sheets

    carpeta_base = _raiz_proyecto() / _config("BACKUP_CARPETA_LOCAL")
    carpeta_backup = carpeta_base / entorno / nombre_backup
    carpeta_backup.mkdir(parents=True, exist_ok=True)

    # Obtener todas las pestañas de la planilla
    planilla = client.open_by_key(SPREADSHEET_ID)
    hojas = planilla.worksheets()

    for hoja in hojas:
        nombre_hoja = hoja.title
        # Nombres seguros para el sistema de archivos
        nombre_archivo = _nombre_archivo_seguro(nombre_hoja) + ".csv"
        ruta_csv = carpeta_backup / nombre_archivo

        valores = hoja.get_all_values()
        with open(ruta_csv, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerows(valores)

    return carpeta_backup


def _nombre_archivo_seguro(nombre):
    """Convierte un nombre de pestaña en un nombre de archivo válido en
    Windows (sin caracteres prohibidos)."""
    prohibidos = '<>:"/\\|?*'
    for c in prohibidos:
        nombre = nombre.replace(c, "_")
    return nombre.strip()


def _borrar_backups_viejos_local(entorno, retencion):
    """Borra las carpetas de backup más viejas en disco."""
    carpeta_base = _raiz_proyecto() / _config("BACKUP_CARPETA_LOCAL") / entorno
    if not carpeta_base.exists():
        return 0

    carpetas = sorted(
        [d for d in carpeta_base.iterdir() if d.is_dir()],
        key=lambda d: d.name,
        reverse=True,
    )
    if len(carpetas) <= retencion:
        return 0

    sobrantes = carpetas[retencion:]
    for d in sobrantes:
        shutil.rmtree(d)

    return len(sobrantes)


# -----------------------------------------------------------------------------
#  Archivos históricos (backup incremental)
# -----------------------------------------------------------------------------

def _backup_historicos():
    """
    Copia los archivos históricos que estén en
    sistema_asistencia/base_datos/archivos_historicos/ hacia la carpeta de
    backups en Drive y local, sin sobreescribir.

    Solo copia archivos nuevos.
    """
    # Por ahora devolvemos 0 porque todavía no hay archivos históricos.
    # Cuando empecemos a generar históricos, se implementa esta función.
    # La idea es: comparar origen vs destino, y copiar solo lo que falte.
    return 0


# -----------------------------------------------------------------------------
#  API pública
# -----------------------------------------------------------------------------

def hacer_backup(motivo="manual"):
    """
    Hace un backup completo de la planilla activa.

    Retorna un diccionario:
      {
        "ok": True/False,
        "motivo": "manual",
        "entorno": "produccion",
        "nombre_backup": "2026-10-07_19-30-45",
        "drive_id": "abc123..." o None,
        "drive_link": "https://..." o "",
        "local_path": "instance/backups/produccion/2026-10-07_19-30-45" o None,
        "errores": ["lista de errores, si hubo"],
        "borrados_drive": 2,
        "borrados_local": 3,
      }
    """
    resultado = {
        "ok": False,
        "motivo": motivo,
        "entorno": _entorno_actual(),
        "nombre_backup": None,
        "drive_id": None,
        "drive_link": "",
        "local_path": None,
        "errores": [],
        "borrados_drive": 0,
        "borrados_local": 0,
    }

    if not _config("BACKUP_ACTIVO", True):
        resultado["errores"].append("Los backups están desactivados (BACKUP_ACTIVO=False).")
        return resultado

    nombre_backup = _nombre_backup()
    entorno = resultado["entorno"]
    resultado["nombre_backup"] = nombre_backup

    from config import SPREADSHEET_ID

    # --- Backup en Drive ---
    if _config("BACKUP_EN_DRIVE", True):
        try:
            drive_id, drive_nombre, drive_link = _backup_drive(
                SPREADSHEET_ID, nombre_backup, entorno
            )
            resultado["drive_id"] = drive_id
            resultado["drive_link"] = drive_link

            # Rotación en Drive
            carpeta_raiz = _config("BACKUP_DRIVE_CARPETA_ID")
            drive = _drive_service()
            carpeta_entorno_id = _buscar_o_crear_carpeta(drive, entorno, carpeta_raiz)
            retencion = _config("BACKUP_RETENCION", 30)
            resultado["borrados_drive"] = _borrar_backups_viejos_drive(
                drive, carpeta_entorno_id, retencion
            )
        except Exception as e:
            resultado["errores"].append(f"Backup en Drive: {e}")

    # --- Backup local ---
    if _config("BACKUP_EN_LOCAL", True):
        try:
            ruta = _backup_local(nombre_backup, entorno)
            resultado["local_path"] = str(ruta.relative_to(_raiz_proyecto()))
            resultado["borrados_local"] = _borrar_backups_viejos_local(
                entorno, _config("BACKUP_RETENCION", 30)
            )
        except Exception as e:
            resultado["errores"].append(f"Backup local: {e}")

    # --- Metadata ---
    resultado["ok"] = len(resultado["errores"]) == 0

    try:
        _guardar_metadata(resultado)
    except Exception as e:
        resultado["errores"].append(f"Guardando metadata: {e}")

    # Invalidamos el caché para que la próxima lectura sea fresca
    try:
        invalidar_todo()
    except Exception:
        pass

    return resultado


def _guardar_metadata(resultado):
    """Guarda un .json con la metadata del backup en Drive y en local."""
    fecha_legible = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    metadata = {
        "fecha": fecha_legible,
        "motivo": resultado["motivo"],
        "entorno": resultado["entorno"],
        "nombre_backup": resultado["nombre_backup"],
        "drive_id": resultado["drive_id"],
        "drive_link": resultado["drive_link"],
        "local_path": resultado["local_path"],
        "ok": resultado["ok"],
        "errores": resultado["errores"],
    }

    # Copia local de la metadata
    if resultado["local_path"]:
        ruta_local = _raiz_proyecto() / resultado["local_path"] / "metadata.json"
        with open(ruta_local, "w", encoding="utf-8") as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)

    # Copia en Drive (dentro de subcarpeta "metadata")
    if resultado["drive_id"] and _config("BACKUP_EN_DRIVE", False):
        try:
            drive = _drive_service()
            carpeta_raiz = _config("BACKUP_DRIVE_CARPETA_ID")
            carpeta_entorno_id = _buscar_o_crear_carpeta(
                drive, resultado["entorno"], carpeta_raiz
            )
            carpeta_metadata_id = _buscar_o_crear_carpeta(
                drive, "metadata", carpeta_entorno_id
            )

            nombre_json = f"{resultado['nombre_backup']}.json"
            from googleapiclient.http import MediaInMemoryUpload

            contenido = json.dumps(metadata, ensure_ascii=False, indent=2).encode("utf-8")
            media = MediaInMemoryUpload(contenido, mimetype="application/json")

            drive.files().create(
                body={"name": nombre_json, "parents": [carpeta_metadata_id]},
                media_body=media,
                fields="id",
            ).execute()
        except Exception as e:
            print(f"⚠️ No se pudo subir metadata a Drive: {e}")


def listar_backups(limite=20):
    """
    Devuelve una lista de backups recientes para mostrar en /configuracion.

    Cada ítem:
      {
        "nombre": "2026-10-07_19-30-45",
        "ruta_local": "instance/backups/produccion/2026-10-07_19-30-45",
        "drive_id": "abc123" o None,
        "fecha": "2026-10-07 19:30:45",
        "motivo": "manual",
        "tamaño_kb": 245,
      }
    """
    carpeta_entorno = _raiz_proyecto() / _config("BACKUP_CARPETA_LOCAL") / _entorno_actual()
    if not carpeta_entorno.exists():
        return []

    backups = []
    for d in sorted(carpeta_entorno.iterdir(), key=lambda x: x.name, reverse=True)[:limite]:
        if not d.is_dir():
            continue
        meta_path = d / "metadata.json"
        metadata = {}
        if meta_path.exists():
            try:
                with open(meta_path, "r", encoding="utf-8") as f:
                    metadata = json.load(f)
            except Exception:
                pass

        # Calcular tamaño total de la carpeta
        tamaño = sum(f.stat().st_size for f in d.glob("*") if f.is_file())

        backups.append({
            "nombre": d.name,
            "ruta_local": str(d.relative_to(_raiz_proyecto())),
            "drive_id": metadata.get("drive_id"),
            "fecha": metadata.get("fecha", d.name),
            "motivo": metadata.get("motivo", "?"),
            "tamaño_kb": round(tamaño / 1024, 1),
        })

    return backups


def borrar_backup(nombre):
    """
    Borra un backup puntual (local y en Drive).
    Se usa desde /configuracion si un backup salió mal.
    """
    borrado_local = False
    borrado_drive = False

    # Local
    ruta = _raiz_proyecto() / _config("BACKUP_CARPETA_LOCAL") / _entorno_actual() / nombre
    if ruta.exists() and ruta.is_dir():
        shutil.rmtree(ruta)
        borrado_local = True

    # Drive
    try:
        drive = _drive_service()
        carpeta_raiz = _config("BACKUP_DRIVE_CARPETA_ID")
        carpeta_entorno_id = _buscar_o_crear_carpeta(
            drive, _entorno_actual(), carpeta_raiz
        )

        consulta = (
            f"name = 'backup_{nombre}' and "
            f"'{carpeta_entorno_id}' in parents and "
            f"trashed = false"
        )
        resultado = drive.files().list(q=consulta, fields="files(id)").execute()
        for f in resultado.get("files", []):
            drive.files().delete(fileId=f["id"]).execute()
            borrado_drive = True
    except Exception as e:
        print(f"⚠️ No se pudo borrar el backup de Drive: {e}")

    return {"borrado_local": borrado_local, "borrado_drive": borrado_drive}