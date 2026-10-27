"""Setup briefs are data, with explicit CLI choices taking precedence."""

import json
import pytest
from conftest import init, rs


@pytest.mark.parametrize("as_file", [False, True])
def test_answers_complete_setup_and_flags_override(tmp_path, as_file):
    answers = {"preset": "competition-solo", "name": "analysis", "user": "operator",
               "competition": "hub/project", "phase_clock": "2026-10-01,2026-12-01",
               "external_actions": "none", "environment": "linux/bash", "language": "fr",
               "platforms": "local", "ordering": "queue"}
    source = json.dumps(answers)
    if as_file:
        path = tmp_path / "answers.json"
        path.write_text(source, encoding="utf-8")
        source = str(path)
    assert init.main([str(tmp_path), "--answers", source, "--language", "en"]) == 0
    stored = rs.read_settings((tmp_path / "agents.md").read_text(encoding="utf-8")).values
    assert stored["competition"] == "hub/project" and stored["language"] == "en"
    assert stored["platforms"] == "local"
    assert "Ordering: queue" in (tmp_path / "plan.md").read_text(encoding="utf-8").splitlines()


@pytest.mark.parametrize("answers", ['{"force": "true"}', '{"language": 3}', '["en"]',
                                     '{"ordering": "random"}', '{invalid', '{"target": "elsewhere"}'])
def test_invalid_answers_write_nothing(tmp_path, answers):
    assert init.main([str(tmp_path), "--answers", answers]) == 2
    assert list(tmp_path.iterdir()) == []


def test_missing_answers_error_supplies_json_option_and_complete_example(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(rs, "detect_host", lambda: "local")
    monkeypatch.setattr(rs, "detect_environment", lambda: "linux/bash")
    assert init.main([str(tmp_path), "--preset", "competition-solo"]) == 2
    error = capsys.readouterr().err
    assert "--answers <json>" in error
    example = error.split("Example: ", 1)[1].strip()
    import shlex
    argv = shlex.split(example)[2:]
    argv[0] = str(tmp_path)
    assert init.main(argv) == 0


@pytest.mark.parametrize("marker,value", [("ANTIGRAVITY_SESSION_ID", "session"),
                                         ("ANTIGRAVITY_AGENT", "1"), ("TERM_PROGRAM", "Antigravity")])
def test_antigravity_host_wins_over_generic_gemini_marker(monkeypatch, marker, value):
    monkeypatch.setenv(marker, value)
    monkeypatch.setenv("GEMINI_API_KEY", "fixture")
    assert rs.detect_host() == "Antigravity"
    assert rs.resolve({}, None, {}, new_project=True)["platforms"] == "Antigravity"
