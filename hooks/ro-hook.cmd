@echo off
setlocal DisableDelayedExpansion
rem Unrelated projects need no interpreter and leave host input untouched.
set "ro_hook_project="
set "ro_hook_dir=%CD%"
call :find_project
if defined ro_hook_project goto project
set "ro_hook_dir=%CLAUDE_PROJECT_DIR%"
call :find_project
if defined ro_hook_project goto project
set "ro_hook_dir=%CODEX_PROJECT_DIR%"
call :find_project
if defined ro_hook_project goto project
echo {}
exit /b 0

:find_project
if not defined ro_hook_dir exit /b 0
for %%P in ("%ro_hook_dir%") do set "ro_hook_dir=%%~fP"
:parent
rem A drive root already ends in a separator; retain any original UNC/device prefix.
set "ro_hook_prefix=%ro_hook_dir%"
if not "%ro_hook_prefix:~-1%"=="\" if not "%ro_hook_prefix:~-1%"=="/" set "ro_hook_prefix=%ro_hook_prefix%\"
if exist "%ro_hook_prefix%agents.md" if not exist "%ro_hook_prefix%agents.md\" (
    set "ro_hook_project=%ro_hook_dir%"
    exit /b 0
)
for %%P in ("%ro_hook_prefix%..") do set "ro_hook_parent=%%~fP"
if "%ro_hook_parent%"=="%ro_hook_dir%" exit /b 0
set "ro_hook_dir=%ro_hook_parent%"
goto parent

:project
rem Keep question/delegation subscriptions installed as policy changes. The
rem shortcut reads agents.md only; the host's stdin stays for the runner.
if "%~1"=="PreToolUse" if "%~2"=="--tool" (
    if "%~3"=="ask" call :policy_quiet "Autonomy" "present"
    if "%~3"=="agent" call :policy_quiet "Brief requirements" "none"
    if "%~3"=="ask" if not errorlevel 1 (echo {} & exit /b 0)
    if "%~3"=="agent" if not errorlevel 1 (echo {} & exit /b 0)
)
rem A missing primary registry is quiet only when recovery state is absent too.
if "%~1"=="Stop" (
    if not exist "%ro_hook_prefix%.ro\jobs.json" if not exist "%ro_hook_prefix%.ro\recovery\jobs.json" (
        echo {}
        exit /b 0
    )
)
if "%~1"=="PostToolUse" (
    call :post_clean
    if not errorlevel 1 (
        echo {}
        exit /b 0
    )
)
rem Edit checks only protect registered jobs; leave stdin untouched on this shortcut.
if "%~1"=="PreToolUse" if "%~2"=="--tool" if "%~3"=="edit" (
    if not exist "%ro_hook_prefix%.ro\jobs.json" if not exist "%ro_hook_prefix%.ro\recovery\jobs.json" (
        echo {}
        exit /b 0
    )
)
rem Installed skill layout (install.py): hooks next to scripts in the skill folder; plugin layout otherwise.
set "runner=%~dp0..\scripts\ro_hook_runner.py"
if not exist "%runner%" set "runner=%~dp0..\skills\research-orchestrator\scripts\ro_hook_runner.py"
set "launcher="
rem Use the configured interpreter for both supervisor and child, even off PATH.
if defined RO_HOOK_PYTHON goto configured
setlocal EnableDelayedExpansion
rem Windows Store placeholders under \WindowsApps\ print a message and exit; skip them.
for %%I in (python3.exe python3.cmd python3.bat python.exe python.cmd python.bat) do (
    set "cand=%%~$PATH:I"
    if defined cand if "!cand:\WindowsApps\=!"=="!cand!" (
        goto run
    )
)
for %%I in (py.exe py.cmd py.bat) do (
    set "cand=%%~$PATH:I"
    if defined cand (
        set "launcher=-3"
        goto resolve_launcher
    )
)
echo hooks inactive: missing Python 3 interpreter 1>&2
echo {}
exit /b 0

:resolve_launcher
rem Resolve py's selected executable so the runner can use its watchdog in process.
for /f "delims=" %%P in ('call "%cand%" -3 -E -S -c "import sys; print(sys.executable)"') do set "resolved=%%P"
if not defined resolved goto unavailable
set "cand=%resolved%"
set "launcher="
goto run

:configured
if exist "%RO_HOOK_PYTHON%" (
    set "cand=%RO_HOOK_PYTHON%"
    goto run
)
:unavailable
echo hooks inactive: configured Python interpreter unavailable 1>&2
echo {}
exit /b 0

:run
setlocal DisableDelayedExpansion
set "RO_HOOK_PYTHON=%cand%"
"%cand%" %launcher% -E -S "%runner%" %* --policy-root "%ro_hook_project%"
exit /b %errorlevel%

:policy_quiet
rem findstr is a Windows utility, independent of Python or the configured PATH.
set "ro_hook_findstr=%SystemRoot%\System32\findstr.exe"
if not exist "%ro_hook_findstr%" exit /b 1
"%ro_hook_findstr%" /i /c:"%~1" "%ro_hook_prefix%agents.md" >nul
if errorlevel 2 exit /b 1
if errorlevel 1 exit /b 0
"%ro_hook_findstr%" /i /c:"%~1" "%ro_hook_prefix%agents.md" | "%ro_hook_findstr%" /i /v /r /c:"^[ ]*-[ ]*%~1:[ ]*%~2[ ]*$" >nul
if errorlevel 2 exit /b 1
if errorlevel 1 exit /b 0
exit /b 1

:post_clean
if "%RO_HOOK_DIAGNOSTICS%"=="1" exit /b 1
set "ro_hook_state=%ro_hook_prefix%.ro"
if exist "%ro_hook_state%\hook-diagnostics.on" exit /b 1
if not exist "%ro_hook_state%\records-hook.ready" exit /b 1
if not exist "%ro_hook_state%\records-hook.json" exit /b 1
set "ro_hook_ready="
for /f "usebackq delims=" %%R in ("%ro_hook_state%\records-hook.ready") do set "ro_hook_ready=%%R"
if not "%ro_hook_ready%"=="records-hook-v1" exit /b 1
for %%R in ("%ro_hook_state%\records-hook.ready") do set "ro_hook_ready_time=%%~tR"
for %%F in (agents.md plan.md discoveries.md handoff.md) do (
    set "ro_hook_source=%ro_hook_prefix%%%F"
    set "ro_hook_name=%%F"
    call :same_stamp
    if errorlevel 1 exit /b 1
)
for %%F in (records-hook.json warnings.log warnings-shown.json) do (
    set "ro_hook_source=%ro_hook_state%\%%F"
    set "ro_hook_name=%%F"
    call :same_stamp
    if errorlevel 1 exit /b 1
)
exit /b 0

:same_stamp
set "ro_hook_stamp=%ro_hook_state%\records-hook-stamps\%ro_hook_name%"
if not exist "%ro_hook_source%" (
    if exist "%ro_hook_stamp%" exit /b 1
    exit /b 0
)
if exist "%ro_hook_source%\" exit /b 1
if not exist "%ro_hook_stamp%" exit /b 1
rem cmd exposes minute precision. A record from the cache's minute stays on the
rem Python path until a later acknowledgement makes the comparison unambiguous.
for %%P in ("%ro_hook_source%") do (
    set "ro_hook_source_time=%%~tP"
    set "ro_hook_source_size=%%~zP"
)
if "%ro_hook_source_time%"=="%ro_hook_ready_time%" exit /b 1
for %%S in ("%ro_hook_stamp%") do if not "%ro_hook_source_time%"=="%%~tS" exit /b 1
set "ro_hook_expected="
for /f "usebackq delims=" %%S in ("%ro_hook_stamp%") do set "ro_hook_expected=%%S"
if not "%ro_hook_source_size%"=="%ro_hook_expected%" exit /b 1
exit /b 0
