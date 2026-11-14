import sqlite3
from pathlib import Path

from app.models.job import CREATE_TABLE

DEFAULT_DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def connect(data_dir):
    """Open the SQLite job database, creating its table if it is not there yet."""
    data_dir.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(data_dir / "jpilot.db")
    conn.execute(CREATE_TABLE)
    return conn
