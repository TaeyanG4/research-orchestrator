"""Measure UTF-8 startup bytes (normalized LF), excluding variable project records.

Run directly, or use --revision HEAD for a reproducible before/after comparison.
The legacy template mandated active references (including guard dependencies);
the trimmed template makes references operation-specific. Answers are fixed so
only the skill changes between runs. Temporary revision files are cleaned up.
"""

from __future__ import annotations

import argparse
import io
import json
from pathlib import Path
import re
import subprocess
import sys
import tarfile
import tempfile


ROOT = Path(__file__).resolve().parents[1]
RELATIVE_SKILL = Path("skills/research-orchestrator")
sys.path.insert(0, str(ROOT))
from scripts.evals.proc import no_window_flags
from scripts.evals.baseline import SKILL_SUBTREE


def measure(skill: Path = ROOT / RELATIVE_SKILL) -> dict[str, dict]:
    sys.path.insert(0, str(skill / "scripts"))
    import init_research_orchestrator as init
    import ro_settings as settings

    if init.SKILL_ROOT.resolve() != skill.resolve():
        raise ValueError("measure revisions in a fresh interpreter")
    core = (skill / "SKILL.md").read_text(encoding="utf-8").encode("utf-8")
    totals = {}
    for name in settings.BUILTIN_PRESETS:
        preset = settings.load_preset(name)
        flags = {"preset": name, "platforms": "local" if preset["platform_mode"] == "single" else "local, remote",
                 "environment": "linux/bash", "git": "off", "competition": "service/task",
                 "phase_clock": "2026-10-01,2026-12-01"}
        values = settings.resolve(flags, preset, {})
        agents = init.compose_agents(values, "project")
        references = set()
        if "Read that core, then these references for the active settings:" in agents:
            references = set(re.findall(r"<skill-root>/(references/[\w./-]+\.md)", agents))
            # These legacy pointers already named their operation, not startup.
            references -= {f"references/{stem}.md" for stem in (
                "plan-collector", "external-actions", "publication-safety", "postmortem")}
            if values["guards"] != "off":
                references.update(("references/decision-guards.md", "references/external-actions.md"))
        elif "At startup read only that core, this file," not in agents:
            raise ValueError("unrecognized startup reading contract")
        reference_bytes = sum(len((skill / path).read_text(encoding="utf-8").encode("utf-8"))
                              for path in references)
        totals[name] = {"core": len(core), "agents": len(agents.encode("utf-8")),
                        "references": sorted(references), "reference_bytes": reference_bytes,
                        "total": len(core) + len(agents.encode("utf-8")) + reference_bytes}
    return totals


def revision_measure(revision: str) -> dict[str, dict]:
    git = ["git", "-c", f"safe.directory={ROOT.as_posix()}"]
    exists = subprocess.run(git + ["cat-file", "-e", f"{revision}:{RELATIVE_SKILL.as_posix()}/SKILL.md"],
                            cwd=ROOT, capture_output=True, creationflags=no_window_flags())
    relative_skill = RELATIVE_SKILL if exists.returncode == 0 else Path(SKILL_SUBTREE)
    paths = [str(relative_skill / path).replace("\\", "/") for path in (
        "SKILL.md", "scripts",
        "templates", "presets", "references")]
    archive = subprocess.run(["git", "-c", f"safe.directory={ROOT.as_posix()}",
                              "archive", "--format=tar", revision, *paths], cwd=ROOT,
                             capture_output=True, check=True, creationflags=no_window_flags()).stdout
    with tempfile.TemporaryDirectory(prefix="ro-startup-") as folder:
        target = Path(folder).resolve()
        with tarfile.open(fileobj=io.BytesIO(archive)) as bundle:
            for member in bundle:
                if not member.isfile():
                    continue
                destination = (target / member.name).resolve()
                if not destination.is_relative_to(target):
                    raise ValueError("revision archive path leaves temporary directory")
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(bundle.extractfile(member).read())
        result = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--skill-root",
                                 str(target / relative_skill)], capture_output=True, text=True,
                                encoding="utf-8", check=True, creationflags=no_window_flags())
        return json.loads(result.stdout)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--revision", help="compare a git revision to the working tree")
    parser.add_argument("--skill-root", type=Path, default=ROOT / RELATIVE_SKILL, help=argparse.SUPPRESS)
    args = parser.parse_args()
    current = measure(args.skill_root)
    if args.revision:
        previous = revision_measure(args.revision)
        for name, row in current.items():
            print(f"{name}: {previous[name]['total']} -> {row['total']} bytes")
    else:
        print(json.dumps(current, indent=2))


if __name__ == "__main__":
    main()
