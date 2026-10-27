"""Regression coverage for publication bytes, not just archive filenames."""
import hashlib
import base64
import json
import uuid
import zipfile

import pytest

from scripts.evals.export_evidence import export_evidence, sanitize_text
from scripts.publication_safety import native_identifiers, violations
from scripts.validate_release import check_publication


@pytest.mark.parametrize('encoding', ['utf-8', 'utf-16-le'])
@pytest.mark.parametrize('container', ['text', 'json', 'archive'])
def test_publication_rejects_encoded_private_paths(tmp_path, encoding, container):
    token = base64.b64encode(('failure at ' + 'X:/' + 'private/workspace/capture.txt').encode(encoding)).decode()
    docs = tmp_path / 'docs'
    docs.mkdir()
    if container == 'archive':
        raw = json.dumps({'stdout_b64': token}).encode()
        with zipfile.ZipFile(docs / 'captures.zip', 'w') as archive:
            archive.writestr('capture.json', raw)
            archive.writestr('manifest.json', json.dumps({'files': [{'path': 'capture.json',
                'export_sha256': hashlib.sha256(raw).hexdigest()}]}))
    else:
        (docs / ('capture.' + ('json' if container == 'json' else 'md'))).write_text(
            json.dumps({'capture': token}) if container == 'json' else 'capture: ' + token)
    errors = []
    check_publication(errors, tmp_path)
    assert any('absolute host path' in error for error in errors)


@pytest.mark.parametrize('encoding', ['utf-8', 'utf-16-le'])
def test_export_withholds_encoded_streams_and_encoded_free_text(tmp_path, encoding):
    token = base64.b64encode(('failure at ' + 'X:/' + 'private/workspace/capture.txt').encode(encoding)).decode()
    source = tmp_path / 'source'
    source.mkdir()
    (source / 'run.json').write_text(json.dumps({'stdout_b64': token, 'stderr_base64': token,
                                              'notes': 'captured: ' + token, 'passed': False}))
    target = tmp_path / 'docs/safe.zip'
    export_evidence({'saved': source}, target)
    with zipfile.ZipFile(target) as archive:
        data = json.loads(archive.read('saved/run.json'))
        assert data == {'notes': 'captured: <withheld encoded text>', 'passed': False}
    errors = []
    check_publication(errors, tmp_path)
    assert errors == []


def test_encoded_terminal_controls_cannot_hide_paths_or_replace_hashes(tmp_path):
    docs = tmp_path / 'docs'
    docs.mkdir()
    raw = ('\x1b[31mfailure at ' + 'X:/' + 'private/workspace/capture.txt\x00\x08').encode()
    (docs / 'capture.md').write_text(base64.b64encode(raw).decode())
    errors = []
    check_publication(errors, tmp_path)
    assert any('absolute host path' in error for error in errors)
    for digest in ('a' * 64, hashlib.sha256(b'evidence').hexdigest()):
        assert sanitize_text(digest) == digest


@pytest.mark.parametrize("prefix", ["", "Path(r", "alpha", "=", '"'])
@pytest.mark.parametrize("separator", ["/", "//", "///", "\\", "\\\\", "\\/", "/\\"])
def test_adjoining_drive_paths_all_separator_forms(prefix, separator):
    path = "X:" + separator + "private" + separator + "project"
    result = sanitize_text(prefix + path + ")")
    assert path not in result and "private" not in result
    assert not violations(result)


@pytest.mark.parametrize("payload,issue", [
    ("Path(rX:/private/project)", "absolute host path"),
    ("/home/person/private", "absolute host path"),
    ("private-account", "private account name"),
    ('{"thread_id":"01234567-89ab-cdef-0123-456789abcdef"}', "native session"),
    ('{"available_skills":[]}', "inventory"),
    ('{"installed_skills":["private-plugin"]}', "inventory"),
    ('{"type":"thread.started"}', "internal session"),
])
def test_release_scans_inside_archive(tmp_path, payload, issue):
    evidence = tmp_path / "docs" / "evidence.zip"
    evidence.parent.mkdir()
    raw = payload.encode()
    with zipfile.ZipFile(evidence, "w") as archive:
        archive.writestr("grading.json", raw)
        archive.writestr("manifest.json", json.dumps({"files": [{"path": "grading.json", "export_sha256": hashlib.sha256(raw).hexdigest()}]}))
    errors = []
    check_publication(errors, tmp_path, private_names=("private-account",))
    assert any(issue in error and "!grading.json" in error for error in errors)


def test_export_withholds_raw_events_and_inventory_but_preserves_hashes(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    raw = b'{"type":"thread.started","thread_id":"01234567-89ab-cdef-0123-456789abcdef"}'
    (source / "events.jsonl").write_bytes(raw)
    (source / "run.json").write_text(json.dumps({"status": "timeout", "isolation": {"available_skills": ["private"]},
        "contamination": {"raw_accesses": ["private tool history"]}, "commands": ["private invocation"]}))
    (source / "grading.json").write_text('{"excluded":true,"expectations":[]}')
    target = tmp_path / "docs" / "safe.zip"
    manifest = export_evidence({"original": source}, target)
    assert manifest["omitted"][0]["source_sha256"] == hashlib.sha256(raw).hexdigest()
    with zipfile.ZipFile(target) as archive:
        assert json.loads(archive.read("original/run.json")) == {"status": "timeout"}
    errors = []
    check_publication(errors, tmp_path)
    assert errors == []


def test_private_case_directory_names_are_sanitized_in_members_and_manifest(tmp_path):
    source = tmp_path / "source"
    private = source / "private-account"
    private.mkdir(parents=True)
    (private / "grading.json").write_text('{"expectations":[]}')
    target = tmp_path / "public.zip"
    export_evidence({"original": source}, target, private_terms=("private-account",))
    with zipfile.ZipFile(target) as archive:
        assert all("private-account" not in name for name in archive.namelist())
        assert b"private-account" not in archive.read("manifest.json")


def test_release_decodes_json_commands_without_losing_real_path_detection(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    summary = docs / "host.md"
    summary.write_text('```json\n' + json.dumps(["Execute this command:\nprint('safe')"]) + '\n```')
    errors = []
    check_publication(errors, tmp_path)
    assert errors == []
    summary.write_text('```json\n' + json.dumps([r"Path(rX:\private\task)"]) + '\n```')
    check_publication(errors, tmp_path)
    assert any("absolute host path" in error for error in errors)


# Shaped like captured Codex output; derived values look real but identify nothing.
REALISTIC = [str(uuid.UUID(hashlib.sha256(seed).hexdigest()[:32])) for seed in (b"thread", b"request")]
NATIVE_LINES = [
    '{"type":"thread.started","thread_id":"%s"}',
    '{"type":"error","message":"429 Too Many Requests, request id: %s"}',
    '{"session_id": "%s", "turn_id": "x"}',
    '"{\\"conversation_id\\":\\"%s\\"}"',
    'requestId=%s',
]


@pytest.mark.parametrize("location", ["tests/fixtures/eval-runfix", "examples/demo/.ro",
                                      "skills/research-orchestrator/evals/case/files"])
@pytest.mark.parametrize("line", NATIVE_LINES)
def test_release_rejects_non_synthetic_native_ids_outside_docs(tmp_path, location, line):
    target = tmp_path / location / "capture.jsonl"
    target.parent.mkdir(parents=True)
    target.write_text(line % REALISTIC[0] + "\n" + line % REALISTIC[1].replace("-", "") + "\n")
    errors = []
    check_publication(errors, tmp_path)
    assert len(errors) == 1 and "non-synthetic native session/request identifier" in errors[0]
    assert REALISTIC[0] not in errors[0]


@pytest.mark.parametrize("value", ["00000000-0000-7000-8000-000000000003", "00000000-0000-4000-8000-000000000004",
                                   "01234567-89ab-cdef-0123-456789abcdef", "0" * 31 + "1"])
def test_release_allows_synthetic_native_ids_in_fixtures_but_not_docs(tmp_path, value):
    fixture = tmp_path / "tests" / "fixtures" / "trace.jsonl"
    fixture.parent.mkdir(parents=True)
    fixture.write_text("\n".join(line % value for line in NATIVE_LINES))
    errors = []
    check_publication(errors, tmp_path)
    assert errors == []
    assert native_identifiers("thread_id: " + value) == []
    if "-" in value:
        (tmp_path / "docs").mkdir()
        (tmp_path / "docs" / "trace.md").write_text("thread_id: " + value)
        check_publication(errors, tmp_path)
        assert any("native session/tool identifier" in error for error in errors)


def test_shipped_fixtures_and_examples_carry_only_synthetic_native_ids():
    from pathlib import Path
    errors = []
    check_publication(errors, Path(__file__).resolve().parents[1])
    assert not [error for error in errors if "non-synthetic native" in error]
