import os
from datetime import datetime
import logging
import sys
import subprocess
import tempfile
import zipfile
import urllib.error
import urllib.request
import urllib.parse
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")
logger = logging.getLogger(__name__)

# -------------Beállítások-------------

CONTAINER_NAME = "n8n"
KEEP_COUNT = 14  # ennyi mentés marad meg
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

try:
    backup_path = os.environ["BACKUP_DIR"]
except KeyError:
    sys.exit("A BACKUP_DIR egyáltalán nincs a .env-ben!")
else:
    # .strip() arra az esetre ha valaki csak egy szőközt ad meg!-a szó elejéről és végéről levágja a szőközöket!
    if not backup_path.strip():
        sys.exit("A BACKUP_DIR üres a .env-ben!")
    BACKUP_DIR = Path(backup_path.strip())


def main():
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(BACKUP_DIR / "backup-log.txt", encoding="utf-8"),
        ],
    )
    logger.info("mentes indul")


if __name__ == "__main__":
    main()
