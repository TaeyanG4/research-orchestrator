"""Compare real parsers against fenced documentation examples without changing the project."""

import json
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(sys.argv[1]).resolve()))
from check_project import Checker
import ro_settings
from ro_state import Project

source = Path("agents.md").read_text(encoding="utf-8")
results = {}
for name, opening, closing, inner in (
    ("tilde", "~~~markdown", "~~~", "```"),
    ("long-backtick", "````markdown", "````", "```"),
    ("long-tilde", "~~~~~", "~~~~~~", "~~~"),
):
    sample = "## Project settings\n- Enforcement: off\n- Block: none\n## Project rules\n"
    example = f"{opening}\n{sample}{inner}\n{sample}{closing}\n"
    text = source.replace("## Project settings\n", example + "## Project settings\n", 1)
    with tempfile.TemporaryDirectory(prefix="policy-probe-") as directory:
        root = Path(directory)
        (root / "agents.md").write_text(text, encoding="utf-8", newline="\n")
        checker = Checker(root)
        checker.check_settings(text)
        parsers = {"shared": ro_settings.read_settings(text).values, "checker": checker.values}
        try:
            parsers["runtime"] = Project(root).settings(required=True)
        except (OSError, ValueError) as error:
            parsers["runtime"] = {"error": type(error).__name__}
        results[name] = {parser: {key: values.get(key) for key in ("enforcement", "block")}
                         for parser, values in parsers.items()}
Path("policy.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
print(json.dumps(results, sort_keys=True))
