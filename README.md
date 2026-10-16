# n8n-backup

[![CI](https://github.com/radaimate/n8n-backup/actions/workflows/ci.yml/badge.svg)](https://github.com/radaimate/n8n-backup/actions/workflows/ci.yml)

*[Magyar változat](README.hu.md)*

Automated backup of the SQLite database of an [n8n](https://n8n.io) instance running in Docker, on Windows.

The script stops the n8n container cleanly, copies the database out of it, packs it into a timestamped ZIP file, keeps only the most recent backups, restarts the container and reports the result via Telegram. It is designed to run from Windows Task Scheduler.

The project is a Python rewrite of an earlier PowerShell script, split into modules, with type hints and tests. Log and notification messages are in Hungarian.

## Features

- **Consistent backup:** the container is stopped with `docker stop -t 30`, so n8n closes the database cleanly and does not write to it during the copy.
- **Timestamped ZIP:** file names like `n8n_backup_2026-10-15_03.00.00.zip`, with the files at the root of the archive.
- **Size check:** a suspiciously small ZIP (under 100 KB) is treated as an error and deleted.
- **Retention:** only the 15 most recent backups are kept, older ones are deleted.
- **The container is always restarted,** even if the backup failed.
- **Telegram notifications** with distinct states (OK / WARNING / ERROR / CRITICAL ERROR / CONFIGURATION ERROR).
- **The encryption key never leaves the container:** only the `database.sqlite*` files are copied out, the `config` file is not.
- **Exit code:** `1` on any failure, so Task Scheduler also sees when something went wrong.
- **Rotating log file:** at most 1 MB, with 3 previous copies.
- **Cleanup:** temporary copies are deleted from `%TEMP%` at the end of each run.

## Requirements

- Windows
- Python 3.13
- Docker Desktop with a running container named `n8n` (using the default data directory of the official `n8nio/n8n` image: `/home/node/.n8n`)
- A Telegram bot (optional, only for notifications)

## Installation

```powershell
git clone https://github.com/radaimate/n8n-backup.git
cd n8n-backup
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Configuration

Copy `.env.example` to `.env` and fill it in:

```powershell
Copy-Item .env.example .env
```

| Variable | Required | Description |
|---|---|---|
| `BACKUP_DIR` | yes | Folder for the ZIP files and the log. Created if it does not exist. Pointing it to a OneDrive folder also gives you an off-site copy. |
| `TELEGRAM_TOKEN` | no | The Telegram bot token (issued by [@BotFather](https://t.me/BotFather)). |
| `TELEGRAM_CHAT_ID` | no | The ID of the chat that receives the notifications. |

If `TELEGRAM_TOKEN` or `TELEGRAM_CHAT_ID` is empty, no notification is sent, but the backup still runs.

The `.env` file contains secrets, so it is listed in `.gitignore` and never committed.

Further settings live in [n8n_backup/config.py](n8n_backup/config.py):

| Constant | Default | Meaning |
|---|---|---|
| `CONTAINER_NAME` | `"n8n"` | Name of the container to back up |
| `KEEP_COUNT` | `15` | Number of backups to keep |
| `MIN_ZIP_SIZE` | `100 * 1024` | ZIP files smaller than this (in bytes) are treated as an error |
| `LOG_MAX_BYTES` | `1024 * 1024` | Maximum size of the log file |
| `LOG_BACKUP_COUNT` | `3` | Number of old log files to keep |

## Usage

From the project root:

```powershell
python -m n8n_backup
```

| Exit code | Meaning |
|---|---|
| `0` | The backup succeeded and the container is running |
| `1` | A step failed (details in the log and the Telegram message) |

## How a backup run works

1. Validate `BACKUP_DIR` and set up logging
2. Stop the container (`docker stop -t 30 n8n`)
3. Copy the `database.sqlite*` files into a temporary folder (`docker cp`)
4. Pack the files into a ZIP
5. Check the ZIP size
6. Delete old backups
7. Restart the container (`docker start n8n`), **even on failure**
8. Delete the temporary folder
9. Report: log + Telegram + exit code

## Scheduling with Task Scheduler

In Task Scheduler, create a new task (*Create Task*) and set the following on the *Actions* tab:

| Field | Value |
|---|---|
| Program/script | The **full** path of the venv Python, e.g. `C:\...\n8n-backup\.venv\Scripts\python.exe` |
| Add arguments | `-m n8n_backup` |
| Start in | The project root folder, e.g. `C:\...\n8n-backup` |

- **Program/script** must point to the venv Python, not the global `python`, because only the venv has the dependencies installed.
- **Start in** is required: `python -m n8n_backup` looks for the `n8n_backup` package in the current directory.
- Docker Desktop usually runs only while a user is logged on, so the task should also use *Run only when user is logged on*.

## Output

**Backups:** `BACKUP_DIR\n8n_backup_YYYY-MM-DD_HH.MM.SS.zip`, containing `database.sqlite` (and the `-wal` and `-shm` files, if present).

**Log:** `BACKUP_DIR\backup-log.txt`. Above 1 MB a new file is started, and the old ones are kept as `backup-log.txt.1` … `.3`.

**Telegram notifications** (the messages themselves are in Hungarian):

| State | Message label | Backup | Container | Action |
|---|---|---|---|---|
| OK | `OK` | succeeded | running | — |
| Warning | `FIGYELMEZTETÉS` | failed | running | Check the log; the next run retries |
| Error | `HIBA` | succeeded | **stopped** | Start the container manually |
| Critical error | `KRITIKUS HIBA` | failed | **stopped** | Immediate action required |
| Configuration error | `KONFIGURÁCIÓS HIBA` | never started | running (not stopped) | Fix `.env`; the next run will not succeed on its own |

The configuration error is reported when `BACKUP_DIR` is missing, empty or cannot be created. In that case the script does not touch the container at all.

## Restore

> **Important: the encryption key.** n8n stores credentials (API keys, passwords) encrypted in the database. The key is **not** part of the backup: it is in the container's `/home/node/.n8n/config` file or in the `N8N_ENCRYPTION_KEY` environment variable. Without the key, restored credentials cannot be used, so store it separately, e.g. in a password manager:
>
> ```powershell
> docker exec n8n cat /home/node/.n8n/config
> ```

Restore steps:

```powershell
# 1. Stop the container
docker stop -t 30 n8n

# 2. Extract the selected backup
Expand-Archive .\n8n_backup_2026-10-15_03.00.00.zip -DestinationPath .\restore

# 3. Delete the old WAL and SHM files left in the container.
#    If they stayed, SQLite would replay the journal of a different database
#    onto the restored file, which can corrupt it.
docker run --rm --volumes-from n8n alpine rm -f /home/node/.n8n/database.sqlite-wal /home/node/.n8n/database.sqlite-shm

# 4. Copy all files from the ZIP back into the container
docker cp .\restore\. n8n:/home/node/.n8n/

# 5. Set the owner before starting. docker cp copies files as root,
#    but n8n runs as the node user (UID 1000).
docker run --rm --volumes-from n8n alpine sh -c "chown 1000:1000 /home/node/.n8n/database.sqlite*"

# 6. Start
docker start n8n
```

`--volumes-from` works when the data directory is on a Docker volume (true for the official n8n setup). Docker pulls the `alpine` image on first use.

This procedure has been tested by restoring a backup into a separate container running the same n8n image: users, workflows and credentials were restored, and an HTTP request confirmed that the restored credentials can be decrypted with the separately stored key.

## Design decisions

**Why stop the container?**

If we copied from a running container, we could copy right when n8n is writing to the database, and inconsistent data could end up in the ZIP.

**Why `urllib` instead of `requests`?**

The script sends a single POST request per day, so `requests` is not worth it, even though its syntax is simpler: it is not part of the standard library (fewer dependencies = less maintenance). With more API calls or JSON handling, I would choose `requests`.

**Why are there two separate `try` blocks in `finally`?**

`finally` contains two cleanup steps, each in its own `try`, so that a failure in one does not prevent the other. For example, if the first had no `try` and `docker start` failed, the `STAGING` (temporary) folder would not be deleted and would be left behind, which is a security risk. The report would not be sent either, because the exception would propagate out of `main()`: the script would crash without a Telegram message.

**Why is the key not in the backup? (n8n encryption key)**

n8n workflows connect to external services such as Gmail or Google Sheets, and n8n stores the required credentials encrypted in `database.sqlite`; the encryption key is in the `config` file. Encrypted data and its key are deliberately stored apart: if a cloud-synced backup leaks, the credentials are useless without the key. For the same reason, the script does not copy the `config` file out of the container, not even temporarily; it copies only the database files.

**Why Telegram?**

It is independent of n8n: if n8n is down, the alert still arrives, because the monitored system is not reporting on itself. It is also free and was simple to implement for what I needed, with no mail server required, and the alerts are fast and push-based. In addition, some companies (Meta) seriously restrict or penalize automation on their messengers.

**Why Python?**

Simply because, alongside C/C++, Python is the language I have the most experience with, and of the three it is the best suited for automation. Its rich standard library also helped a lot.

**Why a CI workflow?**

It is easy to set up but very useful: on every push and pull request it runs the tests and checks formatting, so if something is broken it shows up on GitHub, and no further work gets built on broken code. And since it runs on a clean machine, on both Ubuntu and Windows, it also reveals anything that only works on my own machine.

## Development

```powershell
pip install -r requirements-dev.txt

pytest              # tests
ruff check .        # lint
ruff format .       # formatting
```

The tests need neither Docker nor network access: `subprocess.run` and the `urllib` calls are replaced using pytest's `monkeypatch` fixture.

### Continuous integration (CI)

On every push and pull request, GitHub Actions ([.github/workflows/ci.yml](.github/workflows/ci.yml)) runs the same three checks on both Ubuntu and Windows: `ruff check`, `ruff format --check` and `pytest`. The badge at the top of this README shows the result.

### Project structure

```
n8n_backup/
  __main__.py     # entry point: the backup run and the report
  config.py       # constants, loading .env, validating BACKUP_DIR
  backup.py       # copying DB files, creating and checking the ZIP, retention
  docker_ops.py   # running Docker commands
  notify.py       # Telegram notification
  errors.py       # BackupError exception class
tests/            # pytest tests
.github/workflows/
  ci.yml          # GitHub Actions: lint + tests on Ubuntu and Windows
```

## License

[MIT](LICENSE)
