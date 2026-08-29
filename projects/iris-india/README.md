# IRIS India Evaluator

Standalone Python project (own venv, own deps) that reads already-ingested
IRIS India traces back out of the self-hosted Langfuse instance and writes
quality/format scores onto them. Runs completely decoupled from IRIS India
itself — a crash or slowness here can never affect a live response.

## Setup

```
uv venv -p 3.11
uv pip install -r requirements.txt
cp .env.example .env   # fill in the iris-india project's own API keys
```

## Usage

```
.venv/Scripts/python.exe run_evaluations.py --hours 24
```

Pulls root observations (= traces) ingested in the last N hours, runs every
scorer below, and writes each result back as a Langfuse Score attached to
that trace_id — visible directly in the trace view in the dashboard.
Re-running is safe: already-scored traces are skipped (checked via
`scores_v3.get_many_v3`), so nothing gets double-counted.

## Files

- `langfuse_client.py` — thin wrapper: fetch recent traces, check what's
  already scored, push a score. See the module docstring for the exact
  (undocumented) `fields=` incantations v4's events_only mode requires —
  reverse-engineered against real traces, not found written down anywhere.
- `format_scorer.py` — deterministic, regex-only checks against IRIS
  India's own formatting rules (`agents/prompts/final_rewrite.py`). No LLM
  call, free, 100% reproducible.
- `run_evaluations.py` — the runnable entry point.

## Scorers

| Name | Type | What it checks |
|---|---|---|
| `format_compliance` | Deterministic (regex) | Exactly one teal verdict span (prose routes), no en/em dash, no double-hyphen, no AI filler openers, no robotic hedges, 3-4 paragraphs (prose routes only) |
| `relevance_groundedness` | LLM-as-judge (claude-haiku-4-5, via IRIS's ApiLens proxy — temporary shared key) | Does the response actually address the user's question; is anything a plausible fabrication |
| `possible_fabrication` | LLM-as-judge (boolean, same call as above) | Split out separately so a fabrication concern doesn't just get averaged away inside one blended number |
| `route_plausibility` | LLM-as-judge, runs on EVERY live trace (no golden dataset needed) | Does the route IRIS picked look reasonable for this query, in a generic judge's opinion. Deliberately a WEAKER claim than `route_accuracy` below — the judge doesn't know IRIS's actual routing rules, so a low score here means "maybe worth a look," not "definitely wrong." Two AI opinions disagreeing isn't proof either is at fault. |
| `route_accuracy` | Exact match against a human-authored answer, only on the 36 golden-dataset queries | The strong, ground-truth version of the check above — only exists for queries a human deliberately pre-labeled |

## Automatic scheduling (Windows Task Scheduler)

Tracing is already automatic for every query (wired directly into IRIS India).
Scoring is NOT automatic by default — `run_evaluations.py` only does anything
when launched. To make scoring run continuously without anyone launching it
by hand, register a recurring scheduled task:

```powershell
$scriptPath = "<repo path>\projects\iris-india\run_evaluations.ps1"
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$scriptPath`""
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 15) -RepetitionDuration (New-TimeSpan -Days 3650)
Register-ScheduledTask -TaskName "NuqiEval-IrisIndia" -Action $action -Trigger $trigger -Settings (New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -StartWhenAvailable) -Force
```

This is already registered and verified working (`LastTaskResult: 0`) — runs
every 15 minutes, `--hours 1` look-back per run (wide safety margin if one
run is delayed), each scorer's own de-duplication means nothing gets
double-scored. Logs land in `scheduled_logs/run_evaluations.log`.

**Gotcha worth knowing if you ever edit `run_evaluations.ps1`:** don't redirect
`python.exe`'s output with `*>`/`2>&1` in PowerShell 5.1 — it wraps every
line Python logs to stderr (which `logging` does by default) in a
`NativeCommandError` and makes the task report failure even when the script
exits 0. `run_evaluations.py` writes its own log file directly for exactly
this reason — nothing to redirect at the PowerShell level at all.

```
Get-ScheduledTaskInfo -TaskName "NuqiEval-IrisIndia"   # check last run result
Unregister-ScheduledTask -TaskName "NuqiEval-IrisIndia" -Confirm:$false   # remove it
```

## Golden dataset

`golden_dataset.json` — 36 hand-authored queries covering every major route
(fundamentals, technicals, sentiment, cross_agent, screener, ranking,
concept_explainer, out_of_domain, general, broad_search), written against
the real Accord Fintech schema so they reference real concepts (banking
NIM/CASA/NPA, FII/DII/promoter-pledge shareholding, standalone vs
consolidated, revised quarterly results, real indices/exchanges).

```
.venv/Scripts/python.exe upload_golden_dataset.py
```

Pushes it into Langfuse as a Dataset (`iris-india-golden-queries`, visible
in the dashboard's Datasets tab). Idempotent — re-running adds no duplicates.

## Route-accuracy replay

```
.venv/Scripts/python.exe run_golden_dataset.py [--limit 5] [--base-url http://127.0.0.1:8000]
```

Actually logs into a real, running IRIS India instance (`IRIS_TEST_EMAIL`/
`IRIS_TEST_PASSWORD` in `.env`) and replays every golden query through
`/chat/send`, comparing the route taken against `expected_route`. This is
the one script here that costs real IRIS LLM calls — use `--limit` for a
quick smoke test before running the full 36-item set. No IRIS backend code
is touched; it only calls existing endpoints (`/auth/login`,
`/chat/conversation`, `/chat/send`).

## Not yet built

- Scheduling (cron / Windows Task Scheduler) — currently everything here
  is run manually.
- Dedicated eval-only LLM key (currently reusing IRIS India's own ApiLens
  proxy credentials per instruction — swap `ANTHROPIC_API_KEY`/
  `ANTHROPIC_BASE_URL` in `.env` when a separate one is issued).
