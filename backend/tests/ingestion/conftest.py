import sqlite3

import pytest

from app import db


@pytest.fixture
def conn(tmp_path):
    """A temporary job database, so no test touches the real one."""
    connection = db.connect(tmp_path)
    connection.row_factory = sqlite3.Row
    yield connection
    connection.close()
