"""Beállítások: konstansok, a .env betöltése és a BACKUP_DIR ellenőrzése."""

import os
import tempfile
from pathlib import Path

from dotenv import load_dotenv

from n8n_backup.errors import BackupError

load_dotenv(Path(__file__).parent.parent / ".env")


# -------------Beállítások-------------

CONTAINER_NAME = "n8n"
N8N_DATA_DIR = "/home/node/.n8n"  # az n8n adatmappája a konténeren belül
KEEP_COUNT = 15  # ennyi mentés marad meg
STAGING = Path(tempfile.gettempdir()) / "n8n-backup-staging"
MIN_ZIP_SIZE = 100 * 1024
LOG_MAX_BYTES = 1024 * 1024
LOG_BACKUP_COUNT = 3

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# -------------BACKUP_DIR beolvasása és ellenőrzése-------------


def get_backup_dir() -> Path:
    try:
        backup_path = os.environ["BACKUP_DIR"]
    except KeyError:
        raise BackupError("A BACKUP_DIR egyáltalán nincs a .env-ben!") from None
    else:
        # .strip(): a szöveg elejéről és végéről levágja a szóközöket,
        # így a csak szóközből álló érték is üresnek számít
        backup_path = backup_path.strip()
        if not backup_path:
            raise BackupError("A BACKUP_DIR üres a .env-ben!")
    return Path(backup_path)
