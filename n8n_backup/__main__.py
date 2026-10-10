"""
Belépési pont: a teljes mentési folyamat és a jelentés.

Futtatás a projekt gyökeréből:
    python -m n8n_backup
"""

import logging
import shutil
import sys
from logging.handlers import RotatingFileHandler

from n8n_backup.backup import (
    check_size,
    copy_db_files,
    create_zip,
    remove_old,
    remove_zip,
)
from n8n_backup.config import (
    CONTAINER_NAME,
    LOG_BACKUP_COUNT,
    LOG_MAX_BYTES,
    STAGING,
    get_backup_dir,
)
from n8n_backup.docker_ops import run_docker
from n8n_backup.errors import BackupError
from n8n_backup.notify import send_telegram

logger = logging.getLogger(__name__)


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
                RotatingFileHandler(
                    backup_dir / "backup-log.txt",
                    "a",
                    LOG_MAX_BYTES,
                    LOG_BACKUP_COUNT,
                    encoding="utf-8",
                ),
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


if __name__ == "__main__":
    main()
