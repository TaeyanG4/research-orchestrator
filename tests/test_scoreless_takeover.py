"""Queue takeovers retain provenance and comparison without manufacturing scores."""
from conftest import SKILL, append_events, check, event, found, make_project, set_slot


def test_scoreless_cross_host_takeover_keeps_history_and_requires_reason(tmp_path):
    target = make_project(tmp_path, "queue", "--preset", "team-research", "--workflow", "classic",
                          "--platforms", "Lumen, Prism", "--agents", "2", "--user", "operator",
                          "--guards", "off", "--git", "off")
    set_slot(target, "A", "Lumen")
    set_slot(target, "B", "released", "none")
    plan = target / "plan.md"
    fields = ("- Sources: none\n- Hypothesis: totals reconcile with source rows\n"
              "- Evidence: two printed tables disagree\n- Improvement: none\n"
              "- Next test: sum each row\n")
    plan.write_text("# Queue\n\n- Ordering: queue\n\n## Agent: A\n\n## Agent: B\n\n"
                    "### H-B-01 — Printed table audit\n" + fields, encoding="utf-8")
    assert not found(check(target), "ERROR")
    history = event("2026-10-24 09:00", "B", "none", host="Prism")
    append_events(target, history)
    plan.write_text("# Queue\n\n- Ordering: queue\n\n## Agent: A\n\n"
                    "### H-A-01 — Printed table audit (from H-B-01)\n" + fields + "\n## Agent: B\n",
                    encoding="utf-8")
    reason = "one reconciliation resolves the source disagreement before any new sample"
    action = f"took over H-B-01 from B (cross-host: Prism → Lumen; reason: {reason}) as H-A-01"
    takeover = event("2026-10-25 10:00", "A", "H-A-01", "none — take-over, no experiment", host="Lumen")
    append_events(target, takeover.replace("worked on it", action))
    result = check(target)
    assert not found(result, "ERROR") and not found(result, "WARN")
    assert "H-B-01" in result.retired and "H-A-01" in result.plan_items
    handoff = target / "handoff.md"
    assert history in handoff.read_text(encoding="utf-8")
    assert "- Priority:" not in plan.read_text(encoding="utf-8")
    handoff.write_text(handoff.read_text(encoding="utf-8").replace(reason, ""), encoding="utf-8")
    assert found(check(target), check_id="event.takeover.reason")
    guidance = (SKILL / "references/workflow-classic.md").read_text(encoding="utf-8")
    condition = guidance.split("3. **The item is promising**:", 1)[1].split("\n4.", 1)[0]
    assert "only with priority ordering" in condition
    assert "`Ordering: queue`" in condition and "without inventing scores" in condition
