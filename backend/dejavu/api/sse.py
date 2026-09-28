"""Server-Sent Events for runs and races (spec 10).

Each message is one trace event: `event:` is its type, `id:` identifies it within the stream, and
the data carries the run id and, in a race, the lane. A stream ends with an `end` event so the
browser's EventSource closes instead of reconnecting.
"""

import asyncio
import json
from collections.abc import AsyncIterator

from sse_starlette import EventSourceResponse, ServerSentEvent

from dejavu.agent.trace import TraceEvent
from dejavu.api.live import LiveRun

PING_S = 15


def message(run: LiveRun, event: TraceEvent, lane: str | None = None) -> ServerSentEvent:
    payload = {"run_id": run.id, "lane": lane, **event.model_dump(mode="json")}
    event_id = f"{lane}:{event.seq}" if lane else str(event.seq)
    return ServerSentEvent(data=json.dumps(payload), event=event.type, id=event_id)


async def run_messages(run: LiveRun) -> AsyncIterator[ServerSentEvent]:
    async for event in run.events():
        yield message(run, event)
    yield ServerSentEvent(data=json.dumps({"run_id": run.id}), event="end")


async def race_messages(lanes: dict[str, LiveRun]) -> AsyncIterator[ServerSentEvent]:
    """Both lanes' events, interleaved as they happen, each tagged with its lane."""
    queue: asyncio.Queue[tuple[str, TraceEvent | None]] = asyncio.Queue()

    async def pump(lane: str, run: LiveRun) -> None:
        try:
            async for event in run.events():
                await queue.put((lane, event))
        finally:
            await queue.put((lane, None))

    tasks = [asyncio.create_task(pump(lane, run)) for lane, run in lanes.items()]
    open_lanes = len(tasks)
    try:
        while open_lanes:
            lane, event = await queue.get()
            if event is None:
                open_lanes -= 1
                continue
            yield message(lanes[lane], event, lane)
        yield ServerSentEvent(data=json.dumps({"lanes": {k: r.id for k, r in lanes.items()}}), event="end")
    finally:
        for task in tasks:
            task.cancel()


def stream(messages: AsyncIterator[ServerSentEvent]) -> EventSourceResponse:
    return EventSourceResponse(messages, ping=PING_S, headers={"Cache-Control": "no-store"})
