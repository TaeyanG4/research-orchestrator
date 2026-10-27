"""Host scratch lifetime regressions; no installed host is invoked."""

from pathlib import Path
import tempfile

from scripts.host import scratch


def test_plain_mkdir_and_retirement_preserve_evidence(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("protected temporary ACL would exclude the host user")

    monkeypatch.setattr(tempfile, "mkdtemp", forbidden)
    monkeypatch.setattr(tempfile, "TemporaryDirectory", forbidden)
    path = scratch.create_scratch(tmp_path, "probe-")
    (path / "evidence.log").write_text("synthetic evidence", encoding="utf-8")
    retained = scratch.retire_scratch(path)
    assert retained.parent == tmp_path / "done"
    assert not path.exists()
    assert (retained / "evidence.log").read_text() == "synthetic evidence"


def test_retirement_denied_does_not_mask_probe_result(tmp_path, monkeypatch, capsys):
    path = scratch.create_scratch(tmp_path, "probe-")

    def denied(*args, **kwargs):
        raise PermissionError("synthetic sharing violation")

    monkeypatch.setattr(Path, "rename", denied)
    assert scratch.retire_scratch(path) == path
    assert path.exists()
    assert "Scratch retained" in capsys.readouterr().err
