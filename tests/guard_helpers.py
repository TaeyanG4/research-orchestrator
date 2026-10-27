"""Small, domain-neutral project records for the P2 guard tests."""

from __future__ import annotations

from pathlib import Path
import re

from conftest import FIXTURES, append_discovery, append_events, event, init, make_project, rs

GUARDS = ("G1", "G3", "G5", "G6", "GD", "G8", "G11", "G12", "E1")
BASE_FIELDS = {"Source", "Host", "User", "Date", "Cross-check", "Finding", "Evidence", "Implication", "Reviews"}


def setting(target: Path, name: str, value: str) -> None:
    path = target / "agents.md"
    text = path.read_text(encoding="utf-8")
    pattern = re.compile(rf"^- {re.escape(name)}: .*?$", re.MULTILINE)
    if pattern.search(text):
        text = pattern.sub(lambda _match: f"- {name}: {value}", text, count=1)
    else:
        text = text.replace("## Project settings\n", f"## Project settings\n- {name}: {value}\n", 1)
    stored = rs.read_settings(text, target)
    values = rs.resolve({}, None, stored.values)
    region = rs.split_agents(text)[1]
    path.write_text(init.compose_agents(values, stored.project or "guard", region), encoding="utf-8", newline="\n")
    init.save_template_metadata(target, values)


def project(parent: Path, guards: str = "G1", mode: str = "light", profile: str = "research",
            workflow: str = "unified", name: str = "guard") -> Path:
    extra = ["--competition", "hub/task-a"] if profile == "competition" else []
    target = make_project(parent, name, "--profile", profile, "--workflow", workflow,
                          "--verification", "self", "--guards", "off", "--user", "operator",
                          "--platforms", "Claude Code, Codex", *extra)
    setting(target, "Guards", f"{mode} since 2026-10-01")
    setting(target, "Guard set", guards)
    shared(target, "Not applicable", "none")
    # Fixed historical records support the helpers' explicit evidence citations. Keep them
    # outside the active window and the IDs used by individual measurement tests.
    append_discovery(target, discovery("D-Z-990", source="Z", date="2026-09-30",
                                      finding="independent evidence records agreement 0.91 and confirms execution"))
    append_discovery(target, discovery("D-Z-991", source="Z", date="2026-09-30",
                                      finding="repeated measurements establish resolution 0.01"))
    return target


def shared(target: Path, name: str, value: str) -> None:
    path = target / "handoff.md"
    text = path.read_text(encoding="utf-8")
    pattern = re.compile(rf"^- {re.escape(name)}: .*?$", re.MULTILINE)
    if pattern.search(text):
        text = pattern.sub(lambda _match: f"- {name}: {value}", text, count=1)
    else:
        text = text.replace("## Shared state\n", f"## Shared state\n- {name}: {value}\n", 1)
    path.write_text(text, encoding="utf-8", newline="\n")


def section(target: Path, name: str, text: str) -> None:
    path = target / "handoff.md"
    content = path.read_text(encoding="utf-8")
    marker = f"## {name}\n"
    if marker in content:
        content = content.replace(marker, marker + "\n" + text + "\n", 1)
    else:
        content += f"\n{marker}\n{text}\n"
    path.write_text(content, encoding="utf-8", newline="\n")


def discovery(did: str = "D-A-001", *, source: str = "A", date: str = "2026-10-24", finding: str = "the change helps",
              implication: str = "keep the result", **fields: str) -> str:
    values = [("Source", source), ("Host", "Claude Code"), ("User", "operator"), ("Date", date),
              ("Cross-check", "PENDING"), ("Finding", finding), ("Evidence", "recorded observation"),
              ("Implication", implication), ("Reviews", "")]
    values += [(key.replace("_", " "), value) for key, value in fields.items()]
    return f"## {did} — observation\n" + "\n".join(f"- {key}: {value}" for key, value in values) + "\n"


def instrument(iid: str = "I-A-01", *, provenance: str = "independent", coverage: str = "held-out",
               agreement: str = "0.91 agreement, D-Z-990", resolution: str = "±0.01 (D-Z-991)",
               not_for: str = "none", dynamics: str | None = None) -> str:
    values = [("Provenance", provenance), ("Coverage", coverage), ("Measures", "quality on stable cohort"),
              ("Agreement", agreement), ("Resolution", resolution), ("Not for", not_for)]
    if dynamics is not None:
        values.append(("Dynamics", dynamics))
    return f"### {iid} — measurement\n" + "\n".join(f"- {key}: {value}" for key, value in values) + "\n"


def action(xid: str = "X-A-001", *, artifact_hash: str = "abc001", destination: str = "external endpoint",
           expected: str | None = "quality above 0.80 (written 2026-10-24 08:00)",
           result: str = "quality=0.81 on I-A-01 cohort stable (observed 2026-10-24 09:00)",
           family: str = "family-a", retry: str | None = None) -> str:
    values = [("Kind", "release"), ("Candidate", f"candidate, hash {artifact_hash}"),
              ("Destination", destination), ("Family", family)]
    if expected is not None:
        values.append(("Expected", expected))
    values += [("Result", result), ("Final", "pending"), ("Status", "complete")]
    if retry is not None:
        values.append(("Retry of", retry))
    return f"### {xid} — outward action\n" + "\n".join(f"- {key}: {value}" for key, value in values) + "\n"


def review(did: str = "D-A-001", *, date: str = "2026-10-24", omit: str | None = None) -> str:
    fields = {"Kind": "direction-review", "Gap": "ours 0.81 vs reference 0.90 on I-A-01 (2026-10-24)",
              "Decomposition": "component-a loses 0.09", "Core_families": "family-a built standalone D-Z-990",
              "Data_audit": "source definitions and site effects reviewed", "Intake": "no new methods seen",
              "Rejected_consistent_gains": "none", "Decisions": "no change — current plan covers the gap"}
    if omit:
        fields.pop(omit.replace(" ", "_"))
    return discovery(did, date=date, **fields)


def plan(target: Path, *items: str) -> None:
    path = target / "plan.md"
    text = path.read_text(encoding="utf-8")
    if "\n## Queue\n" in text:
        prefix = text[:text.index("\n## Queue\n")]
        content = prefix + "\n## Queue\n\n" + "\n".join(items)
    else:
        prefix = text[:text.index("\n## Agent: A\n")]
        content = prefix + "\n## Agent: A\n\n" + "\n".join(items)
    path.write_text(content, encoding="utf-8", newline="\n")


def append_measurements(target: Path, *, cohorts: list[str] | None = None, count: int = 5,
                        start: int = 1, values: list[float] | None = None) -> None:
    for offset in range(count):
        cohort = cohorts[offset] if cohorts else "stable"
        value = values[offset] if values else 0.810 + offset * 0.001
        append_discovery(target, discovery(f"D-A-{start + offset:03}", date=f"2026-10-{20 + offset:02}",
                                          Family="family-a", Result=f"quality={value:.3f} on I-A-01 cohort {cohort}"))


def effort_events(target: Path, tags: list[str | None]) -> None:
    append_events(target, *(event(f"2026-10-24 10:{index:02}", "A", "none",
                                 extra=f"- Effort: {tag}\n" if tag else "") for index, tag in enumerate(tags)))


def replay(parent: Path, fixture: str, workflow: str = "unified", profile: str = "competition") -> Path:
    target = project(parent, ", ".join(GUARDS), profile=profile, workflow=workflow)
    for name in ("discoveries.md", "handoff.md", "plan.md"):
        fragment = FIXTURES / fixture / name
        if not fragment.is_file():
            continue
        text = fragment.read_text(encoding="utf-8")
        text = re.sub(r"(?m)^- User: .*?$", "- User: operator", text)
        if name == "discoveries.md":
            append_discovery(target, text)
        elif name == "plan.md":
            plan(target, text)
        else:
            # Fixtures contain only Shared state fields and the two new record sections.
            before, _, sections = text.partition("\n## Instruments\n")
            for line in before.splitlines():
                match = re.match(r"^- (.+?): (.*)$", line)
                if match:
                    shared(target, *match.groups())
            if sections:
                instruments, marker, actions = sections.partition("\n## External actions\n")
                section(target, "Instruments", instruments)
                if marker:
                    section(target, "External actions", actions)
    return target
