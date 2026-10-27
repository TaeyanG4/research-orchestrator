"""Owned job lifecycles, monitoring signals and confirmation before durable events."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import shlex
import signal
import subprocess
import sys
import time
import threading
from types import SimpleNamespace

import pytest

from conftest import with_real_ps
import ro_jobs as jobs
import ro_state as state
import ro_records as records
from ro_checks import normal_path, path_checks
from ro_state import Project, process_start, same_process

HANDOFF = ("# Handoff\n\n## Active handoff\n\n"
           "### Agent: A\n- Current host: Claude Code\n- Current user: owner\n\n"
           "### Agent: B\n- Current host: Codex\n- Current user: owner\n\n"
           "## Completed / review log\n\n## Archived history\n")


@pytest.fixture
def project(tmp_path, monkeypatch):
    root = tmp_path / "job's workspace"
    root.mkdir()
    (root / "handoff.md").write_text(HANDOFF, encoding="utf-8")
    (root / "plan.md").write_text("# Plan\n## Agent: A\n" + "".join(
        f"### {item}\n- Goal: run the bounded test worker\n"
        for item in ("H-A-01", "H-A-02", "H-A-03")) +
        "## Agent: B\n### H-B-01\n- Goal: run the bounded test worker\n", encoding="utf-8")
    project = Project(root, slot="A", session="author-session")
    children, popen = [], subprocess.Popen

    def start(*args, **kwargs):
        child = popen(*args, **kwargs)
        children.append(child)
        return child

    monkeypatch.setattr(subprocess, "Popen", start)
    try:
        yield project
    finally:
        cleanup(project)
        for child in children:
            child.wait(timeout=10)  # Reap runners before deleting their open logs.
        # Runners launched by a subprocess are outside the local Popen spy.
        # Tree termination can precede the child's final log-handle release.
        for entry in project.read_json("jobs.json", []):
            child = entry.get("child", {})
            if child.get("pid") and child.get("start"):
                wait_for(lambda: not same_process(child["pid"], child["start"]))


def options(command: list[str], **values) -> argparse.Namespace:
    defaults = dict(cmd=command, item="H-A-01", expect="30s", confirm="0.1s", run_dir=None,
                    bind=[], input=[], error=[], heartbeat=None, max_silence="20m", require_receipt=None)
    defaults.update(values)
    return argparse.Namespace(**defaults)


def stored(project: Project) -> dict:
    return project.read_json("jobs.json", [])[-1]


def cleanup(project: Project) -> None:
    for entry in project.read_json("jobs.json", []):
        if jobs.running_job(entry):
            jobs.kill(project, entry["id"])


def test_short_exit_is_never_recorded_as_launched(project) -> None:
    result = jobs.launch(project, options([sys.executable, "-c", "import time; time.sleep(3)"], confirm="3.5s"))
    assert (project.root / "handoff.md").read_text(encoding="utf-8") == HANDOFF
    assert stored(project)["exit_code"] == 0
    assert stored(project)["confirmed"] is False
    assert "Next: " + jobs.monitor_command(project, stored(project)["id"]) in result


def test_confirmation_records_an_event_and_auto_binds_the_script_and_run_dir(project) -> None:
    run_dir = project.root / "run"
    run_dir.mkdir()
    script = run_dir / "worker.py"
    script.write_text("import time\ntime.sleep(30)\n", encoding="utf-8")
    result = jobs.launch(project, options([sys.executable, str(script)], run_dir=str(run_dir)))
    entry = stored(project)
    assert entry["id"] in result and entry["confirmed"] is True
    assert "Next: " + jobs.monitor_command(project, entry["id"]) in result
    assert "monitor until it finishes, record the outcome, then close" in result
    assert "Launch confirmation is not completion" in result and "handoff.md" in result
    os_family = project.settings()["environment"].split("/")[0]
    expected = {normal_path(str(path), project.root, os_family) for path in (run_dir, script)}
    bound = {normal_path(value, project.root, os_family) for value in entry["bound"]}
    assert expected <= bound
    assert entry["id"] in (project.root / "handoff.md").read_text(encoding="utf-8")
    with pytest.raises(ValueError, match="conflicts"):
        jobs.launch(project, options([sys.executable, "-c", "pass"], run_dir=str(run_dir)))


@pytest.mark.parametrize("run_dir", [None, ".", ".."])
def test_launch_without_run_dir_does_not_bind_project_root(project, run_dir) -> None:
    script = project.root / "worker.py"
    script.write_text("import time\ntime.sleep(30)\n", encoding="utf-8")
    inputs = project.root / "inputs"
    inputs.mkdir()
    result = jobs.launch(project, options([sys.executable, str(script)], run_dir=run_dir, bind=["inputs"]))
    entry = stored(project)
    os_family = project.settings()["environment"].split("/")[0]
    expected = {normal_path(str(path), project.root, os_family) for path in (script, inputs)}
    assert {normal_path(value, project.root, os_family) for value in entry["bound"]} == expected
    assert "Notice: project root is not bound" in result
    for path in ("plan.md", "handoff.md", "discoveries.md", "inputs-extra/data.txt"):
        assert path_checks([path], "jobs.mutate-bound", project.root, [entry], os_family) == []
    for path in ("worker.py", "inputs/data.txt"):
        findings = path_checks([path], "jobs.mutate-bound", project.root, [entry], os_family)
        assert len(findings) == 1 and findings[0].check == "jobs.mutate-bound"
        assert not findings[0].uncertain
    # An exclusive binding still conflicts; a shared script alone does not (next test).
    with pytest.raises(ValueError, match="conflicts"):
        jobs.launch(project, options([sys.executable, str(script)], bind=["inputs"]))


def test_parallel_jobs_share_read_inputs_but_never_exclusive_outputs(project) -> None:
    (project.root / "plan.md").write_text("# Plan\n\n## Agent: A\n" + "\n".join(
        f"### H-A-0{number} — trial\n- Parallel: YES\n" for number in range(1, 4)), encoding="utf-8")
    script = project.root / "worker.py"
    script.write_text("import time\ntime.sleep(30)\n", encoding="utf-8")
    for name in ("data", "run-a", "run-b", "run-c"):
        (project.root / name).mkdir()
    os_family = project.settings()["environment"].split("/")[0]
    jobs.launch(project, options([sys.executable, str(script)], run_dir="run-a", input=["data"]))
    first = stored(project)
    assert {normal_path(value, project.root, os_family) for value in first["inputs"]} == {
        normal_path(str(path), project.root, os_family) for path in (script, project.root / "data")}
    # Same script and same read-only data in another run directory: a normal parallel trial.
    jobs.launch(project, options([sys.executable, str(script)], item="H-A-02", run_dir="run-b", input=["data"]))
    assert len(project.read_json("jobs.json", [])) == 2
    # Inputs stay protected from mutation while either job runs.
    assert path_checks(["data/table.csv"], "jobs.mutate-bound", project.root, [first], os_family)
    for conflicting in (dict(run_dir="run-a"), dict(run_dir="run-c", bind=["data"]),
                        dict(run_dir="run-c", bind=["worker.py"]), dict(run_dir="run-c", input=["run-a"])):
        with pytest.raises(ValueError, match="conflicts"):
            jobs.launch(project, options([sys.executable, "-c", "pass"], item="H-A-03", **conflicting))
    assert len(project.read_json("jobs.json", [])) == 2


def test_legacy_registry_bindings_stay_exclusive(project) -> None:
    script = project.root / "worker.py"
    script.write_text("pass\n", encoding="utf-8")
    (project.root / "run").mkdir()
    legacy = {"id": "J-A-0001", "slot": "A", "status": "running", "pid": os.getpid(),
              "start": state.process_start(os.getpid()), "run_dir": str(project.root / "run"),
              "bound": [str(project.root / "run"), str(script)]}
    project.write_json("jobs.json", [legacy])
    try:
        with pytest.raises(ValueError, match="conflicts"):
            jobs.launch(project, options([sys.executable, str(script)], item="H-A-02"))
    finally:
        project.write_json("jobs.json", [])  # The entry borrows this test process's identity.


@pytest.mark.parametrize("binding", [".", ".."])
def test_launch_refuses_explicit_project_root_or_ancestor_binding(project, binding) -> None:
    with pytest.raises(ValueError, match="project root or its ancestor"):
        jobs.launch(project, options([sys.executable, "-c", "pass"], bind=[binding]))
    assert project.read_json("jobs.json", []) == []


def test_legacy_project_root_binding_does_not_lock_coordination_files(project) -> None:
    entry = {"status": "running", "run_dir": str(project.root),
             "bound": [str(project.root), str(project.root / "worker.py")]}
    assert path_checks(["handoff.md"], "jobs.mutate-bound", project.root, [entry]) == []
    assert path_checks(["worker.py"], "jobs.mutate-bound", project.root, [entry])


@pytest.mark.parametrize("shell", ["bash", "powershell"] if os.name == "nt" else ["bash"])
def test_monitor_reports_completion_and_releases_its_identity(project, shell) -> None:
    project.slot = "B"
    (project.root / "agents.md").write_text("## Project settings\n"
        f"- Environment: {'windows' if os.name == 'nt' else 'linux'}/{shell}\n", encoding="utf-8")
    output = jobs.launch(project, options([sys.executable, "-c", "import time; time.sleep(.5)"],
                                          item="H-B-01", confirm="0s"))
    command = next(line.removeprefix("Next: ") for line in output.splitlines() if line.startswith("Next: "))
    # Execute the printed command from elsewhere, including the quoted project path and non-default slot.
    argv = (["powershell", "-NoProfile", "-NonInteractive", "-Command", command]
            if shell == "powershell" else shlex.split(command))
    result = subprocess.run(argv, cwd=project.root.parent, capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    assert "Job: J-B-0001; item H-B-01; outcome: process exited with code 0" in result.stdout
    assert stored(project)["exit_code"] == 0
    assert stored(project)["monitor"]["active"] is False
    assert stored(project)["monitor"]["reason"] == "process exited with code 0"
    assert stored(project)["monitor"]["ended"] >= stored(project)["monitor"]["since"]
    assert stored(project)["status"] == "finished"
    assert "monitor outcome recorded" in jobs.jobs(project)


def test_detached_runner_survives_the_launching_cli_exit(project) -> None:
    code = ("import argparse,sys; sys.path.insert(0,sys.argv[1]); "
            "from ro_state import Project; from ro_jobs import launch; "
            "print(launch(Project(sys.argv[2],slot='A'),argparse.Namespace(item='H-A-01',expect='30s',confirm='0s',"
            "cmd=[sys.executable,'-c','import time; time.sleep(30)'])))")
    result = subprocess.run([sys.executable, "-c", code, str(Path(jobs.__file__).parent), str(project.root)],
                            capture_output=True, text=True, encoding="utf-8", timeout=10)
    assert result.returncode == 0, result.stderr
    assert stored(project)["id"] in result.stdout and stored(project)["confirmed"]
    assert jobs.running_job(stored(project))


def test_monitor_reports_an_error_after_confirmation(project) -> None:
    jobs.launch(project, options([sys.executable, "-u", "-c",
                                  "import time; time.sleep(.3); print('fatal'); time.sleep(30)"],
                                 error=["fatal"], confirm="0s"))
    assert jobs.monitor(project, stored(project)["id"])
    assert stored(project)["status"] == "error"
    assert jobs.running_job(stored(project))
    assert not jobs.live_monitor(stored(project))


def test_error_pattern_prevents_launch_event_and_keeps_live_bindings(project) -> None:
    result = jobs.launch(project, options([sys.executable, "-u", "-c",
                                         "import time; print('worker fatal'); time.sleep(30)"],
                                        error=["worker fatal"], confirm="0.5s", bind=["input.txt"]))
    # Polling sees an exact configured signature; its contents never enter the output.
    assert stored(project)["status"] == "error" and not stored(project)["confirmed"]
    assert "Next: " + jobs.monitor_command(project, stored(project)["id"]) in result
    assert "worker fatal" not in result
    assert (project.root / "handoff.md").read_text(encoding="utf-8") == HANDOFF
    assert jobs.running_job(stored(project))
    with pytest.raises(ValueError, match="conflicts"):
        jobs.launch(project, options([sys.executable, "-c", "pass"], bind=["input.txt"]))


@pytest.mark.parametrize("signal_name", ["heartbeat", "overrun"])
def test_monitor_reports_missing_heartbeat_or_twice_expected_duration(project, signal_name) -> None:
    jobs.launch(project, options([sys.executable, "-c", "import time; time.sleep(30)"], confirm="0s"))
    entry = stored(project)
    entry["started"] = time.time() - 10
    if signal_name == "heartbeat":
        entry.update(heartbeat=str(project.root / "heartbeat"), max_silence=1, expect=30)
    else:
        entry.update(expect=1)
    project.write_json("jobs.json", [entry])
    result = jobs.monitor(project, entry["id"])
    assert ("heartbeat" if signal_name == "heartbeat" else "duration") in result
    assert stored(project)["monitor"]["active"] is False
    assert jobs.running_job(stored(project))


def test_no_heartbeat_path_means_no_heartbeat_failure(project) -> None:
    jobs.launch(project, options([sys.executable, "-c", "import time; time.sleep(30)"]))
    entry = stored(project)
    entry.update(started=time.time() - 10, max_silence=.01)
    assert jobs._condition(entry) is None


def test_reused_pid_is_marked_finished_and_never_killed(project, monkeypatch) -> None:
    entry = {"id": "J-A-0001", "item": "H-A-01", "slot": "A", "pid": os.getpid(),
             "start": "a-different-start-time", "status": "running", "bound": []}
    project.write_json("jobs.json", [entry])
    called = []
    monkeypatch.setattr(jobs.subprocess, "run", with_real_ps(lambda *args, **kwargs: called.append(args)))
    with pytest.raises(ValueError, match="identity changed"):
        jobs.kill(project, entry["id"])
    assert called == []
    assert "finished" in jobs.jobs(project)
    assert "monitor outcome missing" in jobs.jobs(project, prune=True)
    jobs.monitor(project, entry["id"])
    assert "No jobs" in jobs.jobs(project, prune=True)


def test_kill_terminates_only_the_owned_job_tree(project) -> None:
    child_file = project.root / "child.json"
    program = ("import json,subprocess,sys,time; "
               "p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)']); "
               "open(sys.argv[1],'w').write(json.dumps({'pid':p.pid})); time.sleep(30)")
    jobs.launch(project, options([sys.executable, "-c", program, str(child_file)]))
    deadline = time.monotonic() + 5
    while not child_file.exists() and time.monotonic() < deadline:
        time.sleep(.02)
    import json
    child = json.loads(child_file.read_text(encoding="utf-8"))["pid"]
    child_start = process_start(child)
    assert child_start is not None
    entry = stored(project)
    assert "tree killed" in jobs.kill(project, entry["id"])
    deadline = time.monotonic() + 3
    while same_process(child, child_start) and time.monotonic() < deadline:
        time.sleep(.02)
    assert not same_process(child, child_start)
    assert same_process(os.getpid(), process_start(os.getpid()))


@pytest.mark.parametrize("launcher_exits", [False, True])
def test_supervisor_crash_keeps_tree_bindings_and_claims_until_safe_kill(project, launcher_exits):
    worker = project.root / "crash-worker.py"
    worker.write_text("import pathlib,time\nwhile not pathlib.Path('finish').exists():\n    time.sleep(.05)\n", encoding="utf-8")
    program = ("import json,subprocess,sys,time; p=subprocess.Popen([sys.executable,'crash-worker.py']); "
               "open('crash-worker.json','w').write(json.dumps({'pid':p.pid})); "
               f"time.sleep({.15 if launcher_exits else 30})")
    jobs.launch(project, options([sys.executable, "-c", program], confirm="0.4s", bind=["input.txt"]))
    entry = stored(project)
    child_pid = json.loads((project.root / "crash-worker.json").read_text(encoding="utf-8"))["pid"]
    child_start = process_start(child_pid)
    os.kill(entry["pid"], signal.SIGTERM)  # Crash only the supervisor, leaving its owned children alive.
    wait_for(lambda: not same_process(entry["pid"], entry["start"]))
    assert same_process(child_pid, child_start)
    assert "attention" in jobs.jobs(project)
    current = stored(project)
    assert current["orphaned"] and "ended" not in current and jobs.running_job(current)
    assert records.running_jobs(project) == [current]
    assert path_checks(["input.txt"], "jobs.mutate-bound", project.root, [current])
    with pytest.raises(ValueError, match="conflicts"):
        jobs.launch(project, options([sys.executable, "-c", "pass"], bind=["input.txt"]))
    with pytest.raises(ValueError, match="running job"):
        records.release(project, "H-A-01")
    assert "supervisor exited" in jobs.monitor(project, entry["id"])
    assert "taken; running jobs 1" in records.close(project)
    assert "Current host: Claude Code" in (project.root / "handoff.md").read_text(encoding="utf-8")
    assert entry["id"] in jobs.jobs(project, prune=True)
    assert "tree killed" in jobs.kill(project, entry["id"])
    wait_for(lambda: not same_process(child_pid, child_start))
    assert not jobs.running_job(stored(project))
    assert "tree killed" in jobs.monitor(project, entry["id"])
    assert "Slot A: released" in records.close(project)


def test_unverified_orphan_tree_stays_protected_without_signalling_recycled_processes(project, monkeypatch):
    entry = {"id": "J-A-0001", "item": "H-A-01", "slot": "A", "pid": 123,
             "start": "old", "status": "running", "tree_owned": True}
    monkeypatch.setattr(jobs, "_live_supervisor", lambda _: False)
    monkeypatch.setattr(jobs, "_live_child", lambda _: False)
    monkeypatch.setattr(jobs, "_tree_alive", lambda _: None)
    jobs._refresh(entry)
    assert entry["orphaned"] and entry["status"] == "attention"
    assert jobs.running_job(entry)
    project.write_json("jobs.json", [entry])
    monkeypatch.setattr(jobs, "os", SimpleNamespace(name="posix", getpgid=lambda pid: pid))
    monkeypatch.setattr(jobs, "same_process", lambda *_: False)
    with pytest.raises(ValueError, match="identity cannot be established"):
        jobs.kill(project, entry["id"])
    project.write_json("jobs.json", [])  # This synthetic identity never owned a real process.


@pytest.mark.parametrize("empty, expected", [(False, None), (True, False)])
def test_missing_windows_job_name_is_not_proof_of_tree_termination(monkeypatch, empty, expected):
    monkeypatch.setattr(jobs, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(jobs, "_windows_tree_alive", lambda _: False)
    entry = {"tree_owned": True, "tree_empty": empty, "windows_job": "owned-test-tree", "ended": 123}
    assert jobs._tree_alive(entry) is expected


@pytest.mark.parametrize("terminal", [{"tree_empty": True}, {"status": "finished", "ended": 123, "exit_code": 0}])
def test_verified_terminal_tree_is_not_revived_by_reused_group_id(monkeypatch, terminal):
    monkeypatch.setattr(jobs, "os", SimpleNamespace(name="posix"))
    monkeypatch.setattr(jobs, "_group_members", lambda _: [99])
    monkeypatch.setattr(jobs, "same_process", lambda *_: False)
    entry = {"pid": 99, "start": "old", "tree_owned": True, **terminal}
    assert jobs._tree_alive(entry) is False
    assert not jobs.running_job(entry)


@pytest.mark.parametrize("host,user", [("released", "none"), ("unassigned", "owner"),
                                       ("Claude Code", "none"), ("ro", "owner"), ("", "owner")])
def test_free_or_incomplete_slot_refuses_launch_before_any_reservation(project, host, user):
    text = HANDOFF.replace("Current host: Claude Code", "Current host: " + host).replace("Current user: owner", "Current user: " + user)
    (project.root / "handoff.md").write_text(text, encoding="utf-8")
    with pytest.raises(ValueError, match="taken host and user"):
        jobs.launch(project, options([sys.executable, "-c", "pass"]))
    assert project.read_json("jobs.json", []) == []
    assert project.read_json("job-sequence.json", None) is None
    assert (project.root / "handoff.md").read_text(encoding="utf-8") == text


def test_record_launch_never_invents_missing_host_or_user(project):
    (project.root / "handoff.md").write_text("# Handoff\n", encoding="utf-8")
    with pytest.raises(ValueError, match="taken host and user"):
        jobs._record_launch(project, {"slot": "A"})
    assert (project.root / "handoff.md").read_text(encoding="utf-8") == "# Handoff\n"


def wait_for(predicate, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if predicate():
                return
        except PermissionError:
            # A Windows atomic replacement can briefly exclude a test reader.
            # Retry only during this bounded observation window; persistent
            # access errors still fail on the final assertion below.
            if os.name != 'nt':
                raise
        time.sleep(.02)
    assert predicate()


@pytest.mark.parametrize("terminate", [False, True])
def test_parent_exit_preserves_descendant_ownership_and_bindings(project, terminate) -> None:
    worker = project.root / "worker.py"
    worker.write_text("import pathlib, time\n"
                      "while not pathlib.Path('finish').exists():\n    time.sleep(.05)\n", encoding="utf-8")
    launcher = ("import json,subprocess,sys,time; "
                "p=subprocess.Popen([sys.executable,'worker.py']); "
                "open('child.json','w').write(json.dumps({'pid':p.pid})); time.sleep(.2)")
    result = jobs.launch(project, options([sys.executable, "-c", launcher], confirm="0.4s",
                                          bind=["input.txt"]))
    entry = stored(project)
    child = json.loads((project.root / "child.json").read_text(encoding="utf-8"))["pid"]
    child_start = process_start(child)
    try:
        assert child_start is not None
        assert entry.get("child_ended") and not jobs._live_child(entry)
        assert jobs.running_job(entry) and "ended" not in entry
        assert entry["status"] == "running" and not entry["confirmed"]
        assert "still supervised" in result
        os_family = project.settings()["environment"].split("/")[0]
        assert path_checks(["input.txt"], "jobs.mutate-bound", project.root, [entry], os_family)
        with pytest.raises(ValueError, match="conflicts"):
            jobs.launch(project, options([sys.executable, "-c", "pass"], bind=["input.txt"]))
        monitor = subprocess.Popen([sys.executable, str(Path(jobs.__file__).with_name("ro.py")),
                                    "--project", str(project.root), "--slot", "A", "monitor", entry["id"]],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        wait_for(lambda: jobs.live_monitor(stored(project)))
        assert monitor.poll() is None and not jobs.monitor_outcome(stored(project))
        if terminate:
            assert "tree killed" in jobs.kill(project, entry["id"])
        else:
            (project.root / "finish").touch()
        output, errors = monitor.communicate(timeout=10)
        assert monitor.returncode == 0, errors
        assert ("tree killed" if terminate else "code 0") in output
        wait_for(lambda: not same_process(child, child_start))
        assert stored(project)["status"] == ("killed" if terminate else "finished")
        assert jobs.monitor_outcome(stored(project))
    finally:
        (project.root / "finish").touch()
        if child_start:
            wait_for(lambda: not same_process(child, child_start))


@pytest.mark.parametrize("signal_name", ["heartbeat", "error", "overrun"])
def test_monitor_recovers_after_repair_and_retains_incident_history(project, signal_name) -> None:
    program = ("import pathlib,time\n"
               "print('fatal', flush=True)\n"
               "while not pathlib.Path('finish').exists():\n    time.sleep(.05)\n")
    jobs.launch(project, options([sys.executable, "-c", program], confirm="0s"))
    entry = stored(project)
    if signal_name == "heartbeat":
        entry.update(started=time.time() - 10, heartbeat=str(project.root / "heartbeat"), max_silence=1)
    elif signal_name == "overrun":
        entry.update(started=time.time() - 10, expect=1)
    else:
        entry["errors"] = ["fatal"]
    project.write_json("jobs.json", [entry])
    first = jobs.monitor(project, entry["id"])
    reason = {"heartbeat": "heartbeat silence", "error": "error pattern matched",
              "overrun": "2x expected duration exceeded"}[signal_name]
    assert reason in first
    first_incident = stored(project)["incidents"][0].copy()
    if signal_name != "error":
        # Restarting alone cannot resolve a condition that is still present.
        assert reason in jobs.monitor(project, entry["id"])
        assert stored(project)["incidents"] == [first_incident]
    if signal_name == "heartbeat":
        (project.root / "heartbeat").touch()
        jobs._update(project, entry["id"], max_silence=30)
    elif signal_name == "overrun":
        jobs._update(project, entry["id"], expect=30)
    monitor = subprocess.Popen([sys.executable, str(Path(jobs.__file__).with_name("ro.py")),
                                "--project", str(project.root), "--slot", "A", "monitor", entry["id"]],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        wait_for(lambda: jobs.live_monitor(stored(project)) and stored(project)["status"] == "running")
        assert monitor.poll() is None
        incident = stored(project)["incidents"][0]
        assert incident["observed"] == first_incident["observed"] and incident["reason"] == reason
        assert incident["resolved"] >= incident["observed"]
        (project.root / "finish").touch()
        output, errors = monitor.communicate(timeout=10)
        assert monitor.returncode == 0, errors
        assert "process exited with code 0" in output
        assert stored(project)["status"] == "finished"
        assert jobs.monitor_outcome(stored(project))
        assert stored(project)["incidents"] == [incident]
    finally:
        (project.root / "finish").touch()


def test_dead_launcher_reservation_recovers_without_adopting_a_process(project) -> None:
    project.write_json("jobs.json", [{"id": "J-A-0001", "item": "H-A-01", "slot": "A", "pid": None,
                                     "status": "starting", "bound": [str(project.root)],
                                     "launcher": {"pid": os.getpid(), "start": "old-start"}}])
    assert "launch-failed" in jobs.jobs(project)
    result = jobs.launch(project, options([sys.executable, "-c", "import time; time.sleep(30)"]))
    assert stored(project)["id"] == "J-A-0002" and stored(project)["confirmed"]
    assert "J-A-0002" in result


def test_monitor_live_identity_is_required(project) -> None:
    entry = {"monitor": {"pid": os.getpid(), "start": process_start(os.getpid()), "active": True}}
    assert jobs.live_monitor(entry)
    entry["monitor"]["start"] = "reused"
    assert not jobs.live_monitor(entry)


def test_command_registry_is_redacted_and_jobs_never_prints_it(project) -> None:
    jobs.launch(project, options([sys.executable, "-c", "import time; time.sleep(30)",
                                  "--token=private-value"]))
    entry = stored(project)
    assert "private-value" not in entry["command"]
    assert "token" not in jobs.jobs(project)


def test_command_storage_removes_github_fine_grained_and_temporary_aws_tokens(project) -> None:
    secrets = ["github_pat_" + "aB9_" * 20, "ASIA" + "A1" * 8]
    jobs.launch(project, options([sys.executable, "-c", "import time; time.sleep(30)", *secrets]))
    command = stored(project)["command"]
    assert command.count("[REDACTED]") == 2
    assert all(secret not in (project.state / "jobs.json").read_text(encoding="utf-8") for secret in secrets)
    assert "time.sleep(30)" in command


@pytest.mark.parametrize("value", ["0s", "-1h", "1fortnight", "999999999999999h", "nan"])
def test_invalid_duration_is_refused(value) -> None:
    with pytest.raises(ValueError):
        jobs.duration(value)


def test_log_error_pattern_can_cross_a_chunk_boundary(tmp_path) -> None:
    log = tmp_path / "worker.log"
    log.write_bytes(b"x" * (jobs.LOG_SCAN_BYTES - 3) + b"fatal worker")
    entry = {"log": str(log), "errors": ["fatal worker"]}
    assert not jobs._error_match(entry)
    assert jobs._error_match(entry)


def test_consumed_log_error_does_not_recur_but_new_error_still_matches(tmp_path) -> None:
    log = tmp_path / "worker.log"
    log.write_text("fatal\n", encoding="utf-8")
    entry = {"log": str(log), "errors": ["fatal"]}
    assert jobs._error_match(entry)
    assert not jobs._error_match(entry)
    with log.open("a", encoding="utf-8") as output:
        output.write("normal\nfatal\n")
    assert jobs._error_match(entry)
    assert not jobs._error_match(entry)


@pytest.mark.parametrize("split", [1, 2, 4, 5])
@pytest.mark.parametrize("complete", [False, True])
def test_multibyte_error_crosses_reads_and_reports_each_occurrence_once(tmp_path, monkeypatch, split, complete):
    monkeypatch.setattr(jobs, "LOG_SCAN_BYTES", 7)
    error = "실패"
    log = tmp_path / "worker.log"
    log.write_bytes(b"x" * (7 - split) + error.encode("utf-8"))
    entry = {"log": str(log), "errors": [error]}
    if not complete:
        assert not jobs._error_match(entry)
        assert entry["scan_utf8_pending"]
        entry = json.loads(json.dumps(entry))  # A later CLI resumes persisted decoder state.
    assert jobs._error_match(entry, complete=complete)
    assert not jobs._error_match(entry, complete=complete)
    with log.open("ab") as output:
        output.write(b"\n" + error.encode("utf-8"))
    assert jobs._error_match(entry, complete=complete)
    assert not jobs._error_match(entry, complete=complete)


@pytest.mark.parametrize("split", [1, 2, 4, 5])
def test_multibyte_error_finishes_after_short_read_and_empty_poll(tmp_path, split):
    error = "실패"
    data = error.encode("utf-8")
    log = tmp_path / "worker.log"
    log.write_bytes(data[:split])
    entry = {"log": str(log), "errors": [error]}
    assert not jobs._error_match(entry, complete=True)
    assert not jobs._error_match(entry, complete=True)
    entry = json.loads(json.dumps(entry))
    with log.open("ab") as output:
        output.write(data[split:])
    assert jobs._error_match(entry, complete=True)
    assert not jobs._error_match(entry, complete=True)


@pytest.mark.parametrize("member, expected", [("23 20 S\n", True), ("23 20 Z\n", False),
                                               ("23 99 S\n", False)])
def test_posix_group_liveness_excludes_supervisor_zombies_and_unrelated_processes(monkeypatch, member, expected):
    monkeypatch.setattr(jobs, "os", SimpleNamespace(name="posix", getpgrp=lambda: 20, getpid=lambda: 20))

    def inspect(command, **kwargs):
        assert kwargs["start_new_session"] is True
        return SimpleNamespace(returncode=0, stdout="20 20 S\n" + member)

    monkeypatch.setattr(jobs.subprocess, "run", inspect)
    assert jobs._owned_descendants(None) is expected


def test_failed_group_inspection_is_not_reported_as_an_empty_group(monkeypatch):
    monkeypatch.setattr(jobs, "os", SimpleNamespace(name="posix", getpgrp=lambda: 20))
    monkeypatch.setattr(jobs.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(returncode=1))
    with pytest.raises(OSError, match="cannot inspect owned process group"):
        jobs._owned_descendants(None)


def alter_runner(monkeypatch, *, spawn_delay=0, exit_delay=0) -> None:
    """Patch only our detached runner's child spawn/wait, across its process boundary."""
    original_popen = jobs.subprocess.Popen
    code = (
        "import sys,time\n"
        "sys.path.insert(0,sys.argv[1])\n"
        "import ro_jobs\n"
        "original=ro_jobs.subprocess.Popen\n"
        "def altered(*args,**kwargs):\n"
        "    if 'cwd' not in kwargs:\n"
        "        return original(*args,**kwargs)\n"
        f"    time.sleep({spawn_delay!r})\n"
        "    child=original(*args,**kwargs)\n"
        "    original_wait=child.wait\n"
        "    def wait(*args,**kwargs):\n"
        "        result=original_wait(*args,**kwargs)\n"
        f"        time.sleep({exit_delay!r})\n"
        "        return result\n"
        "    child.wait=wait\n"
        "    return child\n"
        "ro_jobs.subprocess.Popen=altered\n"
        "sys.exit(ro_jobs._runner(sys.argv[2],sys.argv[3]))\n"
    )

    def launch_runner(command, *args, **kwargs):
        if "--runner" in command:
            command = [sys.executable, "-c", code, str(Path(jobs.__file__).parent), *command[-2:]]
        return original_popen(command, *args, **kwargs)

    monkeypatch.setattr(jobs.subprocess, "Popen", launch_runner)


def test_prune_then_relaunch_preserves_sequence_and_isolates_logs(project) -> None:
    jobs.launch(project, options([sys.executable, "-u", "-c",
                                 "import time; print('old-failure'); time.sleep(.4)"], confirm="0s"))
    first = stored(project)
    jobs.monitor(project, first["id"])
    original_log = Path(first["log"]).read_bytes()
    assert b"old-failure" in original_log
    assert jobs.jobs(project, prune=True) == "No jobs."
    assert project.read_json("job-sequence.json")["last"] == 1
    result = jobs.launch(project, options([sys.executable, "-u", "-c",
                                          "import time; print('new-log'); time.sleep(30)"],
                                         error=["old-failure"], confirm="0.2s"))
    second = stored(project)
    assert second["id"] == "J-A-0002" and second["confirmed"]
    assert second["id"] in result
    assert first["log"] != second["log"]
    assert Path(first["log"]).read_bytes() == original_log
    assert b"old-failure" not in Path(second["log"]).read_bytes()


def test_pruning_legacy_registry_preserves_its_high_water_mark(project) -> None:
    project.write_json("jobs.json", [{"id": "J-A-0017", "item": "H-A-01", "status": "finished"}])
    assert "monitor outcome missing" in jobs.jobs(project, prune=True)
    jobs.monitor(project, "J-A-0017")
    assert jobs.jobs(project, prune=True) == "No jobs."
    assert project.read_json("job-sequence.json") == {"last": 17}
    jobs.launch(project, options([sys.executable, "-c", "import time; time.sleep(30)"], confirm="0s"))
    assert stored(project)["id"] == "J-A-0018"


@pytest.mark.parametrize("confirm", ["0s", "0.2s"])
def test_confirmation_requires_successful_child_start_even_after_delayed_spawn(project, monkeypatch, confirm) -> None:
    alter_runner(monkeypatch, spawn_delay=.5)
    jobs.launch(project, options([str(project.root / "missing-executable")], confirm=confirm))
    assert stored(project)["confirmed"] is False
    assert stored(project)["status"] == "launch-failed"
    assert (project.root / "handoff.md").read_text(encoding="utf-8") == HANDOFF


def test_confirmation_interval_starts_after_delayed_child_start(project, monkeypatch) -> None:
    alter_runner(monkeypatch, spawn_delay=.5)
    jobs.launch(project, options([sys.executable, "-c", "import time; time.sleep(.15)"], confirm="0.3s"))
    assert stored(project)["confirmed"] is False
    assert stored(project)["exit_code"] == 0


def test_live_supervisor_cannot_confirm_an_exited_child(project, monkeypatch) -> None:
    alter_runner(monkeypatch, exit_delay=.5)
    jobs.launch(project, options([sys.executable, "-c", "import time; time.sleep(.15)"], confirm="0.3s"))
    assert stored(project)["confirmed"] is False
    assert stored(project)["exit_code"] == 0


def test_post_launch_supervisor_exception_keeps_bindings_before_any_refresh(project):
    """A real child outlives an exception injected after its durable registration."""
    run = project.root / "failed-supervisor"
    run.mkdir()
    entry = {"id": "J-A-0001", "item": "H-A-01", "slot": "A", "session": project.session,
             "status": "starting", "pid": None, "run_dir": str(run), "bound": [str(run)],
             "windows_job": "Local\\ro-test-" + __import__("uuid").uuid4().hex if os.name == "nt" else None,
             "log": str(project.root / "runner.log")}
    project.write_json("jobs.json", [entry])
    # Fail only the runner's own poll. Patching the shared time module also broke the macOS
    # identity lookup (subprocess waits for `ps` with time.sleep) before registration.
    code = ("import sys, time, types; sys.path.insert(0,sys.argv[1]); import ro_jobs\n"
            "def fail_after_start(_): raise RuntimeError('injected post-launch supervisor failure')\n"
            "ro_jobs.time=types.SimpleNamespace(time=time.time,monotonic=time.monotonic,sleep=fail_after_start)\n"
            "sys.exit(ro_jobs._runner(sys.argv[2],sys.argv[3]))\n")
    flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS if os.name == "nt" else 0
    with Path(entry["log"]).open("wb") as output:
        child = subprocess.Popen([sys.executable, "-c", code, str(Path(jobs.__file__).parent),
                                  str(project.root), entry["id"]], stdin=subprocess.PIPE,
                                 stdout=output, stderr=output, creationflags=flags,
                                 start_new_session=os.name != "nt")
        child.communicate(json.dumps([sys.executable, "-c", "import time; time.sleep(30)"]).encode(), timeout=10)
    assert child.returncode == 1
    failed = stored(project)  # No jobs/monitor/launch refresh has run.
    assert failed["status"] == "launch-failed" and failed["child_started"]
    assert jobs.running_job(failed) and jobs.protected_job(failed)
    findings = path_checks([str(run / "result.txt")], "jobs.mutate-bound", project.root, [failed])
    assert len(findings) == 1 and not findings[0].uncertain
    with pytest.raises(ValueError, match="bound path conflicts"):
        jobs.launch(project, options([sys.executable, "-c", "pass"], run_dir=str(run)))


def test_failed_supervisor_unverified_tree_keeps_binding(monkeypatch, tmp_path):
    failed = {"status": "launch-failed", "tree_owned": True, "bound": [str(tmp_path / "run")]}
    monkeypatch.setattr(jobs, "_tree_alive", lambda _: None)
    assert jobs.protected_job(failed)
    assert path_checks(["run/result.txt"], "jobs.mutate-bound", tmp_path, [failed])
    monkeypatch.setattr(jobs, "_tree_alive", lambda _: False)
    assert not jobs.protected_job(failed)
    assert path_checks(["run/result.txt"], "jobs.mutate-bound", tmp_path, [failed]) == []


def test_shared_protection_predicate_releases_proven_dead_identity(monkeypatch, tmp_path):
    monkeypatch.setattr(jobs, "same_process", lambda *_: False)
    entry = {"status": "running", "pid": 99999999, "start": "old", "bound": [str(tmp_path / "run")]}
    assert not jobs.protected_job(entry)
    assert path_checks(["run/result.txt"], "jobs.mutate-bound", tmp_path, [entry]) == []
    entry.pop("pid")
    entry.pop("start")
    assert jobs.protected_job(entry)  # A legacy ownership assertion is unverified, not disproven.


def test_two_launch_contenders_atomically_reserve_the_same_resource(project):
    barrier = threading.Barrier(2)
    for name in ("left", "right"):
        (project.root / name).mkdir()

    def contender(number):
        owner = Project(project.root, slot="A", session=f"contender-{number}")
        barrier.wait(timeout=5)
        try:
            return jobs.launch(owner, options([sys.executable, "-c", "import time; time.sleep(30)"],
                                              item=f"H-A-0{number + 1}", run_dir=("left", "right")[number], confirm="0s"))
        except ValueError as exc:
            return str(exc)

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(contender, range(2)))
    assert sum("compute reservation conflicts" in result for result in results) == 1
    entries = project.read_json("jobs.json")
    assert len(entries) == 1 and entries[0]["confirmed"]
    assert entries[0]["compute"] == {"machine": jobs.platform.node().casefold(), "resource": "CPU", "parallel": False}


@pytest.mark.parametrize("resource,prior_resource,parallel,prior_parallel,conflict", [
    ("CPU", "CPU", False, True, True), ("CPU", "CPU", True, False, True),
    ("CPU", "CPU", True, True, False), ("CPU", "GPU", False, False, False),
    ("EITHER", "GPU", False, False, True), ("GPU", "EITHER", False, False, True),
])
def test_compute_conflict_respects_resources_and_both_parallel_flags(resource, prior_resource, parallel, prior_parallel, conflict):
    request = {"machine": "machine-a", "resource": resource, "parallel": parallel}
    reserved = {"machine": "machine-a", "resource": prior_resource, "parallel": prior_parallel}
    assert jobs._compute_conflict(request, {"compute": reserved}) is conflict
    reserved["machine"] = "machine-b"
    assert not jobs._compute_conflict(request, {"compute": reserved})


def test_compute_handoff_claims_block_unregistered_work(project):
    handoff = project.root / "handoff.md"
    handoff.write_text(HANDOFF.replace("## Active handoff", "## Shared state\n"
        "- Active compute: CPU — B (H-B-01, since 2026-10-05 18:20)\n\n## Active handoff"), encoding="utf-8")
    with pytest.raises(ValueError, match="handoff claim"):
        jobs.launch(project, options([sys.executable, "-c", "pass"]))
    assert project.read_json("jobs.json", []) == []


def test_compute_handoff_claims_scope_machine_and_parallel_permission(project):
    handoff = project.root / "handoff.md"
    handoff.write_text(HANDOFF.replace("## Active handoff", "## Shared state\n"
        "- Active compute: CPU@elsewhere — B (H-B-01, since 2026-10-05 18:20)\n\n## Active handoff"), encoding="utf-8")
    request = {"machine": "local-machine", "resource": "CPU", "parallel": False}
    jobs._check_compute_claims(project, "H-A-01", request)
    handoff.write_text(HANDOFF.replace("## Active handoff", "## Shared state\n"
        "- Active compute: CPU — B (H-B-01, since 2026-10-05 18:20)\n\n## Active handoff"), encoding="utf-8")
    (project.root / "plan.md").write_text("## Agent: B\n### H-B-01\n- Parallel: YES\n", encoding="utf-8")
    with pytest.raises(ValueError, match="handoff claim"):
        jobs._check_compute_claims(project, "H-A-01", request)
    request["parallel"] = True
    jobs._check_compute_claims(project, "H-A-01", request)


def test_resource_reservation_reads_only_live_item_routing(project):
    (project.root / "plan.md").write_text(
        "# Plan\n\n```markdown\n## Agent: A\n### H-A-01\n- Resource: GPU\n- Parallel: YES\n```\n\n"
        "## Agent: A\n### H-A-01\n- Resource: CPU\n- Parallel: NO\n- Stages: s2 bounded check\n", encoding="utf-8")
    request = jobs._compute_request(project, "H-A-01/s2")
    assert request["resource"] == "CPU" and request["parallel"] is False


def test_zero_confirmation_records_a_live_child_identity(project) -> None:
    result = jobs.launch(project, options([sys.executable, "-c", "import time; time.sleep(30)"], confirm="0s"))
    entry = stored(project)
    assert entry["id"] in result and entry["confirmed"]
    assert entry["child_started"] >= entry["started"]
    assert same_process(entry["child"]["pid"], entry["child"]["start"])


class MissingProc:
    def __truediv__(self, value):
        return self

    def exists(self):
        return False

    def read_text(self, **kwargs):
        raise FileNotFoundError("no proc filesystem")


def bsd_process(monkeypatch, status):
    """Exercise the real BSD fallback without depending on the test host's OS."""
    monkeypatch.setattr(state, "os", SimpleNamespace(name="posix", kill=lambda *_: None))
    monkeypatch.setattr(state, "Path", lambda *_: MissingProc())
    def ps(command, **kwargs):
        return SimpleNamespace(returncode=0, stdout=f"Sun Oct 25 12:00:00 2026 {status[0]}\n")

    monkeypatch.setattr(subprocess, "run", ps)


def test_bsd_process_identity_ignores_changing_status(monkeypatch):
    status = ["R+"]
    bsd_process(monkeypatch, status)
    start = state.process_start(12345)
    assert start == "Sun Oct 25 12:00:00 2026"
    status[0] = "Ss"
    assert state.same_process(12345, start)
    assert not state._owner_dead({"pid": 12345, "start": start})


@pytest.mark.parametrize("status", ["Z", "Z+", "X"])
def test_bsd_zombie_status_is_checked_separately(monkeypatch, status):
    bsd_process(monkeypatch, [status])
    assert state.process_start(12345) is None
    assert state._owner_dead({"pid": 12345, "start": "Sun Oct 25 12:00:00 2026"})


@pytest.mark.parametrize("final_text", ["fatal", "normal"])
def test_completed_job_scans_all_remaining_log_bytes(project, final_text):
    prefix = b"already checked\n"
    log = project.root / "worker.log"
    log.write_bytes(prefix + b"x" * (jobs.LOG_SCAN_BYTES + 1) + final_text.encode())
    entry = {"id": "J-A-0001", "item": "H-A-01", "slot": "A", "status": "finished",
             "outcome": "process exited with code 0", "exit_code": 0, "log": str(log),
             "errors": ["fatal"], "scan_offset": len(prefix), "pid": os.getpid(),
             "start": "different creation time", "ended": time.time() - 1}
    project.write_json("jobs.json", [entry])
    result = jobs.monitor(project, entry["id"])
    current = stored(project)
    assert current["scan_offset"] == log.stat().st_size
    assert current["status"] == ("error" if final_text == "fatal" else "finished")
    assert ("error pattern matched" in result) is (final_text == "fatal")
    assert current["monitor"]["active"] is False
    assert "monitor outcome recorded" in jobs.jobs(project)
    assert "monitor outcome recorded" in jobs.jobs(project)


def test_kill_refuses_another_slots_job(project) -> None:
    jobs.launch(project, options([sys.executable, "-c", "import time; time.sleep(30)"]))
    owner = project.slot
    project.slot = "B"
    with pytest.raises(ValueError, match="belongs to slot A"):
        jobs.kill(project, stored(project)["id"])
    assert jobs.running_job(stored(project))
    project.slot = owner


def test_idle_monitor_backs_off_and_writes_only_changes(project, monkeypatch) -> None:
    jobs.launch(project, options([sys.executable, "-c", "import time; time.sleep(1.5)"], expect="10s"))
    writes, sleeps = [], []
    write_json, sleep = project.write_json, time.sleep
    monkeypatch.setattr(project, "write_json", lambda name, data: (writes.append(name), write_json(name, data)))
    monkeypatch.setattr(jobs.time, "sleep", lambda seconds: (sleeps.append(seconds), sleep(seconds)))
    assert "process exited with code 0" in jobs.monitor(project, stored(project)["id"])
    assert len(writes) <= 4  # Monitor start, exit and outcome; never one write per poll.
    assert max(sleeps) > jobs.POLL_SECONDS and max(sleeps) <= jobs.MAX_POLL_SECONDS
    assert jobs._poll_bound({"started": time.time(), "expect": 0.05}) == jobs.POLL_SECONDS
