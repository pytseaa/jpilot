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

## Run (fake runner, no TACC needed)

```bash
.venv/Scripts/python.exe -m uvicorn --app-dir backend app.main:create_app --factory --port 8000
cd frontend && npm ci && npm run dev    # open http://localhost:5173
```

Tests: `.venv/Scripts/python.exe -m pytest backend`. Frontend typecheck: `cd frontend && npm run typecheck`.

The JSearch key is read from the `JSEARCH_API_KEY` environment variable and is never written to a file.
