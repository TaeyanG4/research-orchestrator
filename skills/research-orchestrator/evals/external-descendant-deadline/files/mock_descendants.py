"""Local deadline probe with a delayed effect two generations below the launcher."""
import os
from pathlib import Path
import subprocess
import sys
import time

mode = sys.argv[1]
if mode == "launcher":
    with Path("executions.log").open("a", encoding="utf-8") as stream:
        stream.write("launcher\n")
    print("remote-id: pending-482", flush=True)
    subprocess.Popen([sys.executable, __file__, "child"])
elif mode == "child":
    subprocess.Popen([sys.executable, __file__, "grandchild"])
    time.sleep(30)
elif mode == "grandchild":
    Path("grandchild.pid").write_text(str(os.getpid()), encoding="utf-8")
    time.sleep(3)
    Path("late-effect.txt").write_text("unexpected delayed effect", encoding="utf-8")
else:
    raise SystemExit("choose launcher, child or grandchild")
