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
KEEP_COUNT = 15  # ennyi mentés marad meg
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
    restart_ok = False

    try:
        logger.info("mentes indul")
        run_docker(["stop", "-t", "30", CONTAINER_NAME])
        db_fajlok = copy_db_files()
        logger.info("Kimásolt DB fájlok: %s", [f.name for f in db_fajlok])
        zip_utvonal = zip_maker(db_fajlok)
        try:
            meret = ell_meret(zip_utvonal)
        except BackupError:
            try:
                zip_utvonal.unlink(missing_ok=True)
            except OSError as e:
                logger.warning("Nem sikerült törölni: %s --> (%s)", zip_utvonal.name, e)
            raise
        logger.info("A ZIP file kész: %s", zip_utvonal)
        logger.info(f"A ZIP mérete: {meret}MB")
        regi_torles()
    # BackupErrorral a várható hibákat fogom meg
    except BackupError as b:
        logger.error(f"Hiba történt:{b}")
        send_telegram(f"A folyamat közben hiba lépett fel:{b}")
        sys.exit(1)
    # Exception-nel a váratlan hibákat fogom meg
    except Exception as e:
        logger.exception(f"Hiba történt:{e}")
        send_telegram(f"A folyamat közben hiba lépett fel:{e}")
        sys.exit(1)
    else:
        send_telegram(f"Sikeres mentés! :{zip_utvonal}--{meret}")
    finally:
        try:
            run_docker(["start", CONTAINER_NAME])
            restart_ok = True
        except BackupError as b:
            logger.error(f"A {CONTAINER_NAME} konténert nem sikerült újraindítani: {b}")
            send_telegram(
                f"KRITIKUS! a(z) {CONTAINER_NAME} konténert nem sikerült újraindítani! {b}"
            )
        # STAGING takarítására hogy ne maradjon ott a következő futásig a TEMP-ben az érzékeny adat
        try:
            if STAGING.exists():
                shutil.rmtree(STAGING)
        except OSError as o:
            logger.warning(f"A STAGING mappa utolagos ürítése sikertelen: {o}")


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
    try:
        with zipfile.ZipFile(ZIP_HELY, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for f in lista:
                zf.write(f, arcname=f.name)
    except Exception:
        try:
            ZIP_HELY.unlink(missing_ok=True)
        except OSError as o:
            logger.warning(
                f"Hiba lépett fel a zip_maker hibakezelésében, Nem sikerült törölni a rossz félkész ZIP-et! :{ZIP_HELY.name}--{o}"
            )
        raise
    return ZIP_HELY


def ell_meret(zip_hely: Path) -> float:
    if not zip_hely.exists():
        raise BackupError("Nem található ilyen ZIP file!")
    meret = zip_hely.stat().st_size
    meret_mb = round(meret / (1024**2), 2)
    if meret < MIN_ZIP_SIZE:
        raise BackupError(f"Gyanúsan kicsi a ZIP-mérete: {meret_mb}MB !")
    return meret_mb


def regi_torles() -> None:
    zipek = BACKUP_DIR.glob("n8n_backup_*.zip")
    rendezve = sorted(zipek, key=lambda f: f.stat().st_mtime, reverse=True)
    regiek = rendezve[KEEP_COUNT:]
    for r in regiek:
        try:
            logger.info(f"A {r.name} mentés már régi így törlésre kerül!")
            r.unlink()
        except OSError as e:
            logger.warning("Nem sikerült törölni: %s --> (%s)", r.name, e)


if __name__ == "__main__":
    main()
