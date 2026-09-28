"""Everything the routes share: settings, app state, memory, the model chain and the live runs."""

import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path

from dejavu.api.live import API_RUNS_DIR, RunManager
from dejavu.config import Settings
from dejavu.eval.report import EVAL_DIR
from dejavu.health import CheckResult, run_checks
from dejavu.llm.toolcalling import ToolCaller
from dejavu.memory.hindsight_adapter import HindsightMemory, MemoryBackend
from dejavu.runner import build_caller
from dejavu.sim.telemetry import INCIDENTS_DIR
from dejavu.store.db import Store
from dejavu.strategies.amnesiac import Amnesiac
from dejavu.strategies.base import MemoryStrategy
from dejavu.strategies.dejavu import DejaVu
from dejavu.strategies.rag import NaiveRAG

STRATEGY_LABELS = ("dejavu", "amnesiac", "rag", "day1")


class UnknownStrategyError(ValueError):
    """Not one of STRATEGY_LABELS."""


class Services:
    def __init__(
        self,
        settings: Settings,
        store: Store,
        memory: MemoryBackend,
        *,
        caller: Callable[[], Awaitable[ToolCaller]] | None = None,
        checks: Callable[[], Awaitable[list[CheckResult]]] | None = None,
        telemetry_root: Path = INCIDENTS_DIR,
        trace_dir: Path = API_RUNS_DIR,
        eval_dir: Path = EVAL_DIR,
    ) -> None:
        self.settings = settings
        self.eval_dir = eval_dir
        self.store = store
        self.memory = memory
        self._build_caller = caller or (lambda: build_caller(settings))
        self._checks = checks or (lambda: run_checks(settings))
        self._caller: ToolCaller | None = None
        self._caller_lock = asyncio.Lock()
        self.runs = RunManager(
            store,
            self.caller,
            approval_timeout_s=settings.approval_timeout_s,
            trace_dir=trace_dir,
            telemetry_root=telemetry_root,
        )

    @classmethod
    def from_settings(cls, settings: Settings) -> "Services":
        return cls(settings, Store(), HindsightMemory(settings))

    async def caller(self) -> ToolCaller:
        """The model chain, resolved on first use so the API starts even when Groq is down."""
        async with self._caller_lock:
            if self._caller is None:
                self._caller = await self._build_caller()
            return self._caller

    async def checks(self) -> list[CheckResult]:
        return await self._checks()

    def bank_for(self, label: str) -> str | None:
        return {
            "dejavu": self.settings.dejavu_bank_live,
            "day1": self.settings.dejavu_bank_day1,
            "rag": self.settings.dejavu_bank_rag,
        }.get(label)

    def strategy(self, label: str) -> MemoryStrategy:
        """`day1` is DejaVu reading the Day-0-only snapshot; `dejavu` reads the live bank."""
        if label == "amnesiac":
            return Amnesiac()
        bank = self.bank_for(label)
        if bank is None:
            raise UnknownStrategyError(label)
        return NaiveRAG(self.memory, bank) if label == "rag" else DejaVu(self.memory, bank)

    async def aclose(self) -> None:
        await self.runs.aclose()
        aclose = getattr(self.memory, "aclose", None)
        if aclose is not None:
            await aclose()
