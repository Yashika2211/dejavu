"""The `api` fixture: the app with an in-memory store, the fake memory and a scripted model."""

from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest

from dejavu.api.main import create_app
from dejavu.api.services import Services
from dejavu.health import CheckResult
from dejavu.llm.toolcalling import ToolCaller
from dejavu.store.db import Store
from tests.api.harness import MODEL, Api
from tests.memory.fakememory import FakeMemory
from tests.memory.test_reader import BRIEF


@pytest.fixture
async def api(make_client, groq, settings, telemetry_root, tmp_path: Path) -> AsyncIterator[Api]:
    memory = FakeMemory(structured=BRIEF)
    client, _ = make_client()
    caller = ToolCaller(client, [MODEL])

    async def build_caller() -> ToolCaller:
        return caller

    async def checks() -> list[CheckResult]:
        return [
            CheckResult(name="groq", ok=True, detail="ok"),
            CheckResult(name="hindsight", ok=False, detail="down"),
        ]

    services = Services(
        settings.model_copy(update={"approval_timeout_s": 5.0}),
        Store("sqlite://"),
        memory,
        caller=build_caller,
        checks=checks,
        telemetry_root=telemetry_root,
        trace_dir=tmp_path / "runs",
        eval_dir=tmp_path / "eval",
    )
    app = create_app(services)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test", timeout=60) as http:
            yield Api(http, services, memory, groq)
