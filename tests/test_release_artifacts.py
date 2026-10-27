"""Light release gates reject broken publication artifacts without launching tests."""
import hashlib
import json
from types import SimpleNamespace
import zipfile

import pytest

from scripts import validate_release as release


@pytest.mark.parametrize("text", ["See ?2.4", "Events 87?88", "A1?A5"])
def test_release_rejects_lost_numeric_reference_characters(tmp_path, text):
    path = tmp_path / "docs" / "nested" / "guide.md"
    path.parent.mkdir(parents=True)
    path.write_text(text, encoding="utf-8")
    errors = []
    release.check_doc_encoding(errors, tmp_path)
    assert len(errors) == 1 and "numeric reference" in errors[0]


def test_release_accepts_unicode_references_and_normal_questions(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "guide.md").write_text("§2.4: A1–A5, Events 87–88. Ready? Yes.\n", encoding="utf-8")
    errors = []
    release.check_doc_encoding(errors, tmp_path)
    assert errors == []


@pytest.mark.parametrize("skip", [False, True])
def test_structural_flag_skips_scenarios_and_pytest_but_keeps_checks(monkeypatch, skip):
    calls = []
    for name in vars(release).copy():
        if name.startswith("check_"):
            monkeypatch.setattr(release, name, lambda *args, _name=name, **kwargs: calls.append(_name))
    monkeypatch.setattr(release, "DOCS", [])
    monkeypatch.setattr(release, "sys", SimpleNamespace(stdout=SimpleNamespace(reconfigure=lambda **kw: None)))
    assert release.main(["--skip-tests"] if skip else []) == 0
    assert {"check_publication", "check_doc_encoding", "check_local_links", "check_examples", "check_core_split"} <= set(calls)
    scenarios = {"check_tests", "check_example", "check_initializer", "check_settings_modes"}
    assert set(calls) & scenarios == (set() if skip else scenarios)


@pytest.mark.parametrize("filename,text", [
    ("p2-builder-prompt.md", "Sanitized instructions."),
    ("merge-build-report.md", "Sanitized results."),
    ("builder-latest.md", "Sanitized results."),
    ("session-report.md", "Sanitized results."),
    ("plans/reviews/phase-fix-report.md", "Sanitized implementation results."),
    ("review.md", "You are the BUILDER in the release repository."),
    ("notes.md", "Session report: coordinator instructions follow."),
])
@pytest.mark.parametrize("archived", [False, True])
def test_release_rejects_session_reports_even_without_private_paths(tmp_path, filename, text, archived):
    docs = tmp_path / "docs"
    docs.mkdir()
    if archived:
        raw = text.encode()
        with zipfile.ZipFile(docs / "evidence.zip", "w") as archive:
            archive.writestr(filename, raw)
            archive.writestr("manifest.json", json.dumps({"files": [
                {"path": filename, "export_sha256": hashlib.sha256(raw).hexdigest()}]}))
    else:
        (docs / filename).parent.mkdir(parents=True, exist_ok=True)
        (docs / filename).write_text(text)
    errors = []
    release.check_publication(errors, tmp_path)
    assert any("internal agent prompt or session report" in error for error in errors)


def test_design_conclusion_and_structured_evidence_remain_public(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "design.md").write_text("# Ownership design\n\nReserve under one lock to avoid competing owners.\n")
    (docs / "builder-coverage.md").write_text("# Coverage\n\n| Cases | Measured |\n| --- | --- |\n| 2 | 0 |\n")
    errors = []
    release.check_publication(errors, tmp_path)
    assert errors == []


def test_local_links_check_fragments_duplicates_unicode_and_fences(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    target = docs / "guide.md"
    target.write_text('# Lookup, `launch`, monitor and stop\n\n## Repeat\n\n## Repeat\n'
                      '\n## 시작\n\n<a id="stable"></a>\n\n```md\n## Not a heading\n```\n', encoding="utf-8")
    readme = tmp_path / "README.md"
    readme.write_text('[Run](docs/guide.md#lookup-launch-monitor-and-stop)\n'
                      '[Repeated](docs/guide.md#repeat-1)\n[Unicode](docs/guide.md#%EC%8B%9C%EC%9E%91)\n'
                      '[Explicit](docs/guide.md#stable)\n[External](https://example.org/#absent)\n'
                      '```md\n[Sample](missing.md)\n```\n', encoding="utf-8")
    errors = []
    release.check_local_links(errors, tmp_path)
    assert errors == []
    readme.write_text('[Old anchor](docs/guide.md#launch-monitor-and-stop)\n'
                      '[Moved](docs/plans/reviews/builder-latest.md)\n', encoding="utf-8")
    release.check_local_links(errors, tmp_path)
    assert len(errors) == 2
    assert "broken local anchor" in errors[0]
    assert "broken local link" in errors[1]
