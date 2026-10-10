"""
Ez a script az n8n workflow-k adatbázisáról készít mentést:
ZIP-be csomagolja, majd attól függően, hogy sikerült-e a művelet,
Telegramon értesítést küld.
"""

import logging
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")
logger = logging.getLogger(__name__)


# -------------Beállítások-------------

CONTAINER_NAME = "n8n"
KEEP_COUNT = 15  # ennyi mentés marad meg
STAGING = Path(tempfile.gettempdir()) / "n8n-backup-staging"
MIN_ZIP_SIZE = 100 * 1024

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")


class BackupError(Exception):
    """A mentés valamelyik lépése sikertelen"""


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


# -------------Fő folyamat: mentés + jelentés-------------


def main() -> None:
    try:
        backup_dir = get_backup_dir()
        backup_dir.mkdir(parents=True, exist_ok=True)
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)-8s %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
            handlers=[
                logging.StreamHandler(),
                logging.FileHandler(backup_dir / "backup-log.txt", encoding="utf-8"),
            ],
        )
    except (BackupError, OSError) as e:
        logger.error("A mentés el sem indult!\n%s", e)
        send_telegram(
            f"n8n-mentés - HIBA\nA mentés el sem indult (backup_dir_hiba)!\n{e}"
        )
        sys.exit(1)

    restart_ok = False
    backup_ok = False
    error_message = ""
    success_message = ""
    restart_error_message = ""
    try:
        logger.info("Mentés indul")
        run_docker(["stop", "-t", "30", CONTAINER_NAME])
        db_files = copy_db_files()
        logger.info("Kimásolt DB-fájlok: %s", [f.name for f in db_files])
        zip_path = create_zip(db_files, backup_dir)
        try:
            size_mb = check_size(zip_path)
        except BackupError:
            remove_zip(zip_path)
            raise
        backup_ok = True
        success_message = f"A ZIP-fájl kész: {zip_path.name}, mérete: {size_mb} MB"
        logger.info("A ZIP-fájl kész: %s", zip_path)
        logger.info("A ZIP mérete: %s MB", size_mb)
        remove_old(backup_dir)
    # BackupErrorral a várható hibákat fogom meg
    except BackupError as e:
        logger.error("Hiba történt: %s", e)
        error_message = str(e)
    # Exception-nel a váratlan hibákat fogom meg
    except Exception as e:
        logger.exception("Hiba történt: %s", e)
        error_message = f"{type(e).__name__}: {e}"
    finally:
        try:
            run_docker(["start", CONTAINER_NAME])
            restart_ok = True
        except BackupError as e:
            logger.error(
                "A(z) %s konténert nem sikerült újraindítani: %s", CONTAINER_NAME, e
            )
            restart_error_message = str(e)
        # STAGING takarítása, hogy ne maradjon ott a következő futásig
        # a TEMP-ben az érzékeny adat
        try:
            if STAGING.exists():
                shutil.rmtree(STAGING)
        except OSError as e:
            logger.warning("A STAGING mappa utólagos ürítése sikertelen: %s", e)

    if restart_ok and backup_ok:
        message = f"n8n-mentés - OK\n{success_message}"
        level = logging.INFO
    elif restart_ok and not backup_ok:
        message = f"n8n-mentés - FIGYELMEZTETÉS\nSikertelen mentés, de a konténer fut!\n{error_message}"
        level = logging.WARNING
    elif not restart_ok and backup_ok:
        message = f"n8n-mentés - HIBA\nSikeres mentés, de a konténer áll! Kézi újraindítást igényel!\n{success_message}\n{restart_error_message}"
        level = logging.ERROR
    else:
        message = f"n8n-mentés - KRITIKUS HIBA\nSikertelen mentés és sikertelen újraindítás! Sürgős beavatkozást igényel!\n{error_message}\n{restart_error_message}"
        level = logging.CRITICAL
    logger.log(level, message)
    send_telegram(message)
    if not (backup_ok and restart_ok):
        sys.exit(1)


# -------------Telegram-értesítés küldése-------------


def send_telegram(text: str) -> None:
    if not TELEGRAM_CHAT_ID or not TELEGRAM_TOKEN:
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        message_parameters = {"chat_id": TELEGRAM_CHAT_ID, "text": text}
        # dict -> string: urllib.parse.urlencode(message_parameters)
        # string -> bájtok: az .encode() által ez lesz az üzenet törzse
        body = urllib.parse.urlencode(message_parameters).encode()
        # még nem küldi el, csak elkészíti, mint egy megcímzett, lezárt borítékot
        request = urllib.request.Request(url, data=body)

        with urllib.request.urlopen(request, timeout=10):
            pass
    except (urllib.error.URLError, TimeoutError) as e:
        logger.warning("Telegram-üzenet küldése sikertelen: %s", e)


# -------------Docker-hívások-------------


def run_docker(args: list[str]) -> None:
    try:
        result = subprocess.run(
            ["docker", *args],
            capture_output=True,
            timeout=60,
            encoding="UTF-8",
            errors="replace",
        )

    except FileNotFoundError as e:
        raise BackupError("A Docker nem található") from e
    except subprocess.TimeoutExpired as e:
        raise BackupError(f"'docker {' '.join(args)}' sikertelen: időtúllépés") from e

    if result.returncode != 0:
        raise BackupError(
            f"'docker {' '.join(args)}' sikertelen: {result.stderr.strip()}"
        )


# -------------DB-fájlok kimásolása a konténerből-------------


def copy_db_files() -> list[Path]:
    source = f"{CONTAINER_NAME}:/home/node/.n8n/."
    if STAGING.exists():
        shutil.rmtree(STAGING)
    STAGING.mkdir(parents=True, exist_ok=True)
    run_docker(["cp", source, str(STAGING)])
    db_files = list(STAGING.glob("database.sqlite*"))
    if not db_files:
        raise BackupError("Nem található database.sqlite a kimásolt fájlok között")
    return db_files


# -------------ZIP-törlő segédfüggvény--------------------


def remove_zip(zip_path: Path) -> None:
    try:
        zip_path.unlink(missing_ok=True)
        logger.info("Törölve: %s", zip_path.name)
    except OSError as e:
        logger.warning("Nem sikerült törölni: %s --> (%s)", zip_path.name, e)


# -------------ZIP-fájl készítése-------------


def create_zip(ziplist: list[Path], backup_dir: Path) -> Path:
    timestamp = datetime.now().strftime("%Y-%m-%d_%H.%M.%S")
    zip_path = backup_dir / f"n8n_backup_{timestamp}.zip"
    try:
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for f in ziplist:
                zf.write(f, arcname=f.name)
    except Exception:
        remove_zip(zip_path)
        raise
    return zip_path


# -------------ZIP-fájl méretének ellenőrzése-------------


def check_size(zip_path: Path) -> float:
    if not zip_path.exists():
        raise BackupError("Nem található ilyen ZIP-fájl!")
    size_bytes = zip_path.stat().st_size
    size_mb = round(size_bytes / (1024**2), 2)
    if size_bytes < MIN_ZIP_SIZE:
        raise BackupError(f"Gyanúsan kicsi a ZIP-fájl: {size_mb} MB!")
    return size_mb


# -------------Régi mentések törlése (retenció)-------------


def remove_old(backup_dir: Path) -> None:
    zip_files = backup_dir.glob("n8n_backup_*.zip")
    newest_first = sorted(zip_files, key=lambda f: f.stat().st_mtime, reverse=True)
    old_backups = newest_first[KEEP_COUNT:]
    for ob in old_backups:
        remove_zip(ob)


if __name__ == "__main__":
    main()
