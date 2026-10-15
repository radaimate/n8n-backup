"""Tesztek a config modul-hoz"""

import pytest

from n8n_backup.config import get_backup_dir
from n8n_backup.errors import BackupError


def test_get_backup_dir_missing(monkeypatch):
    monkeypatch.delenv("BACKUP_DIR", raising=False)

    with pytest.raises(BackupError, match="A BACKUP_DIR egyáltalán nincs"):
        get_backup_dir()


def test_get_backup_dir_empty(monkeypatch):
    monkeypatch.setenv("BACKUP_DIR", "    ")

    with pytest.raises(BackupError, match="A BACKUP_DIR üres"):
        get_backup_dir()


def test_get_backup_dir_valid(monkeypatch, tmp_path):
    monkeypatch.setenv("BACKUP_DIR", f"    {str(tmp_path)}   ")

    return_path = get_backup_dir()
    assert return_path == tmp_path
