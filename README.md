# CSIT6000V
CSIT6000V Course Project Repository

## Layout

```text
backend/                   FastAPI app: routers, schemas, models, and one service per pipeline stage
backend/tacc_qwen_client/  the program the backend submits to TACC (standard library only)
frontend/                  React + TypeScript
tacc_qwen_serve/           job that starts the Qwen service; started by hand before use
```

## Setup

```bash
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r backend/requirements.txt   # Windows
.venv/bin/python -m pip install -r backend/requirements.txt            # macOS / Linux
```

## Run

The backend uses TACC by default, so a run needs the Qwen service (see below). To run without TACC, set `JPILOT_RUNNER=fake`.

```bash
JPILOT_RUNNER=fake .venv/Scripts/python.exe -m uvicorn --app-dir backend app.main:create_app --factory --port 8000
cd frontend && npm ci && npm run dev    # open http://localhost:5173
```

### Run with TACC and real Qwen (the default)

`tcloud` runs on Linux, so run the backend in WSL (Ubuntu) for this. The tests never need it.

1. Start the Qwen service by hand from `tacc_qwen_serve/` with `tcloud submit`, and wait for `Application startup complete` in its log.
2. Put the `SERVICE_BASE_URL=` address from that log into `backend/tacc_qwen_client/server-url.txt`, as `http://<node>:8000/v1`. Keep `/v1`.
3. Start the backend. `JPILOT_RUNNER` is unset, so it uses TACC:

```bash
.venv/bin/python -m uvicorn --app-dir backend app.main:create_app --factory --port 8000
```

`JPILOT_RUNNER` accepts only `tacc` (the default) or `fake`. Any other value stops the app at startup.

Tests: `.venv/Scripts/python.exe -m pytest backend`. Frontend typecheck: `cd frontend && npm run typecheck`.

The JSearch key is read from the `JSEARCH_API_KEY` environment variable and is never written to a file.
