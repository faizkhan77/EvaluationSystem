# run_evaluations.ps1
# ====================
# Wrapper invoked by the Windows Scheduled Task (see the Register-ScheduledTask
# setup) so evaluation runs automatically on a timer instead of needing someone
# to launch run_evaluations.py by hand. Still fully decoupled from IRIS India
# itself — this only ever reads already-ingested traces back out of
# Langfuse; a failure here can't affect a live IRIS response.
#
# Deliberately does NOT redirect python.exe's output with `*>`/`2>&1` here —
# in PowerShell 5.1, redirecting a native executable's stderr wraps every
# line in a NativeCommandError and makes the task look failed even when the
# script exits 0 (Python's logging module writes to stderr by default).
# run_evaluations.py writes its own log file directly instead (scheduled_logs/
# run_evaluations.log) — nothing to redirect here at all.
#
# --hours 1 with the 15-minute recurring trigger gives a wide safety margin:
# even if one run is delayed or fails outright, the next run's 1-hour
# look-back still catches anything missed. Each scorer's own de-duplication
# means nothing gets double-scored regardless.

Set-Location $PSScriptRoot

& "$PSScriptRoot\.venv\Scripts\python.exe" run_evaluations.py --hours 1
exit $LASTEXITCODE
