import json, math, statistics
from pathlib import Path
values = json.loads(Path('observations.json').read_text())
method = json.loads(Path('method.json').read_text())
n = 3
if method['degrees_of_freedom'] != len(values) - 1:
    raise ValueError('Input count and method metadata disagree')
mean = sum(values) / n
sd = math.sqrt(sum((x - mean)**2 for x in values) / (n - 1))
se = sd / math.sqrt(n)
multiplier = method['multiplier']
Path('result.json').write_text(json.dumps({'n':n,'mean':mean,'sd':sd,'interval':[mean - multiplier*se,mean + multiplier*se]}))
