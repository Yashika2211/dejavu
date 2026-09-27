"""Write the ground-truth fact sheets behind every human-voice fixture.

For each Gauntlet incident this replays the humans' actions (`data/fixtures/human_paths.yaml`)
in the simulator and writes `data/fixtures/facts/incident-NN.json`. The postmortems, Slack
threads and feedback notes in `data/fixtures/incidents/` are written from these sheets and
reviewed by hand, so every time and number in them matches the simulation.

    uv run python scripts/generate_fixtures.py
"""

import json

from rich.console import Console
from rich.table import Table

from dejavu.config import REPO_ROOT
from dejavu.sim.generators.humans import fact_sheet
from dejavu.sim.schedule import entry_for, gauntlet

FACTS_DIR = REPO_ROOT / "data" / "fixtures" / "facts"


def main() -> None:
    FACTS_DIR.mkdir(parents=True, exist_ok=True)
    table = Table(title="Gauntlet fact sheets (canonical human account)")
    for col in ("#", "incident", "date", "root cause", "recovered", "MTTR", "failed pay", "INR at risk"):
        table.add_column(col)
    for scenario in gauntlet():
        entry = entry_for(scenario)
        assert entry is not None
        facts = fact_sheet(entry.n, scenario)
        (FACTS_DIR / f"incident-{entry.n:02d}.json").write_text(
            json.dumps(facts.model_dump(), indent=2) + "\n"
        )
        table.add_row(
            str(entry.n),
            facts.incident_id,
            facts.date,
            f"{facts.root_cause_category} / {facts.culprit_service}",
            facts.resolved_at,
            f"{facts.mttr_min:g}m",
            f"{facts.failed_payments:,}",
            f"{facts.inr_at_risk:,}",
        )
    Console().print(table)


if __name__ == "__main__":
    main()
