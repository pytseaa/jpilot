"""The ingestion command, as the team runs it: what it prints, freezes and refuses. main() is the seam."""
from fake_jsearch import FakeJSearch, job
from samples import EXTRACTED, TODAY, jsearch_returning

from app.ingest import main
from app.runners.fake import FakeRunner
from app.runners.tacc import SubmissionFailed
from app.services.ingestion import ROLES


def test_the_run_prints_how_many_jobs_it_fetched_stored_and_dropped(tmp_path, capsys):
    jobs = [job("a"), job("b"), job("zh", job_description="\u8077" * 100)]
    runner = FakeRunner({"job-0": EXTRACTED, "job-1": EXTRACTED})

    code = main([], search=jsearch_returning(*jobs), runner=runner, data_dir=tmp_path, today=TODAY)

    assert code == 0
    assert capsys.readouterr().out == (
        "Jobs fetched: 3\nStored: 2\nAlready stored: 0\nDropped as mostly Chinese: 1\n"
        "Dropped with no description: 0\nFailed at extraction: 0\nFailed JSearch requests: 0\n")


def test_snapshot_writes_an_exact_copy_of_the_database_named_with_the_date(tmp_path, capsys):
    runner = FakeRunner({"job-0": EXTRACTED})

    main(["--snapshot"], search=jsearch_returning(job("a")), runner=runner, data_dir=tmp_path, today=TODAY)

    copy = tmp_path / "snapshots" / "jpilot-2026-11-14.db"
    assert copy.read_bytes() == (tmp_path / "jpilot.db").read_bytes()
    assert "jpilot-2026-11-14.db" in capsys.readouterr().out


def test_a_run_without_the_snapshot_flag_freezes_nothing(tmp_path):
    main([], search=jsearch_returning(job("a")), runner=FakeRunner({"job-0": EXTRACTED}),
         data_dir=tmp_path, today=TODAY)

    assert not (tmp_path / "snapshots").exists()


def test_a_second_snapshot_on_the_same_day_is_refused_before_any_request_and_the_first_stays(tmp_path, capsys):
    main(["--snapshot"], search=jsearch_returning(job("a")), runner=FakeRunner({"job-0": EXTRACTED}),
         data_dir=tmp_path, today=TODAY)
    frozen = (tmp_path / "snapshots" / "jpilot-2026-11-14.db").read_bytes()
    capsys.readouterr()
    second = jsearch_returning(job("b"))

    code = main(["--snapshot"], search=second, runner=FakeRunner({"job-0": EXTRACTED}),
                data_dir=tmp_path, today=TODAY)

    assert code == 1 and second.calls == []
    assert "already exists" in capsys.readouterr().err
    assert (tmp_path / "snapshots" / "jpilot-2026-11-14.db").read_bytes() == frozen


def test_a_missing_jsearch_key_stops_the_command_with_a_clear_message(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("JSEARCH_API_KEY", raising=False)

    code = main([], runner=FakeRunner({}), data_dir=tmp_path, today=TODAY)

    assert code == 2
    assert "JSEARCH_API_KEY" in capsys.readouterr().err


def test_an_unreachable_qwen_service_prints_its_message_and_makes_no_snapshot(tmp_path, capsys):
    def broken(prompts):
        raise SubmissionFailed("The Qwen service could not be reached. Please restart it.")

    code = main(["--snapshot"], search=jsearch_returning(job("a")), runner=broken,
                data_dir=tmp_path, today=TODAY)

    assert code == 1
    assert "restart" in capsys.readouterr().err
    assert not (tmp_path / "snapshots").exists()


def test_a_snapshot_does_not_change_when_a_later_run_adds_jobs(tmp_path):
    main(["--snapshot"], search=jsearch_returning(job("a")), runner=FakeRunner({"job-0": EXTRACTED}),
         data_dir=tmp_path, today="2026-11-14")
    frozen = (tmp_path / "snapshots" / "jpilot-2026-11-14.db").read_bytes()

    main([], search=jsearch_returning(job("b")), runner=FakeRunner({"job-0": EXTRACTED}),
         data_dir=tmp_path, today="2026-11-20")

    assert (tmp_path / "snapshots" / "jpilot-2026-11-14.db").read_bytes() == frozen
    assert (tmp_path / "jpilot.db").read_bytes() != frozen


def test_a_run_that_got_no_jobs_because_requests_failed_exits_with_an_error_and_freezes_nothing(tmp_path, capsys):
    every_request_fails = FakeJSearch(failing=[(f"{role} in Hong Kong", None) for role in ROLES])

    code = main(["--snapshot"], search=every_request_fails, runner=FakeRunner({}),
                data_dir=tmp_path, today=TODAY)

    assert code == 1
    assert "JSearch" in capsys.readouterr().err
    assert not (tmp_path / "snapshots").exists()
