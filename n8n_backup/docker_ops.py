"""Docker-parancsok futtatása, hiba esetén BackupError-ral."""

import subprocess

from n8n_backup.errors import BackupError

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
