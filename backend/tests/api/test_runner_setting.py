import pytest

from app.main import create_app
from app.runners.fake import FakeRunner
from app.runners.tacc import TaccRunner


def test_the_tacc_runner_is_used_when_the_setting_is_not_given(tmp_path, monkeypatch):
    monkeypatch.delenv("JPILOT_RUNNER", raising=False)

    assert isinstance(create_app(data_dir=tmp_path).state.runner, TaccRunner)


def test_the_fake_runner_is_used_when_the_setting_is_fake(tmp_path, monkeypatch):
    monkeypatch.setenv("JPILOT_RUNNER", "fake")

    assert isinstance(create_app(data_dir=tmp_path).state.runner, FakeRunner)


def test_the_setting_tacc_uses_the_real_runner(tmp_path, monkeypatch):
    monkeypatch.setenv("JPILOT_RUNNER", "tacc")

    assert isinstance(create_app(data_dir=tmp_path).state.runner, TaccRunner)


def test_an_unknown_setting_stops_the_app_at_startup_rather_than_falling_back_to_fake(
        tmp_path, monkeypatch):
    # A typo must not quietly run canned answers while the user believes they are on TACC.
    monkeypatch.setenv("JPILOT_RUNNER", "TACC")

    with pytest.raises(ValueError, match="JPILOT_RUNNER"):
        create_app(data_dir=tmp_path)
