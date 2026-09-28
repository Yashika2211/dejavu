"""An in-memory `MemoryBackend`: enough of Hindsight's behaviour to test DejaVu's own logic.

It stores what is retained (upserting by document_id, appending when asked), recalls by word
overlap, returns a configurable structured reflect answer, and lets operations stay pending for a
number of polls. Real Hindsight behaviour is verified by the spike and the live tests.
"""

import re
from collections import defaultdict
from typing import Any

from dejavu.memory.hindsight_adapter import (
    FileItem,
    MemoryHit,
    MemoryUnavailableError,
    ReflectAnswer,
    RetainItem,
)

_WORD = re.compile(r"[a-z0-9_]+")


class FakeMemory:
    def __init__(self, *, structured: dict[str, Any] | None = None, pending_polls: int = 0) -> None:
        self.config: dict[str, dict[str, Any]] = defaultdict(dict)
        self.directives: dict[str, set[str]] = defaultdict(set)
        self.models: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
        self.items: dict[str, list[RetainItem]] = defaultdict(list)
        self.files: dict[str, list[FileItem]] = defaultdict(list)
        self.ops: dict[str, int] = {}
        self.recalls: list[dict[str, Any]] = []
        self.reflects: list[dict[str, Any]] = []
        self.structured = structured
        self.pending_polls = pending_polls
        self.consolidations = 0
        self.down = False

    def _check(self) -> None:
        if self.down:
            raise MemoryUnavailableError("Hindsight is unreachable")

    def _op(self, op_id: str | None = None) -> str:
        op = op_id or f"op-{len(self.ops) + 1}"
        self.ops[op] = self.pending_polls
        return op

    async def configure_bank(self, bank_id: str, **config: Any) -> None:
        self._check()
        self.config[bank_id].update(config)

    async def directive_names(self, bank_id: str) -> set[str]:
        return set(self.directives[bank_id])

    async def add_directive(self, bank_id: str, name: str, content: str) -> None:
        self.directives[bank_id].add(name)

    async def retain(
        self, bank_id: str, items: list[RetainItem], *, operation_id: str | None = None
    ) -> list[str]:
        self._check()
        for item in items:
            existing = next((i for i in self.items[bank_id] if i.document_id == item.document_id), None)
            if existing is not None and item.update_mode == "append":
                existing.content += "\n" + item.content
            elif existing is not None:
                self.items[bank_id][self.items[bank_id].index(existing)] = item
            else:
                self.items[bank_id].append(item)
        return [self._op(operation_id)]

    async def retain_files(self, bank_id: str, files: list[FileItem]) -> list[str]:
        self._check()
        self.files[bank_id] += files
        return [self._op() for _ in files]

    def _search(self, bank_id: str, query: str, tags: list[str] | None, limit: int = 5) -> list[RetainItem]:
        words = set(_WORD.findall(query.lower()))
        pool = [i for i in self.items[bank_id] if not tags or not i.tags or set(tags) & set(i.tags)]
        scored = sorted(pool, key=lambda i: -len(words & set(_WORD.findall(i.content.lower()))))
        return [i for i in scored[:limit] if words & set(_WORD.findall(i.content.lower()))]

    async def recall(self, bank_id: str, query: str, **kwargs: Any) -> list[MemoryHit]:
        self._check()
        self.recalls.append({"query": query, **kwargs})
        kind = (kwargs.get("types") or ["world"])[0]
        return [
            MemoryHit(
                id=i.document_id,
                text=i.content[:200],
                type=kind,
                when=i.timestamp.isoformat(),
                document_id=i.document_id,
                tags=i.tags,
            )
            for i in self._search(bank_id, query, kwargs.get("tags"))
        ]

    async def reflect(self, bank_id: str, query: str, **kwargs: Any) -> ReflectAnswer:
        self._check()
        self.reflects.append({"query": query, **kwargs})
        based = await self.recall(bank_id, query, tags=kwargs.get("tags"))
        return ReflectAnswer(
            text="reflection",
            structured=self.structured,
            structured_error=None if self.structured else "could not produce structured output",
            based_on=based,
        )

    async def operation_status(self, bank_id: str, operation_id: str) -> str:
        remaining = self.ops.get(operation_id, 0)
        if remaining > 0:
            self.ops[operation_id] = remaining - 1
            return "pending"
        return "completed"

    async def consolidate(self, bank_id: str) -> str:
        self.consolidations += 1
        return self._op()

    async def stats(self, bank_id: str) -> dict[str, Any]:
        return {
            "pending_consolidation": 0,
            "pending_operations": 0,
            "total_observations": len(self.items[bank_id]),
        }

    async def mental_model_ids(self, bank_id: str) -> set[str]:
        return set(self.models[bank_id])

    async def create_mental_model(
        self,
        bank_id: str,
        model_id: str,
        name: str,
        source_query: str,
        tags: list[str],
        trigger: dict[str, Any],
    ) -> str | None:
        self.models[bank_id][model_id] = {
            "name": name,
            "source_query": source_query,
            "tags": tags,
            "trigger": trigger,
        }
        return self._op()

    async def clone_bank(self, source: str, target: str) -> str:
        self.items[target] = list(self.items[source])
        self.config[target] = dict(self.config[source])
        return self._op()

    async def delete_bank(self, bank_id: str) -> None:
        for store in (self.items, self.config, self.directives, self.models, self.files):
            store.pop(bank_id, None)
