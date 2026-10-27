from pathlib import Path
import sys

with Path("stage-executions.log").open("a", encoding="utf-8") as target:
    target.write(sys.argv[1] + "\n")
print("stage finished")
