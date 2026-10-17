"""A __main__.py modul tesztjei."""

import pytest

from n8n_backup import __main__
from n8n_backup.config import CONTAINER_NAME
from n8n_backup.errors import BackupError

# A stop és a start minden esetben lefut, a finally miatt hiba után is
STOP_START = [["stop", "-t", "30", CONTAINER_NAME], ["start", CONTAINER_NAME]]


@pytest.fixture
def fakes(monkeypatch, tmp_path):
    """Minden külső függést lecserél a sikeres változatra; a tesztek ezt írják felül."""
    messages = []
    calls = []

    def fake_get_backup_dir():
        return tmp_path

    def fake_copy_db_files():
        return [tmp_path / "database.sqlite"]

    def fake_create_zip(*args, **kwargs):
        return tmp_path / "x.zip"

    def fake_check_size(zip_path):
        return 1.5

    def fake_remove_old(backup_dir):
        pass

    def fake_send_telegram(message):
        messages.append(message)

    def fake_run_docker(args):
        calls.append(args)

    monkeypatch.setattr(__main__, "get_backup_dir", fake_get_backup_dir)
    monkeypatch.setattr(__main__, "copy_db_files", fake_copy_db_files)
    monkeypatch.setattr(__main__, "create_zip", fake_create_zip)
    monkeypatch.setattr(__main__, "check_size", fake_check_size)
    monkeypatch.setattr(__main__, "remove_old", fake_remove_old)
    monkeypatch.setattr(__main__, "send_telegram", fake_send_telegram)
    monkeypatch.setattr(__main__, "run_docker", fake_run_docker)
    monkeypatch.setattr(__main__, "STAGING", tmp_path / "staging")

    return {"messages": messages, "calls": calls}


def test_main_all_ok(fakes):
    __main__.main()

    assert len(fakes["messages"]) == 1
    assert fakes["messages"][0].startswith("n8n-mentés - OK")
    assert fakes["calls"] == STOP_START


def test_main_backup_fails(fakes, monkeypatch):
    def fake_copy_db_files():
        raise BackupError()

    monkeypatch.setattr(__main__, "copy_db_files", fake_copy_db_files)

    with pytest.raises(SystemExit) as exc:
        __main__.main()

    assert exc.value.code == 1
    assert fakes["calls"] == STOP_START
    assert len(fakes["messages"]) == 1
    assert fakes["messages"][0].startswith("n8n-mentés - FIGYELMEZTETÉS")


def test_main_restart_fails(fakes, monkeypatch):
    def fake_run_docker(args):
        fakes["calls"].append(args)
        if args[0] == "start":
            raise BackupError("start hiba")

    monkeypatch.setattr(__main__, "run_docker", fake_run_docker)

    with pytest.raises(SystemExit) as exc:
        __main__.main()

    assert exc.value.code == 1
    assert len(fakes["messages"]) == 1
    assert fakes["messages"][0].startswith("n8n-mentés - HIBA")
    assert "start hiba" in fakes["messages"][0]
    assert fakes["calls"] == STOP_START


def test_main_critical(fakes, monkeypatch):
    def fake_copy_db_files():
        raise BackupError("mentés hiba")

    def fake_run_docker(args):
        fakes["calls"].append(args)
        if args[0] == "start":
            raise BackupError("start hiba")

    monkeypatch.setattr(__main__, "run_docker", fake_run_docker)
    monkeypatch.setattr(__main__, "copy_db_files", fake_copy_db_files)
    with pytest.raises(SystemExit) as exc:
        __main__.main()
    assert exc.value.code == 1
    assert fakes["calls"] == STOP_START
    assert len(fakes["messages"]) == 1
    assert fakes["messages"][0].startswith("n8n-mentés - KRITIKUS HIBA")
    assert "mentés hiba" in fakes["messages"][0]
    assert "start hiba" in fakes["messages"][0]


def test_main_config_failure(fakes, monkeypatch):
    def fake_get_backup_dir():
        raise BackupError("konfigurációs hiba")

    monkeypatch.setattr(__main__, "get_backup_dir", fake_get_backup_dir)

    with pytest.raises(SystemExit) as exc:
        __main__.main()
    assert exc.value.code == 1
    assert fakes["messages"][0].startswith("n8n-mentés - KONFIGURÁCIÓS HIBA")
    assert "konfigurációs hiba" in fakes["messages"][0]
    assert fakes["calls"] == []
    assert len(fakes["messages"]) == 1
