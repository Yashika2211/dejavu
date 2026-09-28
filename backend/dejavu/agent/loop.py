"""The investigation loop: ReAct-style, one tool call per turn, shared by every strategy (spec 5.1).

The strategy's briefing is injected before the first call. Each turn the model picks one tool:
simulator tools run against the world and cost simulated minutes, `update_hypotheses` replaces the
board, `recall_memory` asks the strategy, `submit_diagnosis` ends the run and `page_human`
escalates. Tool output is sanitised and wrapped as untrusted before the model sees it; invalid
arguments go back to the model (twice per step) without costing a step. If the budget runs out the
model is asked for its best diagnosis; after a diagnosis its remediation plan is executed, approved
by a simulated human in the Gauntlet or by a real one in the UI.
"""

import json
import re
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass, field
from importlib import resources
from typing import Any, Literal

from pydantic import BaseModel, ValidationError

from dejavu.agent.context import ContextBuilder, Turn, board_text, wrap_output
from dejavu.agent.schemas import AgentStep, Diagnosis, Hypothesis, HypothesisBoard, RecallArgs
from dejavu.agent.tools import TOOLS, ToolResult, execute
from dejavu.agent.trace import Trace
from dejavu.llm.errors import ContextTooLongError, LLMError
from dejavu.llm.toolcalling import Call, Decision, ToolCaller, ToolSpec, tool_spec
from dejavu.security import sanitize
from dejavu.sim.clock import fmt_hm
from dejavu.sim.remediation import requires_approval
from dejavu.sim.world import IncidentWorld
from dejavu.strategies.base import IncidentContext, MemoryBriefing, MemoryStrategy
from dejavu.taxonomy import Remediation, RootCause

INCIDENT_REF = re.compile(r"\bINC-\d{4}\b")
Approver = Callable[[Remediation, str, dict[str, str]], Awaitable[bool]]


async def auto_approve(_action: Remediation, _target: str, _params: dict[str, str]) -> bool:
    """The Gauntlet's simulated human approves every action; consequences are scored."""
    return True


@dataclass
class LoopConfig:
    max_steps: int = 16
    sim_budget_min: float = 90.0
    max_invalid_per_step: int = 2
    context_tokens: int = 6000
    verbatim_steps: int = 4
    execute_plan: bool = True


class RunResult(BaseModel):
    run_id: str
    incident_id: str
    strategy: str
    ended: Literal["diagnosed", "escalated", "budget", "error"]
    diagnosis: Diagnosis | None
    ttd_min: float | None
    steps: list[AgentStep]
    plan_steps: list[AgentStep]
    hypotheses: list[Hypothesis]
    briefing: MemoryBriefing | None
    llm_calls: list[dict[str, Any]]
    wall_clock_s: float
    notes: list[str]


def system_prompt(config: LoopConfig) -> str:
    template = resources.files("dejavu.agent").joinpath("prompts/system.md").read_text()
    return (
        template.replace("{max_steps}", str(config.max_steps))
        .replace("{budget_min}", f"{config.sim_budget_min:g}")
        .replace("{categories}", ", ".join(c.value for c in RootCause))
        .replace("{actions}", ", ".join(a.value for a in Remediation))
    )


def _words(text: str, limit: int = 25) -> str:
    words = text.split()
    return " ".join(words[:limit]) + ("…" if len(words) > limit else "")


def _matches_first_check(call: Call, briefing: MemoryBriefing | None) -> bool:
    """A step follows the briefing when the specific thing it probes is named in a suggested check."""
    if briefing is None:
        return False
    probes = [
        str(call.args[k]).lower()
        for k in ("metric", "query", "operation", "topic", "name")
        if call.args.get(k)
    ]
    return any(len(p) > 3 and p in check.lower() for p in probes for check in briefing.first_checks)


class Investigator:
    """Runs one investigation of one incident for one strategy."""

    def __init__(
        self,
        caller: ToolCaller,
        strategy: MemoryStrategy,
        *,
        config: LoopConfig | None = None,
        trace: Trace | None = None,
        approver: Approver = auto_approve,
        run_id: str | None = None,
    ) -> None:
        self.caller = caller
        self.strategy = strategy
        self.config = config or LoopConfig()
        self.run_id = run_id or f"run-{uuid.uuid4().hex[:10]}"
        self.trace = trace or Trace(self.run_id, directory=None)
        self.approver = approver

    # tools the model can call ----------------------------------------------------------------------

    def tool_specs(self) -> list[ToolSpec]:
        specs = [tool_spec(t.name, t.description, t.args) for t in TOOLS.values()]
        specs.append(
            tool_spec(
                "update_hypotheses",
                "Record the full current hypothesis board, most likely first. No time cost.",
                HypothesisBoard,
            )
        )
        if self.strategy.has_memory:
            specs.append(
                tool_spec(
                    "recall_memory",
                    "Search memory of past incidents, postmortems and runbooks. 0.5 minutes.",
                    RecallArgs,
                )
            )
        specs.append(
            tool_spec(
                "submit_diagnosis",
                "Submit the root cause and the remediation plan. Ends the investigation.",
                Diagnosis,
            )
        )
        return specs

    # the loop ----------------------------------------------------------------------------------------

    async def run(self, world: IncidentWorld) -> RunResult:
        started = time.perf_counter()
        calls_before = len(self.caller.client.calls)
        ctx = IncidentContext.from_alert(
            world.scenario.incident_id, world.store.alert, world.scenario.alert_at
        )
        self.trace.emit(
            "run_started", 0, incident_id=ctx.incident_id, strategy=self.strategy.name, alert=ctx.summary
        )

        briefing: MemoryBriefing | None = None
        try:
            briefing = await self.strategy.brief(ctx)
        except Exception as exc:  # memory must never take the investigation down with it
            self.trace.emit("degraded", 0, component="memory", error=f"{type(exc).__name__}: {exc}"[:300])
        if briefing:
            self.trace.emit("briefing", 0, source=briefing.source, text=briefing.text, data=briefing.data)

        specs = self.tool_specs()
        builder = ContextBuilder(
            system_prompt(self.config),
            self._header(ctx, briefing),
            tools=[s.as_openai() for s in specs],
            budget_tokens=self.config.context_tokens,
            verbatim=self.config.verbatim_steps,
        )
        state = _RunState()

        while state.ended is None:
            if (
                len(state.steps) >= self.config.max_steps
                or world.clock.elapsed_min >= self.config.sim_budget_min
            ):
                state.ended = "budget"
                break
            decision = await self._decide(builder, state, specs)
            if decision is None:
                state.ended = "error"
                break
            state.notes += decision.notes
            for call in decision.calls:
                await self._handle(call, decision, world, ctx, briefing, state)
                if state.ended is not None:
                    break

        if state.diagnosis is None and state.ended in ("budget", "error"):
            state.diagnosis = await self._final_diagnosis(builder, state, ctx, specs, world)
        plan_steps: list[AgentStep] = []
        if state.diagnosis is not None:
            self.trace.emit("diagnosis", world.clock.elapsed_min, **state.diagnosis.model_dump(mode="json"))
            await self.strategy.on_diagnosis(state.diagnosis, ctx)
            if self.config.execute_plan:
                plan_steps = await self._execute_plan(world, state.diagnosis, len(state.steps))
        if world.resolved_at_min is not None:
            self.trace.emit(
                "resolved", world.resolved_at_min, inr_at_risk=round(world.inr_at_risk(world.resolved_at_min))
            )

        return RunResult(
            run_id=self.run_id,
            incident_id=ctx.incident_id,
            strategy=self.strategy.name,
            ended=state.ended or "error",
            diagnosis=state.diagnosis,
            ttd_min=state.ttd,
            steps=state.steps,
            plan_steps=plan_steps,
            hypotheses=state.board,
            briefing=briefing,
            llm_calls=[asdict(c) for c in self.caller.client.calls[calls_before:]],
            wall_clock_s=round(time.perf_counter() - started, 2),
            notes=state.notes,
        )

    def _header(self, ctx: IncidentContext, briefing: MemoryBriefing | None) -> str:
        parts = [
            f"Incident {ctx.incident_id}. It is {fmt_hm(ctx.alert_at)} IST on {ctx.alert_at:%a %d %b %Y}.",
            f"Alert: {ctx.summary} (service {ctx.service}).",
        ]
        if briefing:
            parts.append(
                "=== MEMORY BRIEFING (priors from past incidents; verify before acting) ===\n"
                f"{briefing.text}\n=== END MEMORY BRIEFING ==="
            )
        parts.append("Investigate with the tools. One tool call per turn.")
        return "\n\n".join(parts)

    async def _decide(
        self, builder: ContextBuilder, state: "_RunState", specs: list[ToolSpec]
    ) -> Decision | None:
        for verbatim in range(self.config.verbatim_steps, -1, -1):
            messages = builder.fit(state.turns, state.board, max_verbatim=verbatim)
            try:
                return await self.caller.decide(messages, specs)
            except ContextTooLongError:
                state.notes.append(f"context too long with {verbatim} verbatim steps; trimming")
            except LLMError as exc:
                self.trace.emit("error", state.now, error=f"{type(exc).__name__}: {exc}"[:500])
                return None
        return None

    async def _handle(
        self,
        call: Call,
        decision: Decision,
        world: IncidentWorld,
        ctx: IncidentContext,
        briefing: MemoryBriefing | None,
        state: "_RunState",
    ) -> None:
        args = dict(call.args)
        rationale = _words(str(args.pop("rationale", "")))
        at = world.clock.elapsed_min
        self.trace.emit("tool_call", at, tool=call.name, args=args, rationale=rationale)

        result = await self._dispatch(call.name, args, world, ctx, state)
        if result.invalid_args:
            state.invalid_streak += 1
        output = sanitize(result.output)
        cited = sorted(set(INCIDENT_REF.findall(rationale)))
        moment = bool(cited) or call.name == "recall_memory" or _matches_first_check(call, briefing)
        counts = not (result.invalid_args and state.invalid_streak <= self.config.max_invalid_per_step)
        if not result.invalid_args:
            state.invalid_streak = 0
        step = AgentStep(
            index=len(state.steps) + 1,
            tool=call.name,
            args=args,
            rationale=rationale,
            ok=result.ok,
            output=output,
            sim_minutes=result.sim_minutes,
            at_min=round(at, 2),
            memory_moment=moment and result.ok,
            cited_incidents=cited,
            model=decision.model,
            repaired=decision.repaired,
            outcome=result.data.get("outcome"),
        )
        if counts:
            state.steps.append(step)
            await self.strategy.on_step(step, ctx)
        state.turns.append(
            Turn(
                step=step,
                assistant={
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": call.id,
                            "type": "function",
                            "function": {"name": call.name, "arguments": _json(call.args)},
                        }
                    ],
                },
                tool={"role": "tool", "tool_call_id": call.id, "content": wrap_output(call.name, output)},
            )
        )
        self.trace.emit(
            "tool_result",
            world.clock.elapsed_min,
            tool=call.name,
            ok=result.ok,
            summary=output.splitlines()[0][:200] if output else "",
            output=output,
            sim_minutes=result.sim_minutes,
        )
        if step.memory_moment:
            self.trace.emit(
                "memory_moment", at, step=step.index, tool=call.name, cited=cited, rationale=rationale
            )
        self.trace.emit(
            "clock", world.clock.elapsed_min, inr_at_risk=round(world.inr_at_risk(world.clock.elapsed_min))
        )
        state.now = world.clock.elapsed_min
        if result.ends_run and call.name == "page_human":
            state.ended, state.ttd = "escalated", world.clock.elapsed_min

    async def _dispatch(
        self, name: str, args: dict[str, Any], world: IncidentWorld, ctx: IncidentContext, state: "_RunState"
    ) -> ToolResult:
        if name == "update_hypotheses":
            board = _validate(HypothesisBoard, args, name)
            if isinstance(board, ToolResult):
                return board
            state.board = board.hypotheses
            self.trace.emit(
                "hypotheses",
                world.clock.elapsed_min,
                hypotheses=[h.model_dump(mode="json") for h in state.board],
            )
            return ToolResult(
                tool=name, output="Hypothesis board updated:\n" + board_text(state.board), sim_minutes=0
            )
        if name == "recall_memory" and self.strategy.has_memory:
            query = _validate(RecallArgs, args, name)
            if isinstance(query, ToolResult):
                return query
            world.clock.advance(0.5)
            try:
                text = await self.strategy.lookup(query.query, ctx)
            except Exception as exc:
                self.trace.emit("degraded", world.clock.elapsed_min, component="memory", error=str(exc)[:300])
                text = "Memory is unavailable right now; continue with live telemetry."
            return ToolResult(tool=name, output=text, sim_minutes=0.5, clock_advanced=True)
        if name == "submit_diagnosis":
            diagnosis = _validate(Diagnosis, args, name)
            if isinstance(diagnosis, ToolResult):
                return diagnosis
            state.diagnosis, state.ended, state.ttd = diagnosis, "diagnosed", world.clock.elapsed_min
            return ToolResult(tool=name, output="Diagnosis recorded.", sim_minutes=0)
        if name == "run_remediation":
            return await self._remediate(args, world)
        return execute(world, name, args)

    async def _remediate(self, args: dict[str, Any], world: IncidentWorld) -> ToolResult:
        try:
            action = Remediation(args.get("action"))
        except ValueError:
            return execute(world, "run_remediation", args)  # let the tool report the validation error
        target = str(args.get("target", ""))
        params = {str(k): str(v) for k, v in (args.get("params") or {}).items()}
        self.trace.emit(
            "remediation_proposed",
            world.clock.elapsed_min,
            action=action.value,
            target=target,
            params=params,
            needs_approval=requires_approval(world.topology, target),
        )
        if not await self.approver(action, target, params):
            return ToolResult(
                tool="run_remediation",
                output=f"{action.value} {target} was declined by the on-call human.",
                sim_minutes=0,
            )
        before = len(world.interventions)
        result = execute(world, "run_remediation", args)
        if len(world.interventions) > before:
            iv = world.interventions[-1]
            self.trace.emit(
                "remediation_applied",
                iv.completes_at,
                action=iv.action.value,
                target=iv.target,
                outcome=iv.kind.value,
            )
        return result

    async def _final_diagnosis(
        self,
        builder: ContextBuilder,
        state: "_RunState",
        ctx: IncidentContext,
        specs: list[ToolSpec],
        world: IncidentWorld,
    ) -> Diagnosis:
        submit = [s for s in specs if s.name == "submit_diagnosis"]
        messages = builder.fit(state.turns, state.board)
        messages.append(
            {
                "role": "user",
                "content": "The budget is exhausted. Call submit_diagnosis now with your best diagnosis and plan.",
            }
        )
        try:
            decision = await self.caller.decide(messages, submit, purpose="final-diagnosis")
            diagnosis = Diagnosis.model_validate(
                {k: v for k, v in decision.calls[0].args.items() if k != "rationale"}
            )
        except (LLMError, ValidationError, IndexError):
            diagnosis = Diagnosis(
                root_cause_category=RootCause.NOVEL,
                culprit_service=ctx.service,
                summary="No diagnosis within the budget.",
                confidence=0.0,
            )
        state.ttd = world.clock.elapsed_min
        return diagnosis

    async def _execute_plan(self, world: IncidentWorld, diagnosis: Diagnosis, offset: int) -> list[AgentStep]:
        steps = []
        for planned in diagnosis.remediation_plan:
            if world.resolved_at_min is not None:
                break
            at = world.clock.elapsed_min
            args = {"action": planned.action.value, "target": planned.target, "params": planned.params}
            result = await self._remediate(args, world)
            steps.append(
                AgentStep(
                    index=offset + len(steps) + 1,
                    tool="run_remediation",
                    args=args,
                    rationale=_words(planned.rationale),
                    ok=result.ok,
                    output=result.output,
                    sim_minutes=result.sim_minutes,
                    at_min=round(at, 2),
                    outcome=result.data.get("outcome"),
                )
            )
        return steps


@dataclass
class _RunState:
    steps: list[AgentStep] = field(default_factory=list)
    turns: list[Turn] = field(default_factory=list)
    board: list[Hypothesis] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    diagnosis: Diagnosis | None = None
    ended: Literal["diagnosed", "escalated", "budget", "error"] | None = None
    ttd: float | None = None
    now: float = 0.0
    invalid_streak: int = 0


def _validate[M: BaseModel](model: type[M], args: dict[str, Any], tool: str) -> M | ToolResult:
    try:
        return model.model_validate(args)
    except ValidationError as exc:
        problems = "; ".join(f"{'.'.join(map(str, e['loc'])) or 'args'}: {e['msg']}" for e in exc.errors())
        return ToolResult(
            tool=tool,
            ok=False,
            invalid_args=True,
            sim_minutes=0.0,
            output=f"invalid arguments for {tool}: {problems}",
        )


def _json(args: dict[str, Any]) -> str:
    return json.dumps(args)
