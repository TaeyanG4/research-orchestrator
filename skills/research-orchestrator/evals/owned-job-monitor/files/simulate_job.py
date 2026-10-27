"""Eight-second owned-job fixture with durable ownership samples."""
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

root = Path(__file__).resolve().parent
out = root / "runs" / "owned"
out.mkdir(parents=True, exist_ok=True)
if (out / "job-result.json").exists():
    raise SystemExit("The simulated job already completed.")
started = datetime.now(timezone.utc).isoformat()
(out / "started-handoff.md").write_bytes((root / "handoff.md").read_bytes())
deadline = time.monotonic() + 8.0
samples = []
while time.monotonic() < deadline:
    handoff = (root / "handoff.md").read_text(encoding="utf-8")
    plan = (root / "plan.md").read_text(encoding="utf-8")
    slot = re.search(r"^### Agent: A\s*$([\s\S]*?)(?=^### |^## |\Z)", handoff, re.M)
    item = re.search(r"^### H-A-01[^\n]*\n([\s\S]*?)(?=^### |^## |\Z)", plan, re.M)
    def field(text, name):
        match = re.search(r"^- " + re.escape(name) + r": (.*)$", text, re.M)
        return match.group(1).strip() if match else None
    samples.append({
        "sampled_at": datetime.now(timezone.utc).isoformat(),
        "current_host": field(slot.group(1) if slot else "", "Current host"),
        "current_user": field(slot.group(1) if slot else "", "Current user"),
        "claim": field(item.group(1) if item else "", "Claimed"),
        "active_compute": field(handoff, "Active compute"),
    })
    (out / "ownership-samples.json").write_text(json.dumps(samples, indent=2) + "\n", encoding="utf-8")
    time.sleep(0.25)
result = {"status": "completed", "started_at": started,
          "completed_at": datetime.now(timezone.utc).isoformat(), "sample_count": len(samples)}
(out / "job-result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
print(json.dumps(result))
