# TACC probe

One small TACC submission that measures what every JobPilot submission will cost. It runs on 1 CPU for about a minute, needs no GPU and no Qwen service, and sends no CV text.

## Run it

In WSL (Ubuntu), from the repo root:

```bash
bash eval/tacc_probe/probe.sh
```

Run it 3 times, at different times of day, because queue wait changes with load. A run lasts the queue wait plus about a minute of job time. The job asks for 1 CPU and at most 5 minutes, so it uses very little quota. The script gives up polling after 15 minutes (`MAX_WAIT`); the job itself is not cancelled, so check `tcloud ps` if it stops early.

## What it does

1. Submits `client/` with `tcloud submit` and times the call.
2. Polls `tcloud ps -j <job>` every 5 seconds and logs each change of state.
3. Once the job is running, reads the log with `tcloud cat` to see whether a running job's log is visible.
4. Downloads the result file and the log, then writes `out/<timestamp>/summary.json`.

## What to record

Copy these fields from `summary.json` for each run.

| Field | Answers | Decides |
|---|---|---|
| `queue_wait_seconds` | Time from the end of `tcloud submit` to the job running | The latency budget. A request makes 2 to 4 submissions, so multiply |
| `tcloud_submit_seconds` | SDK overhead of one submit | Same |
| `saw_pending_state` | Whether `ps` lists a waiting job | Whether the progress view can say "waiting for a worker" |
| `cat_showed_log_while_running` | Whether `tcloud cat` shows a log while the job runs | Whether the page can show "8 of 20 jobs checked" or only the stage |
| `input_file_reached_worker` | Whether a file placed in the client folder arrives on the worker | The plan to send prompts as files |
| `result_downloaded`, `log_downloaded` | Whether the result and log come back by `tcloud download` | The plan to fetch answers as one JSON file |
| `job_could_delete_userdir_file` | Whether a job can delete a file in USERDIR | The CV-file deletion rule (Q23) |
| `userdir_file_listed_after_job` | Whether that file is gone when seen from your PC | Same |
| `workdir_siblings_of_ours` | Whether old job folders pile up beside this one | Whether TACC cleans job folders |

Also write down the time of day, and anything odd in `submit.txt` (the exact text `tcloud submit` prints), because the script reads the job number from it.

## Limits

- `queue_wait_seconds` is from a CPU job. A service restart is slower and is not measured here: your 2026-11-09 service log (job 28507) shows about 3 min 40 s from the first server log line to the server starting to listen. Queue wait before that line is not in the log.
- `workdir_siblings_of_ours` has not run on TACC. If it reports an error, ignore that field.
- The first 3 real runs (2026-11-10, jobs 28538 to 28540) failed to read the job number, because `tcloud submit` writes NUL bytes into its output. The script now strips them. The rerun (job 28542) worked on TACC, and it showed that `tcloud cat` returns the running log.
- `tcloud ps -j <id>` prints an error once a job has finished. The script treats that as "job gone".
