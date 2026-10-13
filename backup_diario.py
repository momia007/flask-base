# backup_diario.py
"""
Script standalone para hacer un backup diario de la planilla.

Está pensado para ser ejecutado desde el Programador de Tareas de Windows
una vez por día (por ejemplo, a las 12:00 del mediodía).

Uso:
    python backup_diario.py

Reglas:
  - Solo hace UN backup por día. Si ya hay uno con la fecha de hoy,
    no hace nada (y sale con código 0).
  - El log se guarda en logs/backup_diario.log.
  - Si algo falla, sale con código != 0 (para que el Programador de
    Tareas lo registre como fallido).

Códigos de salida:
  0 = backup exitoso, o ya había backup hoy (nada que hacer)
  1 = el backup falló
  2 = error inesperado
"""

import sys
import traceback
from datetime import datetime, date
from pathlib import Path


def _ya_hay_backup_de_hoy(carpeta_entorno):
    """
    ¿Ya hay una carpeta de backup creada hoy?
    Los backups se llaman 'YYYY-MM-DD_HH-MM-SS'. Chequeamos que el prefijo
    de la fecha sea el de hoy.
    """
    if not carpeta_entorno.exists():
        return False

    hoy = date.today().strftime("%Y-%m-%d")
    for d in carpeta_entorno.iterdir():
        if d.is_dir() and d.name.startswith(hoy + "_"):
            return True
    return False


def main():
    raiz = Path(__file__).resolve().parent
    log_path = raiz / "logs" / "backup_diario.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    def log(mensaje):
        linea = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {mensaje}"
        print(linea)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(linea + "\n")

    log("=" * 60)
    log("Iniciando backup diario automatico")

    try:
        from flask import Flask
        from config import Config

        app = Flask(__name__)
        app.config.from_object(Config)

        with app.app_context():
            from services import backup

            # ¿Backups activos?
            if not app.config.get("BACKUP_ACTIVO", True):
                log("[AVISO] Backups desactivados (BACKUP_ACTIVO=False). Nada que hacer.")
                return 0

            entorno = app.config.get("ENTORNO", "produccion")
            log(f"Entorno: {entorno}")
            log(f"Planilla: {app.config.get('SPREADSHEET_NOMBRE')}")

            # ¿Ya hay backup de hoy?
            carpeta_local_base = raiz / app.config.get("BACKUP_CARPETA_LOCAL", "instance/backups")
            carpeta_hoy = carpeta_local_base / entorno
            if _ya_hay_backup_de_hoy(carpeta_hoy):
                log("[SALTAR] Ya existe un backup de hoy. No se hace otro.")
                return 0

            # Hacer backup
            log("Ejecutando backup...")
            resultado = backup.hacer_backup(motivo="diario")

            if resultado["ok"]:
                log(f"[OK] Backup exitoso: {resultado['nombre_backup']}")
                if resultado["local_path"]:
                    log(f"     Local: {resultado['local_path']}")
                if resultado["drive_link"]:
                    log(f"     Drive: {resultado['drive_link']}")
                if resultado["borrados_local"]:
                    log(f"     Se borraron {resultado['borrados_local']} backups viejos (local)")
                if resultado["borrados_drive"]:
                    log(f"     Se borraron {resultado['borrados_drive']} backups viejos (Drive)")
                return 0
            else:
                log("[ERROR] El backup fallo:")
                for err in resultado["errores"]:
                    log(f"     - {err}")
                return 1

    except Exception as e:
        log(f"[ERROR] Error inesperado: {e}")
        log(traceback.format_exc())
        return 2


if __name__ == "__main__":
    sys.exit(main())