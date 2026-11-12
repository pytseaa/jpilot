from contextlib import asynccontextmanager, closing

from fastapi import FastAPI

from app import db
from app.routers import search_requests
from app.runners.fake import FakeRunner


def create_app(runner=None, data_dir=None):
    data_dir = data_dir or db.DEFAULT_DATA_DIR

    @asynccontextmanager
    async def lifespan(_):
        with closing(db.connect(data_dir)):
            yield

    app = FastAPI(title="JobPilot", lifespan=lifespan)
    app.state.runner = runner or FakeRunner()
    app.state.requests = {}
    app.include_router(search_requests.router)
    return app
