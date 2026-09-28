"""Reports from a Gauntlet run (spec 7.4), generated only from its `results.jsonl` and
`growth.jsonl`, never written by hand.

Every run directory gets `summary.json`, chart-ready `chart_data.json` and `charts/*.png`. With
`--publish`, `docs/EVAL_RESULTS.md` is rewritten from that run and its charts are copied to
`docs/eval/`.

    uv run python -m dejavu.eval.report                               # the latest run
    uv run python -m dejavu.eval.report --run-id g42-20260928-101500 --publish
"""

import argparse
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from matplotlib.figure import Figure
from matplotlib.patches import Patch

from dejavu.config import REPO_ROOT
from dejavu.eval.metrics import KINDS, Row, compare, learning_curve, summarize
from dejavu.money import inr_words
from dejavu.sim.migrations import MIGRATIONS

EVAL_DIR = REPO_ROOT / "data" / "eval"
DOCS_DIR = REPO_ROOT / "docs"
ORDER = ("amnesiac", "rag", "dejavu")
COLORS = {"amnesiac": "#8b93a7", "rag": "#f79009", "dejavu": "#8b5cf6"}
CHART_TITLES = {
    "mttr": "MTTR per incident",
    "accuracy": "Cumulative accuracy",
    "steps": "Useful and wasted tool calls",
    "cost": "LLM cost per incident",
    "memory_growth": "Memory growth",
}
GROWTH_KEYS = {
    "total_nodes": "memory units",
    "total_observations": "observations",
    "total_entities": "entities",
    "total_documents": "documents",
}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def latest_run(eval_dir: Path = EVAL_DIR) -> Path | None:
    runs = sorted(eval_dir.glob("*/run.json"), key=lambda p: p.stat().st_mtime)
    return runs[-1].parent if runs else None


def _strategies(run: dict[str, Any], rows: list[Row]) -> list[str]:
    present = set(run.get("strategies", [])) | {r["strategy"] for r in rows}
    return [s for s in ORDER if s in present] + sorted(present - set(ORDER))


def _incidents(rows: list[Row]) -> list[dict[str, Any]]:
    seen: dict[int, dict[str, Any]] = {}
    for r in rows:
        seen.setdefault(
            r["n"],
            {
                "n": r["n"],
                "incident_id": r["incident_id"],
                "archetype": r["archetype"],
                "kind": r["kind"],
                "after_migration": r["after_migration"],
                "alert_at": r["alert_at"],
            },
        )
    return [seen[n] for n in sorted(seen)]


def _migration_marks(incidents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Where each migration falls between incidents on the x axis."""
    marks = []
    for m in MIGRATIONS:
        before = [i["n"] for i in incidents if datetime.fromisoformat(i["alert_at"]) < m.at]
        after = [i["n"] for i in incidents if datetime.fromisoformat(i["alert_at"]) >= m.at]
        if before and after:
            marks.append({"id": m.id, "at": m.at.isoformat(), "x": max(before) + 0.5, "summary": m.summary})
    return marks


def build_summary(run: dict[str, Any], rows: list[Row]) -> dict[str, Any]:
    strategies = _strategies(run, rows)
    planned = run.get("n", 0)
    done = {s: sum(r["strategy"] == s for r in rows) for s in strategies}
    return {
        "run": run,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "complete": bool(strategies) and all(done[s] >= planned for s in strategies),
        "incidents_planned": planned,
        "incidents_done": done,
        "strategies": {
            s: summary.model_dump(mode="json") for s in strategies if (summary := summarize(rows, s))
        },
        "comparisons": {
            s: comparison.model_dump(mode="json")
            for s in strategies
            if s != "amnesiac" and (comparison := compare(rows, s))
        },
    }


def build_chart_data(run: dict[str, Any], rows: list[Row], growth: list[Row]) -> dict[str, Any]:
    strategies = _strategies(run, rows)
    incidents = _incidents(rows)
    return {
        "run_id": run.get("run_id"),
        "strategies": strategies,
        "colors": {s: COLORS.get(s, "#555555") for s in strategies},
        "incidents": incidents,
        "migrations": _migration_marks(incidents),
        "curves": {s: learning_curve(rows, s) for s in strategies},
        "growth": {
            s: sorted((g for g in growth if g["strategy"] == s), key=lambda g: g["n"])
            for s in strategies
            if any(g["strategy"] == s for g in growth)
        },
    }


# charts ---------------------------------------------------------------------------------------------


def _figure(title: str, ylabel: str) -> tuple[Figure, Any]:
    fig = Figure(figsize=(10, 4.2), dpi=150, layout="constrained")
    ax = fig.subplots()
    ax.set_title(title, loc="left", fontsize=12)
    ax.set_ylabel(ylabel)
    ax.grid(axis="y", alpha=0.3)
    ax.spines[["top", "right"]].set_visible(False)
    return fig, ax


def _incident_axis(ax: Any, data: dict[str, Any]) -> None:
    ns = [i["n"] for i in data["incidents"]]
    ax.set_xticks(ns)
    ax.set_xlabel("Gauntlet incident")
    for i in data["incidents"]:
        if i["kind"] == "look-alike":
            ax.axvspan(i["n"] - 0.5, i["n"] + 0.5, color="#22d3ee", alpha=0.12, lw=0)
    for m in data["migrations"]:
        ax.axvline(m["x"], color="#1d2330", ls="--", lw=1)
        ax.text(m["x"], 1.0, f" {m['id']}", transform=ax.get_xaxis_transform(), va="top", fontsize=8)


def chart_mttr(data: dict[str, Any], path: Path) -> None:
    fig, ax = _figure("MTTR per incident (shaded: look-alikes; dashed: migrations)", "simulated minutes")
    for s in data["strategies"]:
        points = data["curves"][s]
        ax.plot(
            [p["n"] for p in points], [p["mttr_min"] for p in points], "o-", color=data["colors"][s], label=s
        )
    _incident_axis(ax, data)
    ax.legend(frameon=False)
    fig.savefig(path)


def chart_accuracy(data: dict[str, Any], path: Path) -> None:
    fig, ax = _figure("Cumulative diagnosis accuracy", "correct so far (%)")
    for s in data["strategies"]:
        points = data["curves"][s]
        ax.plot(
            [p["n"] for p in points],
            [100 * p["cumulative_accuracy"] for p in points],
            "o-",
            color=data["colors"][s],
            label=s,
        )
    ax.set_ylim(0, 105)
    _incident_axis(ax, data)
    ax.legend(frameon=False)
    fig.savefig(path)


def chart_steps(data: dict[str, Any], path: Path) -> None:
    fig, ax = _figure("Tool calls per incident: useful and wasted (mean)", "tool calls")
    strategies = data["strategies"]
    tallest = 0.0
    for x, s in enumerate(strategies):
        points = data["curves"][s]
        steps = sum(p["steps"] for p in points) / len(points)
        wasted = sum(p["wasted_steps"] for p in points) / len(points)
        ax.bar(x, steps - wasted, color=data["colors"][s], width=0.5)
        ax.bar(x, wasted, bottom=steps - wasted, color=data["colors"][s], alpha=0.35, width=0.5, hatch="//")
        tallest = max(tallest, steps)
    ax.set_xticks(range(len(strategies)), strategies)
    ax.set_ylim(0, tallest * 1.25 or 1)
    ax.legend(
        handles=[
            Patch(facecolor="#8b93a7", label="useful"),
            Patch(facecolor="white", edgecolor="#8b93a7", hatch="//", label="wasted"),
        ],
        frameon=False,
        loc="upper center",
        ncols=2,
    )
    fig.savefig(path)


def chart_growth(data: dict[str, Any], path: Path) -> bool:
    series = [
        (s, key, label)
        for s, rows in data["growth"].items()
        for key, label in GROWTH_KEYS.items()
        if any(key in r for r in rows)
    ]
    if not series:
        return False
    fig, ax = _figure("Memory growth (0 = after the Day-0 import)", "count")
    styles = ["o-", "s--", "^:", "d-."]
    for s, key, label in series:
        rows = [r for r in data["growth"][s] if key in r]
        style = styles[list(GROWTH_KEYS).index(key) % len(styles)]
        ax.plot(
            [r["n"] for r in rows],
            [r[key] for r in rows],
            style,
            color=data["colors"][s],
            label=f"{s}: {label}",
        )
    ax.set_xlabel("Gauntlet incident")
    ax.legend(frameon=False, fontsize=8, ncols=2)
    fig.savefig(path)
    return True


def chart_cost(data: dict[str, Any], path: Path) -> None:
    fig, ax = _figure("LLM cost per incident", "USD")
    for s in data["strategies"]:
        points = data["curves"][s]
        ax.plot(
            [p["n"] for p in points], [p["usd_cost"] for p in points], "o-", color=data["colors"][s], label=s
        )
    _incident_axis(ax, data)
    ax.legend(frameon=False)
    fig.savefig(path)


def write_charts(data: dict[str, Any], directory: Path) -> list[Path]:
    directory.mkdir(parents=True, exist_ok=True)
    written = []
    for name, draw in (
        ("mttr", chart_mttr),
        ("accuracy", chart_accuracy),
        ("steps", chart_steps),
        ("cost", chart_cost),
    ):
        draw(data, directory / f"{name}.png")
        written.append(directory / f"{name}.png")
    if chart_growth(data, directory / "memory_growth.png"):
        written.append(directory / "memory_growth.png")
    return written


def write_run_report(run_dir: Path) -> dict[str, Any] | None:
    """summary.json, chart_data.json and charts for one run; None until it has results."""
    rows = read_jsonl(run_dir / "results.jsonl")
    if not rows:
        return None
    run = json.loads((run_dir / "run.json").read_text())
    summary = build_summary(run, rows)
    data = build_chart_data(run, rows, read_jsonl(run_dir / "growth.jsonl"))
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2))
    (run_dir / "chart_data.json").write_text(json.dumps(data, indent=2))
    write_charts(data, run_dir / "charts")
    return summary


# EVAL_RESULTS.md ------------------------------------------------------------------------------------------


def _minutes(value: float | None) -> str:
    return "n/a" if value is None else f"{value:g} min"


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value:+g}%"


def render_markdown(summary: dict[str, Any], rows: list[Row], charts: list[str]) -> str:
    run = summary["run"]
    loop = run.get("loop", {})
    strategies = list(summary["strategies"])
    done = summary["incidents_done"]
    status = (
        "complete"
        if summary["complete"]
        else "partial: " + ", ".join(f"{s} {done[s]} of {summary['incidents_planned']}" for s in strategies)
    )
    out = [
        "# Gauntlet results",
        "",
        f"Generated by `backend/dejavu/eval/report.py` from run `{run['run_id']}`. Do not edit by hand; "
        f"regenerate with `uv run python -m dejavu.eval.report --run-id {run['run_id']} --publish`.",
        "",
        "| Run | |",
        "|---|---|",
        f"| Status | {status} |",
        f"| Incidents per strategy | {summary['incidents_planned']} |",
        f"| Strategies | {', '.join(strategies)} |",
        f"| Seed | {run['seed']} |",
        f"| Model | {', '.join(run['models'])} (pinned for every strategy, no fallbacks) |",
        f"| Step budget | {loop.get('max_steps')} tool calls, {loop.get('sim_budget_min')} simulated minutes |",
        f"| Started | {run['started_at'][:16].replace('T', ' ')} |",
        f"| Code | `{run.get('git_sha') or 'unknown'}` |",
        "",
        "## Headline",
        "",
        "| Strategy | Correct | Mean MTTR | Median MTTR | Mean time to diagnosis | Wasted steps | Harmful actions | Payments at risk | Tokens | Cost |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for s, x in summary["strategies"].items():
        out.append(
            f"| {s} | {x['correct']}/{x['incidents']} ({x['accuracy']:.0%}) | {_minutes(x['mttr_mean'])} | "
            f"{_minutes(x['mttr_median'])} | {_minutes(x['ttd_mean'])} | {x['wasted_steps']} | "
            f"{x['harmful_actions']} | {inr_words(x['inr_at_risk'])} | {x['tokens']:,} | ${x['usd_cost']:.2f} |"
        )
    if summary["comparisons"]:
        out += [
            "",
            "## Against the amnesiac baseline",
            "",
            "Paired: each strategy is compared with the amnesiac on the incidents both finished. "
            "Negative MTTR change means faster.",
            "",
            "| Strategy | Incidents | MTTR change | MTTR change on recurrences | Accuracy change | Wasted steps saved | Payments at risk avoided |",
            "|---|---|---|---|---|---|---|",
        ]
        for s, c in summary["comparisons"].items():
            mttr = None if c["mttr_reduction_pct"] is None else -c["mttr_reduction_pct"]
            recur = (
                None if c["recurrence_mttr_reduction_pct"] is None else -c["recurrence_mttr_reduction_pct"]
            )
            out.append(
                f"| {s} | {c['incidents']} | {_pct(mttr)} | {_pct(recur)} | {c['accuracy_delta_pp']:+g} pp | "
                f"{c['wasted_steps_saved']} | {inr_words(c['inr_saved'])} |"
            )
    out += [
        "",
        "## By incident kind",
        "",
        "Accuracy and mean MTTR per kind. Kinds come from the schedule: a recurrence repeats an earlier "
        "Gauntlet archetype, a look-alike resembles one, and a novel incident matches nothing seen before.",
        "",
        "| Kind | " + " | ".join(strategies) + " |",
        "|---|" + "---|" * len(strategies),
    ]
    for kind in KINDS:
        cells = []
        for s in strategies:
            k = summary["strategies"][s]["by_kind"].get(kind)
            cells.append(f"{k['accuracy']:.0%}, {_minutes(k['mttr_mean'])} (n={k['incidents']})" if k else "")
        out.append(f"| {kind} | " + " | ".join(cells) + " |")
    by_pair = {(r["n"], r["strategy"]): r for r in rows}
    out += [
        "",
        "## Per incident",
        "",
        "| # | Incident | Archetype (ground truth) | Kind | " + " | ".join(strategies) + " |",
        "|---|---|---|---|" + "---|" * len(strategies),
    ]
    for i in _incidents(rows):
        cells = []
        for s in strategies:
            r = by_pair.get((i["n"], s))
            cells.append(f"{'✓' if r['correct'] else '✗'} {_minutes(r['mttr_min'])}" if r else "")
        kind = i["kind"] + (", after a migration" if i["after_migration"] else "")
        out.append(
            f"| {i['n']} | {i['incident_id']} | {i['archetype']} | {kind} | " + " | ".join(cells) + " |"
        )
    if charts:
        out += ["", "## Charts", ""]
        out += [f"![{CHART_TITLES.get(name, name)}](eval/{name}.png)" for name in charts]
    out += [
        "",
        "## Limitations",
        "",
        "- Synthetic environment: the incidents come from the SRE-Gym simulator, not production telemetry.",
        f"- Small N and one seed ({run['seed']}): {summary['incidents_planned']} incidents per strategy. A "
        "difference of one or two incidents is within noise.",
        "- MTTR follows the grader's rules (spec 7.3): 3 minutes of detection, time to diagnosis, then "
        "remediation until recovery; with no working fix a human resolves the incident 45 minutes after "
        "the diagnosis.",
        "- Human feedback and postmortems are authored fixtures, written from simulator fact sheets and "
        "identical for every strategy.",
        "- Costs use per-token list prices; the gpt-oss-120b price comes from the build spec, the others "
        "are estimates (`LLM_PRICES` overrides them).",
        "- Foresight prevention is not scored in this run, so `prevented` is zero by construction.",
        "",
    ]
    return "\n".join(out)


def publish(run_dir: Path, docs_dir: Path = DOCS_DIR) -> Path:
    """Rewrite docs/EVAL_RESULTS.md from `run_dir` and copy its charts to docs/eval/."""
    summary = write_run_report(run_dir)
    if summary is None:
        raise SystemExit(f"{run_dir.name} has no results yet")
    target = docs_dir / "eval"
    target.mkdir(parents=True, exist_ok=True)
    charts = []
    for png in sorted((run_dir / "charts").glob("*.png")):
        shutil.copy2(png, target / png.name)
        charts.append(png.stem)
    doc = docs_dir / "EVAL_RESULTS.md"
    doc.write_text(render_markdown(summary, read_jsonl(run_dir / "results.jsonl"), charts))
    return doc


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--run-id", help="a run under data/eval (default: the latest)")
    parser.add_argument("--publish", action="store_true", help="rewrite docs/EVAL_RESULTS.md from this run")
    args = parser.parse_args()
    run_dir = EVAL_DIR / args.run_id if args.run_id else latest_run()
    if run_dir is None or not (run_dir / "run.json").exists():
        raise SystemExit("no Gauntlet run found under data/eval")
    if args.publish:
        print(f"wrote {publish(run_dir).relative_to(REPO_ROOT)}")
    elif write_run_report(run_dir) is None:
        print(f"{run_dir.name} has no results yet")
    else:
        print(f"wrote {(run_dir / 'summary.json').relative_to(REPO_ROOT)} and charts")
