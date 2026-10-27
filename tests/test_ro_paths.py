"""Literal path identity, uncertain paths and operational setting boundaries."""

from __future__ import annotations

import time

import pytest

from ro_checks import Call, inside, normal_path, outcome, pre_checks
import ro_settings as settings


def test_declared_windows_drive_slashes_case_and_trailing_separator_have_same_identity():
    for spelling in (r"H:\work\Input", "H:/work/Input/", r"h:\WORK\INPUT\\", "h:/work/../work/input"):
        assert normal_path(spelling, "H:/work", "windows") == "h:/work/input"


@pytest.mark.parametrize("os_family", ["linux", "macos"])
def test_declared_posix_paths_preserve_case_and_backslashes(os_family):
    assert normal_path("./one/../Input/", "/work", os_family) == "/work/Input"
    assert normal_path(r"run\input", "/work", os_family) == r"/work/run\input"
    assert normal_path("H:/Input", "/work", os_family) == "/work/H:/Input"
    assert normal_path("/work/Input", "/elsewhere", os_family) != normal_path("/work/input", "/elsewhere", os_family)


def test_copy_basenames_and_trailing_separators_follow_declared_os():
    jobs = [{"status": "running", "bound": ["/work/output/input.txt"]}]
    values = {"environment": "linux/bash"}
    for command in (r"cp -t output 'folder\input.txt'", "cp input.txt 'output\\'"):
        assert pre_checks(Call("shell", "bash", command), "/work", jobs, values) == [], command
    findings = pre_checks(Call("shell", "bash", "cp -t output input.txt"), "/work", jobs, values)
    assert findings and all(not finding.uncertain for finding in findings)
    values["environment"] = "windows/bash"
    jobs[0]["bound"] = ["D:/work/output/input.txt"]
    findings = pre_checks(Call("shell", "bash", r"cp -t output 'folder\input.txt'"), "D:/work", jobs, values)
    assert findings and all(not finding.uncertain for finding in findings)


def test_component_comparison_does_not_confuse_siblings_with_shared_prefix():
    assert inside("h:/work/run/input", "h:/work/run")
    assert inside("h:/work/run", "h:/work/run")
    assert not inside("h:/work/runner", "h:/work/run")
    assert not inside("h:/work/run-copy/input", "h:/work/run")


@pytest.mark.parametrize("os_family,target,blocked", [
    ("windows", r"D:\WORK\RUN\input.txt", True),
    ("windows", "d:/work/run/input.txt", True),
    ("linux", "/work/run/input.txt", True),
    ("linux", "/work/RUN/input.txt", False),
    ("macos", "/work/run/input.txt", True),
    ("macos", r"/work/run\input.txt", False),
])
def test_tool_path_checks_follow_declared_os_independently_of_host(os_family, target, blocked):
    root = "D:/work" if os_family == "windows" else "/work"
    jobs = [{"status": "running", "run_dir": root + "/run", "bound": []}]
    values = {"environment": f"{os_family}/bash", "enforcement": "block", "block": "jobs.mutate-bound"}
    findings = pre_checks(Call("Write", paths=[target]), root, jobs, values)
    assert any(outcome(f, values) == "block" for f in findings) is blocked


def test_dynamic_variable_and_glob_paths_are_uncertain_and_cannot_block(tmp_path):
    values = {"enforcement": "block", "block": "jobs.mutate-bound"}
    jobs = [{"id": "J-A-01", "status": "running", "bound": [str(tmp_path / "run")],
             "run_dir": str(tmp_path / "run")}]
    for spelling in ("$INPUT/result.txt", "${INPUT}/result.txt", "%INPUT%/result.txt",
                     "run/*.json", "run/file?.txt", "run/[ab].txt"):
        assert normal_path(spelling, tmp_path) is None
        findings = pre_checks(Call("Write", paths=[spelling]), tmp_path, jobs, values)
        assert findings and all(finding.uncertain for finding in findings)
        assert all(outcome(finding, values) == "warn" for finding in findings)


def test_block_accepts_every_specified_check_id():
    assert set(settings.CHECK_IDS) == {
        "shell.background", "shell.detach", "shell.heredoc", "shell.cd", "jobs.mutate-bound",
        "jobs.read-bound", "jobs.unmonitored", "records.timestamp", "records.id", "publish.scan",
        "external.gate", "ask.away", "brief.requirements",
    }
    for check in settings.CHECK_IDS:
        values = settings.resolve({"block": check}, None, {})
        assert values["block"] == check


def test_block_rejects_unknown_or_duplicate_identifiers():
    for raw in ("shell.unknown", "shell.background,shell.background"):
        with pytest.raises(ValueError):
            settings.resolve({"block": raw}, None, {})


@pytest.mark.parametrize("patterns", [
    ("(a+)+", "(a*){2}", "(a?)+"), ("(?=a)a",), (r"(a)\1",), ("a" * 257,), ("[",),
], ids=["nested-quantifiers", "lookaround", "backreference", "size-limit", "invalid-syntax"])
def test_user_regex_rejects_unbounded_or_unsupported_grammar(patterns):
    for pattern in patterns:
        with pytest.raises(ValueError):
            settings.safe_regex(pattern)


@pytest.mark.parametrize("setting,value", [("external_actions", "regex:(a+)+"),
                                             ("publish_scan", "regex:(a+)+")])
def test_settings_reject_unsafe_regex_in_each_pattern_consumer(setting, value):
    with pytest.raises(ValueError):
        settings.resolve({setting: value}, None, {})


def test_user_regex_accepts_bounded_literal_alternation():
    assert settings.safe_regex(r"token_[a-z0-9]{8,32}|key_[A-Z]{12}").fullmatch("token_abcdefgh")


@pytest.mark.parametrize("patterns", [
    ("a*a*a*a*b", "a+a+b"), ("a{1,256}a{1,256}b",), ("a{1,999999}",),
    ("(a|aa)+b",), ("a.*b",), ("a{1,2}?a?b",),
], ids=["unbounded-sequence", "combined-bounds", "excessive-bound", "overlapping-branches", "wildcard", "lazy"])
def test_pathological_user_patterns_are_rejected_before_evaluation(patterns):
    for pattern in patterns:
        start = time.monotonic()
        with pytest.raises(ValueError):
            settings.safe_regex(pattern)
        assert time.monotonic() - start < .1


def test_restricted_pattern_linear_failure_on_large_input():
    pattern = settings.safe_regex("a{1,64}b")
    start = time.monotonic()
    assert pattern.search("a" * 1000000) is None
    assert time.monotonic() - start < 1


@pytest.mark.parametrize("spelling", ["msys", "unc"])
def test_windows_path_translation_is_out_of_scope(tmp_path, spelling):
    entry = {"status": "running", "bound": []}
    values = {"environment": "windows/bash", "enforcement": "block", "block": "jobs.mutate-bound"}
    if spelling == "msys":
        entry["run_dir"] = "D:/workspace/runs/job-a"
        entry["bound"] = [entry["run_dir"]]
        target = "/d/workspace/runs/job-a/input.txt"
    else:
        entry["run_dir"] = "//storage/share/runs/job-a"
        entry["bound"] = [entry["run_dir"]]
        target = r"\\storage\share\runs\job-a\input.txt"
    findings = pre_checks(Call("shell", "bash", f"rm '{target}'"), tmp_path, [entry], values)
    assert all(outcome(finding, values) != "block" for finding in findings)
