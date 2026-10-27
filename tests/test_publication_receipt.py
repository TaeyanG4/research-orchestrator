"""Publication receipts remain pending until real final-run results are supplied."""

import importlib.util

import pytest

from conftest import ROOT


SPEC = importlib.util.spec_from_file_location("release_receipt", ROOT / "scripts/validate_release.py")
release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release)
HEADER = ("## Release candidate test receipt\n\n"
          "| Date | Interpreter | Pytest summary | validate_release result | Commit |\n"
          "|---|---|---|---|---|\n")
PLACEHOLDERS = ["<date>", "<interpreter>", "<pytest summary>", "<validate_release result>", "<commit>"]
# Synthetic test data only; this is not a run receipt.
COMPLETE = ["2026-01-01", "Python 3.12", "1 passed in 0.01s", "VALIDATION: PASS", "abcdef0"]


def write_receipt(root, fields):
    path = root / "docs/evals/README.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(HEADER + "| " + " | ".join(fields) + " |\n", encoding="utf-8")


@pytest.mark.parametrize("required", [None, "", "0", "true"])
def test_receipt_is_optional_outside_publication(tmp_path, monkeypatch, required):
    monkeypatch.delenv("RO_RELEASE_RECEIPT_REQUIRED", raising=False)
    if required is not None:
        monkeypatch.setenv("RO_RELEASE_RECEIPT_REQUIRED", required)
    errors = []
    release.check_release_receipt(errors, tmp_path)
    write_receipt(tmp_path, PLACEHOLDERS)
    release.check_release_receipt(errors, tmp_path)
    assert errors == []


@pytest.mark.parametrize("missing", range(5))
@pytest.mark.parametrize("value", ["placeholder", "empty"])
def test_publication_rejects_each_incomplete_field(tmp_path, monkeypatch, missing, value):
    monkeypatch.setenv("RO_RELEASE_RECEIPT_REQUIRED", "1")
    fields = COMPLETE.copy()
    fields[missing] = f"`{PLACEHOLDERS[missing]}`" if value == "placeholder" else ""
    write_receipt(tmp_path, fields)
    errors = []
    release.check_release_receipt(errors, tmp_path)
    assert len(errors) == 1 and "release receipt:" in errors[0]


def test_publication_rejects_missing_receipt_and_header_only(tmp_path, monkeypatch):
    monkeypatch.setenv("RO_RELEASE_RECEIPT_REQUIRED", "1")
    errors = []
    release.check_release_receipt(errors, tmp_path)
    assert len(errors) == 1
    write_receipt(tmp_path, COMPLETE)
    (tmp_path / "docs/evals/README.md").write_text(HEADER, encoding="utf-8")
    errors.clear()
    release.check_release_receipt(errors, tmp_path)
    assert len(errors) == 1


def test_publication_accepts_completed_receipt(tmp_path, monkeypatch):
    monkeypatch.setenv("RO_RELEASE_RECEIPT_REQUIRED", "1")
    write_receipt(tmp_path, COMPLETE)
    errors = []
    release.check_release_receipt(errors, tmp_path)
    assert errors == []
