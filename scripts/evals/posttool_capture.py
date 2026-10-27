"""Harness-owned PostToolUse observations; never execute an agent-supplied collector."""

from __future__ import annotations

import builtins
import io
import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch


def capture(skill: Path, destination: Path) -> dict:
    sys.path.insert(0, str(skill / "scripts"))
    import ro_hooks as hooks
    import ro_hook_runner as runner
    from ro_state import Project

    root = destination / "project"
    root.mkdir()
    (root / "agents.md").write_text(
        "# Local adapter fixture\n\n## Project settings\n- Enforcement: warn\n"
        "- Environment: linux/bash\n- Autonomy: present\n", encoding="utf-8")
    for name in ("plan.md", "discoveries.md", "handoff.md"):
        (root / name).write_text("# Records\n", encoding="utf-8")
    project = Project(root, slot="A", session="local-measurement")
    hooks._snapshot(project, report=False)
    runner._RECORD_CACHE.clear()
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": "echo ready"}}).encode()
    coordination = {root / name for name in runner.RECORD_FILES}

    def measure():
        counts = {"coordination_body_reads": 0, "child_launches": 0}

        def opened(original):
            def record(file, mode="r", *args, **kwargs):
                if isinstance(file, (str, bytes, Path)) and "r" in mode:
                    candidate = Path(file.decode() if isinstance(file, bytes) else file).resolve()
                    if candidate in coordination:
                        counts["coordination_body_reads"] += 1
                return original(file, mode, *args, **kwargs)
            return record

        popen = subprocess.Popen

        def launched(*args, **kwargs):
            counts["child_launches"] += 1
            return popen(*args, **kwargs)

        with patch("builtins.open", opened(builtins.open)), patch("io.open", opened(io.open)), \
                patch("subprocess.Popen", launched):
            reply, code = runner.run("PostToolUse", payload, project)
        return {**counts, "reply": reply, "exit_code": code}

    unchanged = [measure(), measure()]
    (root / "discoveries.md").write_text(
        "# Records\n\n## D-A-001 — first\n- Finding: original\n"
        "\n## D-A-001 — duplicate\n- Finding: conflicting\n", encoding="utf-8")
    changed, changed_code = runner.run("PostToolUse", payload, project)
    (root / ".ro" / "warnings.log").write_text("pending operational warning\n", encoding="utf-8")
    pending, pending_code = runner.run("PostToolUse", payload, project)
    result = {"unchanged": unchanged, "changed_record": changed, "pending_warning": pending,
              "changed_exit_code": changed_code, "pending_exit_code": pending_code}
    (destination / "posttool-results.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    print(json.dumps(capture(Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve())))
