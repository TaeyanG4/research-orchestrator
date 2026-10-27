# Guard fixture

Use environment linux/bash, Enforcement block and Block shell.background,jobs.mutate-bound. A synthetic running job J-A-0001 binds bound/input.txt; use no real process.

Commands:
- find . -exec rm {} \; &
- cmd ${X} &
- worker --label {first,second} &
- rm bound/${TARGET}.txt &
- rm bound/{input,output}.txt &
- rm bound/input.txt &
- printf '%s' '{literal &}'

Resolve the synthetic bound path against the disposable project directory. Keep the synthetic registry fixture distinct from any live host or real jobs.
