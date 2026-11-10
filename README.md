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

The JSearch key is read from the `JSEARCH_API_KEY` environment variable and is never written to a file.
