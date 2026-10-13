"""A backup.py függvényeinek tesztjei."""

import os
import zipfile

import pytest

from n8n_backup.backup import check_size, create_zip, remove_old, remove_zip
from n8n_backup.config import KEEP_COUNT, MIN_ZIP_SIZE
from n8n_backup.errors import BackupError


def test_check_size_missing_file(tmp_path):
    zip_path = tmp_path / "nincs_ilyen.zip"  # létre sem hozzuk

    with pytest.raises(BackupError, match="Nem található"):
        check_size(zip_path)


def test_check_size_returns_mb(tmp_path):
    zip_path = tmp_path / "nagy.zip"
    zip_path.write_bytes(b"\0" * (1024 * 1024))  # pontosan 1 MiB

    assert check_size(zip_path) == 1.0


def test_check_size_too_small(tmp_path):
    zip_path = tmp_path / "kicsi.zip"
    zip_path.write_bytes(b"\0" * 10)

    with pytest.raises(BackupError, match="Gyanúsan kicsi"):
        check_size(zip_path)


def test_check_size_exactly_min(tmp_path):
    zip_path = tmp_path / "pontos.zip"
    zip_path.write_bytes(b"\0" * MIN_ZIP_SIZE)

    assert check_size(zip_path) == 0.1


def test_check_size_one_below_min(tmp_path):
    zip_path = tmp_path / "minuszegy.zip"
    zip_path.write_bytes(b"\0" * (MIN_ZIP_SIZE - 1))

    with pytest.raises(BackupError, match="Gyanúsan kicsi"):
        check_size(zip_path)


# --------------------remove-old-------------------------


def test_remove_old_keeps_newest(tmp_path):
    # Arrange: KEEP_COUNT + 2 db zip, mindegyik 1 perccel újabb az előzőnél
    for i in range(KEEP_COUNT + 2):
        zip_path = tmp_path / f"n8n_backup_{i:02d}.zip"
        zip_path.write_bytes(b"")
        mtime = 1_700_000_000 + i * 60
        os.utime(zip_path, (mtime, mtime))

    # Act
    remove_old(tmp_path)

    # Assert: a 2 legrégebbi (00, 01) eltűnt, a többi megmaradt
    remaining = sorted(f.name for f in tmp_path.iterdir())
    expected = [f"n8n_backup_{i:02d}.zip" for i in range(2, KEEP_COUNT + 2)]
    assert remaining == expected


def test_remove_old_less_than_keep_count(tmp_path):
    for i in range(3):
        zip_path = tmp_path / f"n8n_backup_{i:02d}.zip"
        zip_path.write_bytes(b"")
        mtime = 1_700_000_000 + i * 60
        os.utime(zip_path, (mtime, mtime))

    remove_old(tmp_path)

    # Assert: 3 db-nak kell lennie még mindig
    assert len(list(tmp_path.iterdir())) == 3


def test_remove_old_ignores_other_files(tmp_path):
    for i in range(KEEP_COUNT + 2):
        zip_path = tmp_path / f"n8n_backup_{i:02d}.zip"
        zip_path.write_bytes(b"")
        mtime = 1_700_000_000 + i * 60
        os.utime(zip_path, (mtime, mtime))

    log_path = tmp_path / "n8n_log.txt"
    log_path.write_bytes(b"")
    logmtime = 1_000_000_000
    os.utime(log_path, (logmtime, logmtime))
    remove_old(tmp_path)

    # Assert: n8n_log-ot nem szabadna bántania

    assert log_path.exists()


# --------------------create-zip-------------------------


def test_create_zip_creates_file(tmp_path):
    source_path = tmp_path / "src"
    source_path.mkdir()
    out_path = tmp_path / "out"
    out_path.mkdir()

    db_path = source_path / "database.sqlite"
    db_path.write_bytes(b"teszt")
    wal_path = source_path / "database.wal"
    wal_path.write_bytes(b"teszt")

    db_files = [wal_path, db_path]

    zip_path = create_zip(db_files, out_path)

    assert zip_path.exists()
    assert zip_path.match("n8n_backup_*.zip")
    assert zip_path.parent == out_path


def test_create_zip_contents(tmp_path):
    source_path = tmp_path / "src"
    source_path.mkdir()
    out_path = tmp_path / "out"
    out_path.mkdir()

    db_path = source_path / "database.sqlite"
    db_path.write_bytes(b"teszt")
    wal_path = source_path / "database.wal"
    wal_path.write_bytes(b"teszt")

    db_files = [wal_path, db_path]

    zip_path = create_zip(db_files, out_path)

    with zipfile.ZipFile(zip_path, "r") as zf:
        names = sorted(zf.namelist())

    expected_names = sorted([db_path.name, wal_path.name])

    assert names == expected_names


def test_create_zip_error_removes_partial_zip(tmp_path):
    out_path = tmp_path / "out"
    out_path.mkdir()
    missing_path = tmp_path / "nincs_ilyen.sqlite"  # létre sem hozzuk

    with pytest.raises(FileNotFoundError):
        create_zip([missing_path], out_path)

    assert len(list(out_path.iterdir())) == 0


# --------------------remove-zip-------------------------


def test_remove_zip_removes_real(tmp_path):
    zip_path = tmp_path / "n8n_backup_.zip"
    zip_path.write_bytes(b"teszt")

    remove_zip(zip_path)

    assert not zip_path.exists()


def test_remove_zip_missing_file_no_error(tmp_path):
    zip_path = tmp_path / "nincs_ilyen.zip"
    remove_zip(zip_path)
