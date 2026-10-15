"""A docker_ops.py függvényeinek tesztjei."""

import subprocess

import pytest

from n8n_backup.docker_ops import run_docker
from n8n_backup.errors import BackupError


def test_run_docker_nonzero_returncode(monkeypatch):
    # *args = pozícionális paraméterek, **kwargs = kulcsszavas, a *annyit tesz hogy nincs meghatározott mennyiség akármennyi paraméter adható
    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(
            args=args[0],
            returncode=1,
            stdout="",
            stderr="Nem létezik ilyen konténer: n8n\n",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(BackupError, match="Nem létezik ilyen konténer:"):
        run_docker(["stop", "n8n"])


def test_run_docker_not_found(monkeypatch):
    def fake_run(*args, **kwargs):
        raise FileNotFoundError

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(BackupError, match="A Docker nem található"):
        run_docker(["stop", "n8n"])


def test_run_docker_timeout(monkeypatch):
    def fake_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=args[0], timeout=10)

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(BackupError, match="'docker stop n8n' sikertelen: időtúllépés"):
        run_docker(["stop", "n8n"])


def test_run_docker_success(monkeypatch):
    calls = []

    def fake_run(*args, **kwargs):
        calls.append(args[0])
        return subprocess.CompletedProcess(args=args[0], returncode=0, stdout="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    run_docker(["stop", "n8n"])
    assert calls == [["docker", "stop", "n8n"]]
