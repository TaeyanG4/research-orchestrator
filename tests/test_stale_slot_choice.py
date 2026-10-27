"""New-session decisions use frozen record time, not host identity or process probes."""

import datetime as dt
import pytest

from conftest import append_events, event, item, set_queue, set_slot, unified_project
import ro
import ro_sessions as sessions
import ro_settings as settings
from ro_hooks import hook
from ro_records import _slot_sections, brief
from ro_state import Project

NOW = dt.datetime(2026, 10, 27, 12, 0)


@pytest.fixture
def root(tmp_path, monkeypatch):
    monkeypatch.setattr(sessions, "now", lambda: NOW)
    monkeypatch.setattr(settings, "detect_host", lambda: "local")
    path = unified_project(tmp_path)
    set_queue(path, item("H-A-01", "A since 2026-10-27 08:00"))
    append_events(path, event("2026-10-27 09:00", "A", "none"))
    return path


def start(root, session="new-session", **kwargs):
    project = Project(root, session=session, require_slot=False)
    text = sessions.startup(project, **kwargs)
    return project, text


def test_stale_crash_questions_once_with_all_options_and_no_mutation(root):
    before = {name: (root / name).read_bytes() for name in ("handoff.md", "plan.md")}
    project, question = start(root)
    assert question.count("?") == 1
    assert "Candidate A: Current host/user Claude Code/operator; last activity 2026-10-27 09:00" in question
    assert "running jobs none; stale" in question
    assert question.index("Continue slot A") < question.index("Start a new slot") < question.index("Use slot <X>")
    assert "resume its Next action; reclaim it if its session has ended" in question
    assert not project.slot_registered
    assert all((root / name).read_bytes() == value for name, value in before.items())
    assert brief(Project(root, session="brief-session", require_slot=False)).startswith(question.replace(
        "new-session", "brief-session"))


def test_sessionstart_and_brief_share_decision_and_reminder_is_once(root):
    project = Project(root, session="native", require_slot=False)
    expected = sessions.startup(project)
    first = hook(project, "SessionStart", {})["hookSpecificOutput"]["additionalContext"]
    assert expected in first and first.count("Which slot") == 1
    again = hook(Project(root, session="native", require_slot=False), "SessionStart", {})
    assert "Which slot" not in str(again)
    assert "Which slot" not in str(hook(project, "Stop", {}))


def test_stop_first_keeps_the_same_one_question_available(root):
    project = Project(root, session="stop-first", require_slot=False)
    response = hook(project, "Stop", {})
    assert "Which slot should this new session use?" in str(response)
    assert "Which slot" not in str(hook(project, "SessionStart", {}))


def test_repeated_native_start_keeps_explicit_parallel_route(root):
    project = Project(root, session="repeated", require_slot=False)
    payload = {"session_intent": "parallel", "user": "operator", "host": "local"}
    hook(project, "SessionStart", payload)
    before = (root / "handoff.md").read_bytes()
    repeated = Project(root, session="repeated", require_slot=False)
    hook(repeated, "SessionStart", payload)
    assert repeated.slot == "C" and (root / "handoff.md").read_bytes() == before


@pytest.mark.parametrize("choice", ["parallel", "reclaim"])
def test_pending_migration_is_preserved_before_ownership_change(root, choice):
    project = Project(root, slot="A" if choice == "reclaim" else None, session="new", require_slot=False)
    project.write_json("migration.json", {"phase": "forward", "files": []})
    before = {path: path.read_bytes() for path in (root / "handoff.md", root / "plan.md", root / ".ro/migration.json")}
    with pytest.raises(ValueError, match="pending project migration"):
        sessions.startup(project, intent="parallel" if choice == "parallel" else "", reclaim=choice == "reclaim")
    assert all(path.read_bytes() == value for path, value in before.items())
    assert not project.slot_registered


def test_hook_truncation_keeps_complete_question_for_large_candidate_list(root):
    from ro_hooks import response
    project = Project(root, require_slot=False)
    row = sessions.candidates(project)[0]
    rows = [{**row, "slot": slot} for slot in sessions.ORDER]
    output = response("SessionStart", [], [sessions.decision_summary(project, rows)])
    text = output["hookSpecificOutput"]["additionalContext"]
    assert "Start a new slot for parallel work; Use slot <X>." in text and text.count("?") == 1


def test_several_eligible_slots_require_one_question_without_staleness(root):
    set_slot(root, "A", "released", user="none")
    project, question = start(root)
    assert "Continue slot A" in question and "Candidate B:" in question
    assert "?" in question and "; stale" not in question and not project.slot_registered


def test_unique_nonstale_eligible_slot_uses_automatic_path(root):
    append_events(root, event("2026-10-27 11:00", "A", "none"))
    before = (root / "handoff.md").read_bytes()
    project, question = start(root)
    assert question == "" and project.slot == "B" and project.slot_registered
    assert Project(root, session="new-session").slot == "B"
    assert (root / "handoff.md").read_bytes() == before


@pytest.mark.parametrize("source", ["argument", "environment", "registered"])
def test_named_slot_skips_question_without_implicit_reclaim(root, monkeypatch, source):
    before = (root / "handoff.md").read_bytes()
    if source == "environment":
        monkeypatch.setenv("RO_SLOT", "A")
    if source == "registered":
        Project(root, slot="A", session="named").register_slot()
    project = Project(root, slot="A" if source == "argument" else None, session="named", require_slot=False)
    assert sessions.startup(project) == "" and project.slot == "A"
    assert (root / "handoff.md").read_bytes() == before


@pytest.mark.parametrize("mode", ["away", "no-questions"])
def test_questions_disabled_creates_new_slot_and_records_deferred_choice(root, mode):
    if mode == "away":
        policy = root / "agents.md"
        policy.write_text(policy.read_text(encoding="utf-8").replace("- Autonomy: present", "- Autonomy: away"),
                          encoding="utf-8")
    old_handoff = (root / "handoff.md").read_text(encoding="utf-8")
    old_plan = (root / "plan.md").read_bytes()
    Project(root, slot="A").write_json("jobs.json", [{"id": "J-A-done", "slot": "A", "status": "exited"}])
    old_jobs = (root / ".ro/jobs.json").read_bytes()
    project, question = start(root, questions_allowed=mode != "no-questions", user="operator")
    assert question == "" and project.slot == "C" and project.slot_registered
    handoff = (root / "handoff.md").read_text(encoding="utf-8")
    assert _slot_sections(handoff)["A"] == _slot_sections(old_handoff)["A"]
    assert _slot_sections(handoff)["B"] == _slot_sections(old_handoff)["B"]
    assert "- Active agent(s): A, B, C" in handoff
    assert "started new slot C for parallel work (questions disabled)" in handoff
    assert "stale slots: A" in handoff
    assert (root / "plan.md").read_bytes() == old_plan
    assert (root / ".ro/jobs.json").read_bytes() == old_jobs
    context = brief(Project(root, session="new-session"))
    assert "Session choice: new slot C" in context and "stale slots: A" in context
    assert "Which slot" not in context
    Project(root, session="new-session").register_slot()
    assert "stale slots: A" in brief(Project(root, session="new-session"))
    assert sessions.startup(Project(root, session="new-session")) == ""
    assert (root / "handoff.md").read_text(encoding="utf-8") == handoff


def test_reclaim_choice_logs_once_preserving_claims_resume_state_and_jobs(root):
    project = Project(root, slot="A", session="chosen")
    project.write_json("jobs.json", [{"id": "J-A-old", "slot": "A", "status": "exited"}])
    plan, jobs = (root / "plan.md").read_bytes(), (root / ".ro/jobs.json").read_bytes()
    old_slot = _slot_sections((root / "handoff.md").read_text(encoding="utf-8"))["A"]
    assert sessions.startup(project, reclaim=True, host="local", user="operator") == ""
    text = (root / "handoff.md").read_text(encoding="utf-8")
    slot = _slot_sections(text)["A"]
    assert text.count("- Action: reclaimed slot A after stale session (user choice)") == 1
    assert slot["Current host"] == "local" and slot["Current user"] == "operator"
    assert slot["Resumable state"] == old_slot["Resumable state"] and slot["Next action"] == old_slot["Next action"]
    assert (root / "plan.md").read_bytes() == plan and (root / ".ro/jobs.json").read_bytes() == jobs
    assert Project(root, session="chosen").slot == "A"


@pytest.mark.parametrize("status", ["running", "attention", "starting", "error"])
def test_registry_active_jobs_exclude_stale_and_prevent_reclaim(root, status):
    project = Project(root, slot="A", session="chosen")
    project.write_json("jobs.json", [{"id": "J-A-live", "slot": "A", "status": status}])
    assert not sessions.candidates(project)[0]["stale"]
    with pytest.raises(ValueError, match="without running/attention jobs"):
        sessions.startup(project, reclaim=True)
    other, question = start(root)
    assert not question and other.slot == "B"


@pytest.mark.parametrize("tree_alive,child_alive,protected", [
    (False, True, True), (None, False, True), (False, False, False),
])
def test_failed_runner_ownership_controls_slot_reclaim(root, monkeypatch, tree_alive, child_alive, protected):
    import ro_jobs
    monkeypatch.setattr(ro_jobs, "_live_supervisor", lambda job: False)
    monkeypatch.setattr(ro_jobs, "_live_child", lambda job: child_alive)
    monkeypatch.setattr(ro_jobs, "_tree_alive", lambda job: tree_alive)
    project = Project(root, slot="A", session="failed-runner")
    job = {"id": "J-A-failed", "slot": "A", "status": "launch-failed", "tree_owned": True}
    project.write_json("jobs.json", [job])
    row = sessions.candidates(project)[0]
    assert bool(row["jobs"]) is protected
    assert row["stale"] is not protected
    if protected:
        before = (root / "handoff.md").read_bytes()
        assert job["id"] in sessions.decision_summary(project, [row])
        with pytest.raises(ValueError, match="without running/attention jobs"):
            sessions.startup(project, reclaim=True)
        assert (root / "handoff.md").read_bytes() == before
    else:
        sessions.startup(project, reclaim=True, host="local", user="operator")
        assert _slot_sections((root / "handoff.md").read_text(encoding="utf-8"))["A"]["Current host"] == "local"


@pytest.mark.parametrize("stamp,stale", [("10:00", False), ("09:59", True), ("12:01", False)])
def test_newest_claim_event_and_threshold_boundary(root, stamp, stale):
    set_queue(root, item("H-A-01", f"A since 2026-10-27 {stamp}"))
    assert sessions.candidates(Project(root, require_slot=False))[0]["stale"] is stale


def test_custom_threshold_and_undated_slots_are_not_guessed(root):
    policy = root / "agents.md"
    policy.write_text(policy.read_text(encoding="utf-8").replace("- Stale slot after: 2h", "- Stale slot after: 4h"),
                      encoding="utf-8")
    assert not sessions.candidates(Project(root, require_slot=False))[0]["stale"]
    set_slot(root, "B", "local", user="peer")
    assert not sessions.candidates(Project(root, require_slot=False))[1]["stale"]


def test_older_project_without_setting_uses_default_without_missing_error(root):
    from conftest import check, found
    policy = root / "agents.md"
    policy.write_text(policy.read_text(encoding="utf-8").replace("- Stale slot after: 2h\n", ""), encoding="utf-8")
    project = Project(root, require_slot=False)
    assert project.settings()["stale_slot_after"] == "2h"
    assert sessions.candidates(project)[0]["stale"]
    assert not found(check(root, now=NOW), "ERROR", "settings.missing")


def test_unspecified_intent_with_resumable_work_and_no_eligible_slot_asks(root):
    append_events(root, event("2026-10-27 11:30", "A", "none"))
    set_slot(root, "B", "local", user="peer")
    project, question = start(root)
    assert "Which slot" in question and "; stale" not in question and not project.slot_registered


@pytest.mark.parametrize("intent,slot", [("continue", "A"), ("parallel", "C")])
def test_explicit_intent_overrides_away_without_question(root, intent, slot):
    policy = root / "agents.md"
    policy.write_text(policy.read_text(encoding="utf-8").replace("- Autonomy: present", "- Autonomy: away"),
                      encoding="utf-8")
    project, question = start(root, intent=intent, host="local", user="operator")
    assert not question and project.slot == slot
    if intent == "continue":
        assert "reclaimed slot A" not in (root / "handoff.md").read_text(encoding="utf-8")


def test_cli_brief_decision_and_reclaim_are_wired(root, capsys):
    assert ro.main(["--project", str(root), "--session", "cli", "brief"]) == 0
    assert "Which slot" in capsys.readouterr().out
    assert ro.main(["--project", str(root), "--session", "cli", "--slot", "A", "brief", "--reclaim",
                    "--host", "local", "--user", "operator"]) == 0
    assert "Slot A: taken; claims 1" in capsys.readouterr().out


def test_single_stale_slot_cannot_bypass_choice_with_implicit_mutating_command(tmp_path, monkeypatch):
    monkeypatch.setattr(sessions, "now", lambda: NOW)
    path = unified_project(tmp_path, agents="1")
    append_events(path, event("2026-10-27 08:00", "A", "none"))
    with pytest.raises(ValueError, match="run ro brief"):
        Project(path, session="new")


def test_ambiguous_case_contract_rejects_old_selection_only_guidance(root):
    from types import SimpleNamespace
    from scripts.evals.startup_artifacts import CHECKS
    row = {"mapping": None, "response": "Slot not selected; select a slot with --slot"}
    context = SimpleNamespace(data=lambda _name: {"ambiguous": row})
    check = CHECKS["automatic-session-registration", "03-ambiguous-unregistered.md"]
    assert not check(context)[0]
    row["response"] = start(root)[1]
    assert check(context)[0]


@pytest.mark.parametrize("value", ["0h", "-1h", "nan", "2", "forever"])
def test_invalid_stale_durations_are_rejected(value):
    with pytest.raises(ValueError):
        settings.normalize("stale_slot_after", value, {})


def test_classic_parallel_choice_adds_plan_section(tmp_path, monkeypatch):
    from conftest import make_project
    monkeypatch.setattr(sessions, "now", lambda: NOW)
    path = make_project(tmp_path, "classic", "--preset", "work-project", "--workflow", "classic",
                        "--user", "operator", "--platforms", "local", "--agents", "2")
    project, question = start(path, intent="parallel", user="operator", host="local")
    assert not question and project.slot == "C"
    assert "## Agent: C" in (path / "plan.md").read_text(encoding="utf-8")
    assert "### Agent: C" in (path / "handoff.md").read_text(encoding="utf-8")
