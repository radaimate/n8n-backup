import os
from datetime import datetime
import logging
import sys
import subprocess
import tempfile
import zipfile
import urllib.error
import urllib.request
import urllib.parse
from pathlib import Path

# -------------Beállítások------------

CONTAINER_NAME = "n8n"
BACKUP_DIR = Path("n8n-backup")
K_COUNT = 14  # ennyi mentés marad meg

print()
