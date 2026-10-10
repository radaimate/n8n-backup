"""A mentés lépései: DB-fájlok kimásolása, ZIP készítése, ellenőrzése és a retenció."""

import logging
import shutil
import zipfile
from datetime import datetime
from pathlib import Path

from n8n_backup.config import CONTAINER_NAME, KEEP_COUNT, MIN_ZIP_SIZE, STAGING
from n8n_backup.docker_ops import run_docker
from n8n_backup.errors import BackupError

logger = logging.getLogger(__name__)

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
