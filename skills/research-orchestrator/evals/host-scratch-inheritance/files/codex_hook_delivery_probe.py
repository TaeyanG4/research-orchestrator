from pathlib import Path
import subprocess
import tempfile


def run(temp_parent, host="mock-host"):
    with tempfile.TemporaryDirectory(prefix="probe-", dir=temp_parent) as temporary:
        root = Path(temporary)
        for case in ("benign", "unmonitored-stop"):
            project = root / case
            project.mkdir()
            subprocess.run([host], cwd=project, check=False)
            (project / ".ro" / "sessions").mkdir(parents=True, exist_ok=True)
