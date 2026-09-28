"""The API app (spec 10).

    uv run uvicorn dejavu.api.main:app --port 8000      # or: make api

Memory failures answer 503 with "Memory offline: running without memory", which the war room
shows as a banner; investigations themselves degrade to no memory instead of failing.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from dejavu import __version__
from dejavu.api.routes import demo, evals, health, incidents, memory, races
from dejavu.api.services import Services, UnknownStrategyError
from dejavu.config import get_settings
from dejavu.memory.hindsight_adapter import MemoryUnavailableError

log = structlog.get_logger(__name__)
MEMORY_OFFLINE = "Memory offline: running without memory"


def create_app(services: Services | None = None) -> FastAPI:
    settings = services.settings if services else get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        svc = services or Services.from_settings(settings)
        interrupted = svc.store.interrupt_running()
        if interrupted:
            log.warning("runs interrupted by a restart", count=interrupted)
        app.state.services = svc
        try:
            yield
        finally:
            await svc.aclose()

    app = FastAPI(title="DejaVu API", version=__version__, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[f"http://localhost:{settings.web_port}", f"http://127.0.0.1:{settings.web_port}"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(MemoryUnavailableError)
    async def memory_offline(_request: Request, exc: MemoryUnavailableError) -> JSONResponse:
        log.warning("memory unavailable", error=str(exc)[:300])
        return JSONResponse({"detail": MEMORY_OFFLINE}, status_code=503)

    @app.exception_handler(UnknownStrategyError)
    async def unknown_strategy(_request: Request, exc: UnknownStrategyError) -> JSONResponse:
        return JSONResponse({"detail": f"unknown strategy {exc}"}, status_code=422)

    for module in (health, incidents, races, memory, evals, demo):
        app.include_router(module.router)
    app.include_router(memory.ask_router)
    return app


app = create_app()
