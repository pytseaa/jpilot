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
def runner(tcloud):
    return TaccRunner(tcloud=tcloud.command, poll_seconds=0)
