"""The documented launchable Resource values are the ones `ro launch` accepts."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "research-orchestrator"


def test_plan_items_resource_values_match_the_launcher():
    guide = (SKILL / "references" / "plan-items.md").read_text(encoding="utf-8")
    line = next(row for row in guide.splitlines() if row.startswith("`Resource` is the local capacity class"))
    documented = set(re.findall(r"`(CPU|GPU|EITHER)`", line))
    launcher = (SKILL / "scripts" / "ro_jobs.py").read_text(encoding="utf-8")
    message = re.search(r"launch needs Resource ([A-Z/]+) and", launcher).group(1)
    assert documented == set(message.split("/")) == {"CPU", "GPU", "EITHER"}
    assert "`Resource: none`" in line and "Handoff events" in line
