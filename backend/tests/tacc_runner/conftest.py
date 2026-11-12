import pytest
from fake_tcloud import FakeTcloud

from app.runners.tacc import TaccRunner


@pytest.fixture
def tcloud(tmp_path, monkeypatch):
    home = tmp_path / "tcloud-home"
    home.mkdir()
    monkeypatch.setenv("FAKE_TCLOUD_HOME", str(home))
    return FakeTcloud(home)


@pytest.fixture
def client_dir(tmp_path):
    """A stand-in for the client folder, so the tests never write into the real one."""
    folder = tmp_path / "client"
    folder.mkdir()
    (folder / "server-url.txt").write_bytes(b"http://node-7:8000/v1\n")
    return folder


@pytest.fixture
def runner(tcloud, client_dir):
    return TaccRunner(tcloud=tcloud.command, poll_seconds=0, client_dir=client_dir)
