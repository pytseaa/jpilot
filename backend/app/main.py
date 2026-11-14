import os
from contextlib import asynccontextmanager, closing

from fastapi import FastAPI

from app import db
from app.routers import search_requests
from app.runners.fake import FakeRunner
from app.runners.tacc import TaccRunner


def _default_runner():
    # Set JPILOT_RUNNER=tacc to submit to TACC. Anything else is refused, so a typo cannot
    # quietly run the canned answers while the user believes they are on TACC.
    setting = os.environ.get("JPILOT_RUNNER", "tacc")
    if setting == "fake":
        return FakeRunner()
    if setting == "tacc":
        return TaccRunner()
    raise ValueError(f"JPILOT_RUNNER must be 'fake' or 'tacc', not {setting!r}")


def create_app(runner=None, data_dir=None):
    data_dir = data_dir or db.DEFAULT_DATA_DIR

    @asynccontextmanager
    async def lifespan(_):
        with closing(db.connect(data_dir)):
            yield

    app = FastAPI(title="JobPilot", lifespan=lifespan)
    app.state.runner = runner or _default_runner()
    app.state.requests = {}
    app.include_router(search_requests.router)
    return app
