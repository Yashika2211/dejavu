"""Helpers for the API tests: the handle the `api` fixture yields, and an SSE body parser."""

import json
from dataclasses import dataclass
from typing import Any

import httpx

from dejavu.api.services import Services
from tests.llm.fakegroq import ScriptedGroq
from tests.memory.fakememory import FakeMemory

MODEL = "openai/gpt-oss-120b"


@dataclass
class Api:
    http: httpx.AsyncClient
    services: Services
    memory: FakeMemory
    groq: ScriptedGroq


def sse(text: str) -> list[tuple[str, dict[str, Any]]]:
    """(event type, data) for each message of a Server-Sent Events body, pings skipped."""
    out = []
    for block in text.replace("\r\n", "\n").split("\n\n"):
        fields = dict(
            line.split(": ", 1) for line in block.split("\n") if ": " in line and not line.startswith(":")
        )
        if "event" in fields and "data" in fields:
            out.append((fields["event"], json.loads(fields["data"])))
    return out
