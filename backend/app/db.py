import sqlite3
from pathlib import Path

DEFAULT_DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def connect(data_dir):
    """Open the SQLite job database."""
    data_dir.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(data_dir / "jpilot.db")
