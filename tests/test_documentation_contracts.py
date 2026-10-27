"""Release claims retain their evidence boundaries and operational exceptions."""

import re

from conftest import ROOT, SKILL


def test_readmes_route_measurements_through_one_index_and_scope_trust():
    for path in ROOT.glob("README*.md"):
        text = path.read_text(encoding="utf-8")
        links = re.findall(r"\]\((docs/(?:evals|trigger)/[^)]+)\)", text)
        assert links == ["docs/evals/README.md"]
        assert "references/hooks-capabilities.md" in text
        assert not re.search(r"docs/host-dry-runs/[^)]+", text)
        assert "`--shim-only`" in text and "SessionStart" in text and "`ro brief`" in text
        for name in ("postmortem", "compute", "workflow-classic"):
            assert f"references/{name}.md" in text
        codex = next(line for line in text.splitlines() if line.startswith("| Codex |"))
        assert codex.endswith("| `ro`, Git pre-push |")
    index = (ROOT / "docs/evals/README.md").read_text(encoding="utf-8")
    for number in ("231/232", "99.57%", "6/6", "38/38", "87.87%", "0/47", "20/20", "59/60"):
        assert number in index
    assert '14/38' not in index and '47.23%' not in index and '56.31%' not in index
    assert "Grader" in index and "Runtime digest" in index


def test_prominent_trust_scope_distinguishes_untrusted_from_trusted_invocations():
    index = (ROOT / "docs/evals/README.md").read_text(encoding="utf-8")
    paragraphs = [part for part in index.split("\n\n") if "Codex" in part]
    disclosure = next(part for part in paragraphs if "--dangerously-bypass-hook-trust" in part and "/hooks" in part)
    assert {"--dangerously-bypass-hook-trust", "/hooks"} <= set(re.findall(r"`([^`]+)`", disclosure))
    assert re.search(r"persisted.{0,50}(?:not|unverified)", disclosure, re.I | re.S)
    assert re.search(r"(?:ordinary|untrusted).{0,150}(?:not|until|without)", index, re.I | re.S)
    assert any("`ro`" in part and "Git pre-push" in part for part in paragraphs)
    for filename in ("README.md", "README.ko.md", "README.ja.md", "README.zh-CN.md"):
        translated = (ROOT / filename).read_text(encoding="utf-8")
        assert translated.count("](docs/evals/README.md)") == 1
        assert "](skills/research-orchestrator/references/hooks-capabilities.md)" in translated
    diagram = (ROOT / "assets/readme/safety-layers.svg").read_text(encoding="utf-8")
    assert all(token in diagram for token in ("--dangerously-bypass-hook-trust", "/hooks", "codex exec", "Git pre-push"))


def test_claude_record_is_diagnostics_based_and_sanitized():
    record = (ROOT / "docs/host-dry-runs/claude-code-2026-10-27.md").read_text(encoding="utf-8")
    assert re.search(r"\b(?:six|6)\b.*\bprobes?\b", record, re.I)
    assert ".ro/hook-diagnostics.jsonl" in record
    assert "Claude Code 2.1.287" in record and "claude-haiku-5-5" in record
    assert "<temporary-project>" in record and "<plugin-checkout>" in record
    assert not re.search(r"\b[A-Za-z]:[\\/]|/(?:Users|home)/[^/\s]+", record)
    assert len(re.findall(r"^\| (?:background|delete-bound|benign|read-bound|unmonitored-stop|future-record) \|", record, re.M)) == 6
    for path in ROOT.glob("README*.md"):
        row = next(line for line in path.read_text(encoding="utf-8").splitlines() if line.startswith("| Claude Code |"))
        assert row.endswith("| `ro`, Git pre-push |")
        assert "](docs/evals/README.md)" in path.read_text(encoding="utf-8")


def test_read_first_guides_keep_lookup_details_out_of_startup():
    hooks = (SKILL / "references/hooks.md").read_text(encoding="utf-8")
    assert len(hooks.encode("utf-8")) <= 5000
    assert "hooks-capabilities.md" in hooks
    operations = (SKILL / "references/operations-safety.md").read_text(encoding="utf-8")
    assert "## Read first" in operations and "## Lookup:" in operations
    for document in (operations, (SKILL / "references/hooks-capabilities.md").read_text(encoding="utf-8")):
        for section in re.split(r"^## Lookup:.*\n", document, flags=re.M)[1:]:
            first = section.strip().splitlines()[0]
            assert re.match(r"(?:Run|Use|Check|Read|Inspect|Choose|Set)\b.*`(?:ro |python install.py )[^`]+`", first), first


def test_reconciled_enforcement_defaults_preserve_advisory_scope():
    from conftest import rs
    plan = (ROOT / "docs/plans/v3-plan.md").read_text(encoding="utf-8")
    assert "Reconciled 2026-10-27" in plan
    assert f"Block: {rs.DEFAULT_BLOCK}" in plan
    advisory = next(part for part in plan.split("\n\n") if "warn-only" in part and "jobs.unmonitored" in part)
    assert {"jobs.unmonitored", "records.id", "ask.away"} <= set(re.findall(r"`([^`]+)`", advisory))
    for preset in rs.BUILTIN_PRESETS:
        settings = rs.resolve({}, rs.load_preset(preset), {})
        assert settings["enforcement"] == "block"
        assert not {"jobs.unmonitored", "records.id", "ask.away"} & {
            value.strip() for value in settings["block"].split(",")}


def test_ci_measures_each_os_without_duplicate_missing_artifact_failure():
    text = (ROOT / ".github/workflows/validate.yml").read_text(encoding="utf-8")
    assert "if-no-files-found: warn" in text and "if-no-files-found: error" not in text
    step = text.split("- name: Measure installed hook p95 on this OS", 1)[1].split("- name:", 1)[0]
    assert "if: always()" in step and "RO_LATENCY_REPORT: hook-latency.json" in step
    assert "-m latency" in step and "tests/test_ro_cli.py" in step
    assert "name: hook-latency-${{ matrix.os }}" in text


def test_retracted_plan_settings_are_marked_in_original_rows():
    text = (ROOT / "docs/plans/v3-plan.md").read_text(encoding="utf-8")
    for name in ("Review cadence", "Discovery read", "Deliverable field"):
        assert f"| ~~`{name}`~~ | Retracted:" in text


def test_codex_grader_requires_the_observed_trust_condition():
    grader = SKILL / "evals/codex-host-capabilities/graders/90-01-dated-enforcement-status.md"
    text = grader.read_text(encoding="utf-8")
    assert "--dangerously-bypass-hook-trust" in text
    assert "/hooks" in text and re.search(r"(?:not exercised|unverified)", text, re.I)
