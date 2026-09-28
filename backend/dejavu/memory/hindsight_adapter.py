"""Everything DejaVu asks of Hindsight, behind one small interface.

The high-level SDK does most of the work; the REST client covers what it lacks (operations,
consolidation, stats). Keeping every call here means the strategy, writer and reader never see
SDK types, degraded mode has a single home, and tests can swap in an in-memory fake with the same
methods (`MemoryBackend`).
"""

from datetime import datetime
from pathlib import Path
from typing import Any, Literal, Protocol

from hindsight_client import Hindsight
from pydantic import BaseModel, Field

from dejavu.config import Settings
from dejavu.memory.rest import HindsightRest

Budget = Literal["low", "mid", "high"]
TagsMatch = Literal["any", "all", "any_strict", "all_strict", "exact"]


class MemoryUnavailableError(Exception):
    """Hindsight could not be reached or refused the request; callers degrade to no memory."""


class RetainItem(BaseModel):
    """One document to retain, following the write-path conventions (spec 6.3, 6.4)."""

    content: str
    context: str
    timestamp: datetime
    document_id: str
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, str] = Field(default_factory=dict)
    entities: list[tuple[str, str]] = Field(default_factory=list)  # (text, type)
    observation_scopes: list[list[str]] | None = None
    update_mode: Literal["replace", "append"] | None = None

    def payload(self) -> dict[str, Any]:
        item: dict[str, Any] = {
            "content": self.content,
            "context": self.context,
            "timestamp": self.timestamp.isoformat(),
            "document_id": self.document_id,
            "tags": self.tags,
            "metadata": self.metadata,
        }
        if self.entities:
            item["entities"] = [{"text": text, "type": kind} for text, kind in self.entities]
        if self.observation_scopes:
            item["observation_scopes"] = self.observation_scopes
        if self.update_mode:
            item["update_mode"] = self.update_mode
        return item


class FileItem(BaseModel):
    """A file (PDF) to ingest through `retain_files`, which converts it to markdown server-side."""

    path: Path
    document_id: str
    context: str
    timestamp: datetime
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, str] = Field(default_factory=dict)


class MemoryHit(BaseModel):
    """A remembered fact or observation, as the rest of DejaVu sees it."""

    id: str | None = None
    text: str
    type: str | None = None
    when: str | None = None
    document_id: str | None = None
    context: str | None = None
    tags: list[str] = Field(default_factory=list)


class ReflectAnswer(BaseModel):
    text: str
    structured: dict[str, Any] | None = None
    structured_error: str | None = None
    based_on: list[MemoryHit] = Field(default_factory=list)


class MentalModelState(BaseModel):
    """A mental model's refresh bookkeeping."""

    id: str
    name: str = ""
    last_refreshed_at: datetime | None = None
    last_refresh_failed_at: datetime | None = None

    @property
    def refresh_paused(self) -> bool:
        """A failed refresh pauses automatic ones until a manual refresh succeeds."""
        failed, ok = self.last_refresh_failed_at, self.last_refreshed_at
        return failed is not None and (ok is None or failed > ok)


class MemoryBackend(Protocol):
    async def configure_bank(self, bank_id: str, **config: Any) -> None: ...

    async def directive_names(self, bank_id: str) -> set[str]: ...

    async def add_directive(self, bank_id: str, name: str, content: str) -> None: ...

    async def retain(
        self, bank_id: str, items: list[RetainItem], *, operation_id: str | None = None
    ) -> list[str]: ...

    async def retain_files(self, bank_id: str, files: list[FileItem]) -> list[str]: ...

    async def recall(
        self,
        bank_id: str,
        query: str,
        *,
        types: list[str] | None = None,
        tags: list[str] | None = None,
        tags_match: TagsMatch = "any",
        budget: Budget = "mid",
        max_tokens: int = 1500,
        query_timestamp: datetime | None = None,
        include_source_facts: bool = False,
    ) -> list[MemoryHit]: ...

    async def reflect(
        self,
        bank_id: str,
        query: str,
        *,
        budget: Budget = "mid",
        response_schema: dict[str, Any] | None = None,
        tags: list[str] | None = None,
        tags_match: TagsMatch = "any",
    ) -> ReflectAnswer: ...

    async def operation_status(self, bank_id: str, operation_id: str) -> str: ...

    async def consolidate(self, bank_id: str) -> str: ...

    async def stats(self, bank_id: str) -> dict[str, Any]: ...

    async def mental_models(self, bank_id: str) -> list[MentalModelState]: ...

    async def refresh_mental_model(self, bank_id: str, model_id: str) -> str | None: ...

    async def create_mental_model(
        self,
        bank_id: str,
        model_id: str,
        name: str,
        source_query: str,
        tags: list[str],
        trigger: dict[str, Any],
    ) -> str | None: ...

    async def clone_bank(self, source: str, target: str) -> str: ...

    async def delete_bank(self, bank_id: str) -> None: ...


def _dump(obj: Any) -> Any:
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    return obj


def _hit(raw: Any) -> MemoryHit:
    d = _dump(raw) or {}
    return MemoryHit(
        id=d.get("id"),
        text=d.get("text", ""),
        type=d.get("type") or d.get("fact_type"),
        when=d.get("occurred_start") or d.get("mentioned_at") or d.get("date"),
        document_id=d.get("document_id"),
        context=d.get("context"),
        tags=d.get("tags") or [],
    )


def _items(listing: Any) -> list[dict[str, Any]]:
    d = _dump(listing)
    if isinstance(d, dict):
        return list(d.get("items") or d.get("mental_models") or d.get("directives") or [])
    return list(d or [])


class HindsightMemory:
    """`MemoryBackend` over Hindsight Cloud (or a self-hosted server)."""

    def __init__(self, settings: Settings, *, timeout_s: float = 120.0) -> None:
        key = settings.hindsight_api_key.get_secret_value() if settings.hindsight_api_key else None
        self._sdk = Hindsight(base_url=settings.hindsight_base_url, api_key=key, timeout=timeout_s)
        self._rest = HindsightRest(settings.hindsight_base_url, key, timeout=timeout_s)

    async def aclose(self) -> None:
        await self._sdk.aclose()
        await self._rest.aclose()

    async def _call(self, coro: Any) -> Any:
        try:
            return await coro
        except Exception as exc:  # the SDK raises aiohttp and generated-client errors alike
            raise MemoryUnavailableError(f"{type(exc).__name__}: {exc}"[:500]) from exc

    async def configure_bank(self, bank_id: str, **config: Any) -> None:
        await self._call(self._sdk.acreate_bank(bank_id, name=bank_id))
        await self._call(self._sdk.aupdate_bank_config(bank_id, **config))

    async def directive_names(self, bank_id: str) -> set[str]:
        return {d.get("name", "") for d in _items(await self._call(self._sdk.alist_directives(bank_id)))}

    async def add_directive(self, bank_id: str, name: str, content: str) -> None:
        await self._call(self._sdk.acreate_directive(bank_id=bank_id, name=name, content=content))

    async def retain(
        self, bank_id: str, items: list[RetainItem], *, operation_id: str | None = None
    ) -> list[str]:
        resp = await self._call(
            self._sdk.aretain_batch(
                bank_id=bank_id,
                items=[i.payload() for i in items],
                retain_async=True,
                operation_id=operation_id,
            )
        )
        return [op for op in [resp.operation_id, *(resp.operation_ids or [])] if op]

    async def retain_files(self, bank_id: str, files: list[FileItem]) -> list[str]:
        meta = [
            {
                "document_id": f.document_id,
                "context": f.context,
                "tags": f.tags,
                "metadata": f.metadata,
                "timestamp": f.timestamp.isoformat(),
            }
            for f in files
        ]
        resp = await self._call(
            self._sdk.aretain_files(bank_id, [f.path for f in files], files_metadata=meta)
        )
        return list(resp.operation_ids)

    async def recall(
        self,
        bank_id: str,
        query: str,
        *,
        types: list[str] | None = None,
        tags: list[str] | None = None,
        tags_match: TagsMatch = "any",
        budget: Budget = "mid",
        max_tokens: int = 1500,
        query_timestamp: datetime | None = None,
        include_source_facts: bool = False,
    ) -> list[MemoryHit]:
        resp = await self._call(
            self._sdk.arecall(
                bank_id=bank_id,
                query=query,
                types=types,
                tags=tags,
                tags_match=tags_match,
                budget=budget,
                max_tokens=max_tokens,
                query_timestamp=query_timestamp.isoformat() if query_timestamp else None,
                include_source_facts=include_source_facts,
            )
        )
        return [_hit(r) for r in resp.results]

    async def reflect(
        self,
        bank_id: str,
        query: str,
        *,
        budget: Budget = "mid",
        response_schema: dict[str, Any] | None = None,
        tags: list[str] | None = None,
        tags_match: TagsMatch = "any",
    ) -> ReflectAnswer:
        resp = await self._call(
            self._sdk.areflect(
                bank_id=bank_id,
                query=query,
                budget=budget,
                response_schema=response_schema,
                tags=tags,
                tags_match=tags_match,
                include_facts=True,
            )
        )
        based = _dump(resp.based_on) or {}
        return ReflectAnswer(
            text=resp.text,
            structured=resp.structured_output,
            structured_error=resp.structured_output_error,
            based_on=[_hit(m) for m in based.get("memories", [])],
        )

    async def operation_status(self, bank_id: str, operation_id: str) -> str:
        return str((await self._call(self._rest.operation(bank_id, operation_id)))["status"])

    async def consolidate(self, bank_id: str) -> str:
        return str((await self._call(self._rest.consolidate(bank_id)))["operation_id"])

    async def stats(self, bank_id: str) -> dict[str, Any]:
        return dict(await self._call(self._rest.stats(bank_id)))

    async def mental_models(self, bank_id: str) -> list[MentalModelState]:
        listing = await self._call(self._sdk.alist_mental_models(bank_id, detail="metadata"))
        return [MentalModelState.model_validate(m) for m in _items(listing)]

    async def refresh_mental_model(self, bank_id: str, model_id: str) -> str | None:
        resp = _dump(await self._call(self._sdk.arefresh_mental_model(bank_id, model_id)))
        return resp.get("operation_id") if isinstance(resp, dict) else None

    async def create_mental_model(
        self,
        bank_id: str,
        model_id: str,
        name: str,
        source_query: str,
        tags: list[str],
        trigger: dict[str, Any],
    ) -> str | None:
        resp = _dump(
            await self._call(
                self._sdk.acreate_mental_model(
                    bank_id=bank_id,
                    id=model_id,
                    name=name,
                    source_query=source_query,
                    tags=tags or None,
                    trigger=trigger,
                )
            )
        )
        return resp.get("operation_id") if isinstance(resp, dict) else None

    async def clone_bank(self, source: str, target: str) -> str:
        return str(await self._call(self._sdk.aclone_bank(source, target)))

    async def delete_bank(self, bank_id: str) -> None:
        await self._call(self._sdk.adelete_bank(bank_id))
