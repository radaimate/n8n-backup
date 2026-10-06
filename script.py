import os
from datetime import datetime
import logging
import sys
import subprocess
import tempfile
import zipfile
import urllib.error
import urllib.request
import shutil
import urllib.parse
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")
logger = logging.getLogger(__name__)

# -------------Beállítások-------------

CONTAINER_NAME = "n8n"
KEEP_COUNT = 14  # ennyi mentés marad meg
STAGING = Path(tempfile.gettempdir()) / "n8n-backup-staging"

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
MIN_ZIP_SIZE = 100 * 1024


class BackupError(Exception):
    """A mentés valamelyik lépése sikertelen"""


try:
    backup_path = os.environ["BACKUP_DIR"]
except KeyError:
    sys.exit("A BACKUP_DIR egyáltalán nincs a .env-ben!")
else:
    # .strip() arra az esetre ha valaki csak egy szőközt ad meg!-a szó elejéről és végéről levágja a szőközöket!
    if not backup_path.strip():
        sys.exit("A BACKUP_DIR üres a .env-ben!")
    BACKUP_DIR = Path(backup_path.strip())

# -------------Logging konfigrurálás-------------


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
    db_fajlok = copy_db_files()
    logger.info("Kimásolt DB fájlok: %s", [f.name for f in db_fajlok])
    zip_utvonal = zip_maker(db_fajlok)
    logger.info("A ZIP file kész: %s", zip_utvonal)
    logger.info(f"A ZIP mérete: {ell_meret(zip_utvonal)}")


# -------------Telegram-üzenet-------------


def send_telegram(text: str) -> None:
    if not TELEGRAM_CHAT_ID or not TELEGRAM_TOKEN:
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        adatok = {"chat_id": TELEGRAM_CHAT_ID, "text": text}
        # dict -> string :urllib.parse.urlencode(adatok)
        # string -> bájtok, az encode álltal ez lesz az üzenet maga
        body = urllib.parse.urlencode(adatok).encode()
        # nem küldi csak mint egy készrecímzett lezárt borítíkot, elkészíti"
        keres = urllib.request.Request(url, data=body)

        with urllib.request.urlopen(keres, timeout=10):
            pass
    except (urllib.error.URLError, TimeoutError) as e:
        logger.warning(f"Telegram üzenet küldése sikertelen: {e}")


# -------------Docker-hívások-------------


def run_docker(args: list[str]) -> None:
    try:
        eredmeny = subprocess.run(
            ["docker", *args],
            capture_output=True,
            timeout=60,
            encoding="UTF-8",
            errors="replace",
        )

    except FileNotFoundError as e:
        raise BackupError("A docker nem található") from e
    except subprocess.TimeoutExpired as e:
        raise BackupError(f"{' '.join(args)} sikertelen: A timeout idő lejárt") from e

    if eredmeny.returncode != 0:
        raise BackupError(
            f"'docker {' '.join(args)}' sikertelen: {eredmeny.stderr.strip()}"
        )


def copy_db_files() -> list[Path]:
    forras = f"{CONTAINER_NAME}:/home/node/.n8n/."
    if STAGING.exists():
        shutil.rmtree(STAGING)
    STAGING.mkdir(parents=True, exist_ok=True)
    run_docker(["cp", forras, str(STAGING)])
    db_fajlok = list(STAGING.glob("database.sqlite*"))
    if not db_fajlok:
        raise BackupError("Nem található database.sqlite a kimásolt fájlok között")
    return db_fajlok


def zip_maker(lista: list[Path]) -> Path:
    datum = datetime.now().strftime("%Y-%m-%d_%H.%M.%S")
    ZIP_HELY = Path(BACKUP_DIR, f"n8n_backup_{datum}.zip")
    with zipfile.ZipFile(ZIP_HELY, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for f in lista:
            zf.write(f, arcname=f.name)
    return ZIP_HELY


def ell_meret(zip_hely: Path) -> float:
    if not zip_hely.exists():
        raise BackupError("Nem található ilyen ZIP file!")
    if zip_hely.stat().st_size < (MIN_ZIP_SIZE):
        raise BackupError("Gyanúsan kicsi a ZIP-mérete!")
    return round((zip_hely.stat().st_size) / (1024**2), 2)


if __name__ == "__main__":
    main()
