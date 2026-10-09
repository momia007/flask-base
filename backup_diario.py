# backup_diario.py
"""
Script standalone para hacer un backup sin arrancar la app web.

Está pensado para ser ejecutado desde el Programador de Tareas de Windows
una vez por día.

Uso:
    python backup_diario.py

Guarda el resultado en un log dentro de instance/backups/backup_diario.log.
"""

import sys
import traceback
from datetime import datetime
from pathlib import Path


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
    log("Iniciando backup diario automático")

    try:
        # Importar la app para tener contexto de Flask (config, etc.)
        from flask import Flask
        from config import Config

        app = Flask(__name__)
        app.config.from_object(Config)

        with app.app_context():
            from services import backup

            # Chequear que los backups estén activos
            if not app.config.get("BACKUP_ACTIVO", True):
                log("⚠️ Backups desactivados (BACKUP_ACTIVO=False). Nada que hacer.")
                return 0

            # Hacer el backup
            log(f"Entorno: {app.config.get('ENTORNO')}")
            log(f"Planilla: {app.config.get('SPREADSHEET_NOMBRE')}")
            log("Ejecutando backup...")

            resultado = backup.hacer_backup(motivo="automático-diario")

            if resultado["ok"]:
                log(f"✅ Backup exitoso: {resultado['nombre_backup']}")
                if resultado["local_path"]:
                    log(f"   Local: {resultado['local_path']}")
                if resultado["drive_link"]:
                    log(f"   Drive: {resultado['drive_link']}")
                if resultado["borrados_local"]:
                    log(f"   Se borraron {resultado['borrados_local']} backups viejos (local)")
                if resultado["borrados_drive"]:
                    log(f"   Se borraron {resultado['borrados_drive']} backups viejos (Drive)")
                return 0
            else:
                log("❌ El backup falló:")
                for err in resultado["errores"]:
                    log(f"   - {err}")
                return 1

    except Exception as e:
        log(f"❌ Error inesperado: {e}")
        log(traceback.format_exc())
        return 2


if __name__ == "__main__":
    sys.exit(main())