"""Transport regressions from saved iterations; no model sessions or real sleeps."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import threading

import pytest

from scripts.evals import run_evals as runner


TRACE = Path(__file__).parent / "fixtures" / "eval-runfix" / "iteration-4-rate-limit.jsonl"
SERVICE_FAILURES = [
    "Selected model is at capacity. Please try a different model.",
    "unexpected status 503 Service Unavailable: HTTP responses session bridge is cooling down "
    "after repeated upstream timeouts; retry shortly.",
    "unexpected status 502 Bad Gateway: upstream service unavailable.",
    "unexpected status 504 Gateway Timeout: upstream service unavailable.",
]


def test_iteration_4_rate_limit_trace():
    raw = TRACE.read_text(encoding="utf-8")
    assert runner.terminal_transport_category(raw, "") == "rate_limit"
    assert runner.terminal_transport_failure(raw, "")
    assert len(runner.rate_limit_evidence(raw, "")) == 2
    assert not runner.disconnect_evidence(raw, "")


@pytest.mark.parametrize("message", SERVICE_FAILURES)
@pytest.mark.parametrize("prefix", [[], [
    {"type": "error", "message": "Reconnecting... 5/5 (stream disconnected before completion)"},
]])
def test_iteration_6_service_failures_remain_transport_after_disconnect_retries(message, prefix):
    raw = "\n".join(map(json.dumps, [*prefix,
        {"type": "error", "message": message},
        {"type": "turn.failed", "error": {"message": message}},
    ]))
    expected = "rate_limit" if "capacity" in message or "503" in message else "transport"
    assert runner.terminal_transport_category(raw, "Reading additional input from stdin...") == expected
    evidence = runner.rate_limit_evidence if expected == "rate_limit" else runner.disconnect_evidence
    assert evidence(raw, "")[-1]["message"] == message


@pytest.mark.parametrize("message", SERVICE_FAILURES)
@pytest.mark.parametrize("ending", [
    [{"type": "turn.completed"}],
    [{"type": "item.completed", "item": {"type": "agent_message", "text": "Recovered"}}],
    [{"type": "turn.failed", "error": {"message": "Permission denied"}}],
])
def test_service_recovery_and_later_task_failure_are_not_excluded(message, ending):
    raw = "\n".join(map(json.dumps, [{"type": "error", "message": message}, *ending]))
    assert runner.terminal_transport_category(raw, "") is None


@pytest.mark.parametrize("message", SERVICE_FAILURES)
def test_service_error_quoted_by_executor_is_not_a_host_failure(message):
    raw = "\n".join(map(json.dumps, [
        {"type": "item.completed", "item": {"type": "agent_message", "text": message}},
        {"type": "item.completed", "item": {"type": "command_execution", "exit_code": 1,
         "aggregated_output": message}},
    ]))
    assert not runner.disconnect_evidence(raw, "")
    assert runner.terminal_transport_category(raw, "") is None


@pytest.mark.parametrize("status,expected", [
    ({"returncode": 1, "status": "failed", "failure_category": "executor"}, "rate_limit"),
    ({"returncode": 1, "status": "failed", "failure_category": "setup/copy"}, None),
    ({"returncode": 1, "status": "failed", "failure_category": "launch"}, None),
    ({"returncode": None, "status": "timeout", "failure_category": "timeout"}, None),
    ({"returncode": 0, "status": "completed"}, None),
])
def test_saved_service_diagnostic_does_not_override_distinct_failure(tmp_path, status, expected):
    (tmp_path / "events.jsonl").write_text(json.dumps({"type": "turn.failed", "error": {
        "message": SERVICE_FAILURES[0]}}), encoding="utf-8")
    assert runner.saved_transport_category(tmp_path, status) == expected


@pytest.mark.parametrize("message", ["429 Too Many Requests", "rate-limit exceeded", "rate_limit_exceeded",
                                    "Rate limit reached", "You've hit your usage limit", "usage limits reached"])
@pytest.mark.parametrize("kind", ["error", "turn.failed", "item.error", "stderr"])
def test_rate_limit_diagnostics(message, kind):
    event = {"type": "error", "message": message}
    if kind == "turn.failed":
        event = {"type": kind, "error": {"message": message}}
    elif kind == "item.error":
        event = {"type": "item.completed", "item": event}
    raw, stderr = ("", message) if kind == "stderr" else (json.dumps(event), "")
    assert runner.terminal_transport_category(raw, stderr) == "rate_limit"
    assert runner.rate_limit_evidence(raw, stderr)[0]["message"] == message


@pytest.mark.parametrize("ending,stderr", [
    ([{"type": "turn.completed"}], "429 Too Many Requests"),
    ([{"type": "turn.failed", "error": {"message": "Permission denied"}}], "429 Too Many Requests"),
    ([{"type": "item.completed", "item": {"type": "agent_message", "text": "Resumed"}}], ""),
    ([], "429 Too Many Requests\nError: task failed"),
])
def test_rate_limit_recovery_never_replaces_real_failure(ending, stderr):
    raw = TRACE.read_text(encoding="utf-8") + "\n" + "\n".join(map(json.dumps, ending))
    assert runner.terminal_transport_category(raw, stderr) is None


def test_rate_limit_in_agent_text_and_tool_output_is_not_diagnostic():
    raw = "\n".join(map(json.dumps, [
        {"type": "item.completed", "item": {"type": "agent_message", "text": "429 rate limit"}},
        {"type": "item.completed", "item": {"type": "command_execution", "exit_code": 1,
         "aggregated_output": "429 Too Many Requests; Retry-After: 9999"}},
    ]))
    assert not runner.rate_limit_evidence(raw, "")
    assert runner.terminal_transport_category(raw, "") is None


@pytest.mark.parametrize("value,expected", [
    ("Retry-After: 125", 125), ("retry-after: 2.5 seconds", 2.5),
    ({"headers": {"Retry-After": "300"}}, 300), ({"retry_after_seconds": 75}, 75),
    ({"retry_after": 15}, 15), ("retry-after: junk", None), ("Retry-After: -4", None),
    ("Retry-After: Thu, 01 Jan 1970 00:05:00 GMT", 200),
])
def test_retry_after_seconds_and_dates(value, expected, monkeypatch):
    monkeypatch.setattr(runner.time, "time", lambda: 100)
    assert runner.retry_after_seconds(value) == expected


def test_backoff_cap_and_retry_after_minimum():
    clock, waits = [0.0], []

    def sleep(seconds):
        waits.append(seconds)
        clock[0] += seconds

    throttle = runner.RateLimitThrottle(clock=lambda: clock[0], sleep=sleep)
    # The first retry is immediate in a fresh session; later retries back off.
    for attempt, delay in enumerate((0, 0, 0, 60, 120), 1):
        assert throttle.defer([], attempt) == delay
        throttle.wait()
    assert sum(waits) == 180
    raw = json.dumps({"type": "turn.failed", "error": {"message": "429", "retry_after": 400}})
    assert throttle.defer(runner.rate_limit_evidence(raw, ""), 5) == 400
    throttle.wait()
    assert clock[0] == 580
    assert throttle.defer(runner.rate_limit_evidence("", "429 Too Many Requests\nRetry-After: 500"), 4) == 500


def test_shared_gate_pauses_other_workers_and_rechecks_extensions():
    clock = [0.0]
    sleeping, release, launched = threading.Event(), threading.Event(), threading.Event()
    waits = []

    def sleep(seconds):
        waits.append(seconds)
        sleeping.set()
        assert release.wait(5), "test failed to release the fake clock"
        clock[0] += seconds

    throttle = runner.RateLimitThrottle(clock=lambda: clock[0], sleep=sleep)
    throttle.defer([], 4)  # Three fresh sessions have already failed.

    def worker_b():
        throttle.wait()
        launched.set()

    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(worker_b)
        try:
            assert sleeping.wait(5)
            assert not launched.is_set()
            throttle.defer([], 5)  # Another in-flight failure extends the gate.
        finally:
            release.set()
        pending.result(timeout=5)
    assert waits == [60, 60] and launched.is_set()


def test_eval_worker_pool_uses_one_global_gate(tmp_path, monkeypatch):
    (tmp_path / "SKILL.md").write_text("Skill")
    cases = [runner.Case(tmp_path, name, "Prompt", "Result", ()) for name in ("one", "two")]
    monkeypatch.setattr(runner, "load_cases", lambda *args: cases)
    gates = []
    barrier = threading.Barrier(2)

    def run_case(*args, **kwargs):
        gates.append(kwargs["throttle"])
        barrier.wait(timeout=5)
        return {"status": "completed"}

    monkeypatch.setattr(runner, "run_case", run_case)
    monkeypatch.setattr(runner.subprocess, "run", lambda *a, **kw: pytest.fail("No host launch allowed"))
    assert runner.main(["--iteration", "4", "--jobs", "2", "--configs", "with_skill",
                        "--workspace", str(tmp_path / "work"), "--skill-dir", str(tmp_path)]) == 0
    assert len(gates) == 2 and gates[0] is gates[1]


@pytest.mark.parametrize("message,expected", [
    ("You've hit your usage limit. Try again at 3:07 PM.", 3 * 3600 + 7 * 60),
    ("usage limit reached; try again at 11:30", 30 * 60 + 23 * 3600),
    ("rate limited, resets at 12:05 am", 12 * 3600 + 5 * 60),
    ("429 Too Many Requests; try again in 2 hours 5 minutes", 2 * 3600 + 5 * 60),
    ("usage limit: retry in 90 seconds", 90),
    ("429 Too Many Requests", None),
    ("try again at 25:00", None),
])
def test_explicit_reset_time_in_service_message(message, expected):
    now = runner.datetime(2026, 10, 26, 12, 0, 0)
    assert runner.reset_seconds(message, now) == expected


def test_three_fresh_retries_precede_a_stated_reset(monkeypatch):
    throttle = runner.RateLimitThrottle(clock=lambda: 0.0, sleep=lambda seconds: None)
    assert throttle.defer(runner.rate_limit_evidence("", "429 Too Many Requests"), 1) == 0
    monkeypatch.setattr(runner, "reset_seconds", lambda text, now=None: 600.0 if "try again" in text else None)
    raw = json.dumps({"type": "turn.failed", "error": {"message": "usage limit reached; try again at 3:07 PM"}})
    for attempt in (1, 2, 3):
        assert throttle.defer(runner.rate_limit_evidence(raw, ""), attempt) == 0
    assert throttle.defer(runner.rate_limit_evidence(raw, ""), 4) == 600


def test_reset_hint_survives_three_fresh_attempts():
    clock = [0.0]
    throttle = runner.RateLimitThrottle(clock=lambda: clock[0])
    assert throttle.defer([{"retry_after_seconds": 600}], 1) == 0
    clock[0] = 30
    assert throttle.defer([], 2) == 0
    assert throttle.defer([], 3) == 0
    assert throttle.defer([], 4) == 570
