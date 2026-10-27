"""Use tiny local processes to exercise the live selection stopping boundary."""
import json
import os
import sys
import time

from scripts.trigger.selection_stream import stream_selection


def run(code, root, timeout=3, callback=lambda events: events[-1].get("selected", False)):
    return stream_selection([sys.executable, "-u", "-c", code], cwd=root, env=os.environ.copy(),
                            timeout=timeout, on_event=callback)


def test_stream_stops_live_owned_child_on_completed_selection(tmp_path):
    started = time.monotonic()
    result = run("import time; print('{\"selected\": true}', flush=True); time.sleep(20)", tmp_path)
    assert result.boundary_event == 1 and not result.timed_out
    assert json.loads(result.stdout)["selected"] is True
    assert time.monotonic() - started < 8


def test_stream_keeps_after_selection_bytes_separate(tmp_path):
    result = run("print('{\"selected\": true}\\n{\"after\": true}', flush=True)", tmp_path)
    assert result.boundary_event == 1
    assert "after" not in result.stdout and json.loads(result.after_selection)["after"]


def test_stream_nonselection_requires_process_completion(tmp_path):
    result = run("print('{\"type\": \"turn.completed\"}')", tmp_path)
    assert result.returncode == 0 and result.boundary_event is None and not result.timed_out


def test_stream_timeout_keeps_partial_events_and_stderr(tmp_path):
    result = run("import sys,time; print('{\"started\": true}', flush=True); "
                 "print('diagnostic', file=sys.stderr, flush=True); time.sleep(20)", tmp_path, timeout=.2)
    assert result.timed_out and result.boundary_event is None
    assert json.loads(result.stdout)["started"] and result.stderr.strip() == "diagnostic"


def test_non_json_event_does_not_hide_subsequent_selection(tmp_path):
    result = run("print('log\\n{\"selected\": true}', flush=True)", tmp_path)
    assert result.boundary_event == 1 and result.stdout.startswith("log\n")
