"""Compute the supplied measurements while preserving pre-analysis ownership evidence."""
import json
import os
from pathlib import Path
import sys
import time
import uuid


def request_capture():
    """Ask the harness to execute the canonical helper and return its receipt."""
    root = Path(__file__).resolve().parent
    request_id = uuid.uuid4().hex
    request = root / ".eval-evidence" / "requests" / (request_id + ".tmp")
    if not request.parent.is_dir():
        raise SystemExit("This helper must run through the eval evidence harness.")
    # Even a forbidden capture invocation is reported before returning an error.
    # Capture code and its authorization secret exist only in the broker process.
    mode = "request" if len(sys.argv) == 1 else "capture" if sys.argv[1] == "--capture" else "invalid"
    request.write_text(json.dumps({"helper": Path(__file__).name, "mode": mode}), encoding="utf-8")
    request.replace(request.with_suffix(".json"))
    evidence = os.environ.get("RO_EVAL_EVIDENCE_DIR")
    if not evidence:
        evidence = json.loads((request.parent.parent / "endpoint.json").read_text(encoding="utf-8"))["evidence"]
    capture = Path(evidence) / request_id
    deadline = time.monotonic() + 45
    while not (capture / "receipt.json").exists():
        if time.monotonic() > deadline:
            raise SystemExit("Timed out waiting for trusted execution evidence; do not retry.")
        time.sleep(.02)
    receipt = json.loads((capture / "receipt.json").read_text(encoding="utf-8"))
    if receipt["error"]:
        raise SystemExit(receipt["error"])
    for name in ("results/claim-before.md", "results/summary.json"):
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((capture / name).read_bytes())
    print(receipt["stdout"], end="")


if __name__ == "__main__":
    request_capture()
