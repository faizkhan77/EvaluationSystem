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

## Not yet built

- LLM-as-judge scorer (groundedness / does-it-answer-the-question) — needs
  a decision on which LLM key to use (reuse IRIS's own, or a separate
  eval-only key) before wiring up.
- Route-accuracy scorer against a golden query dataset.
- Scheduling (cron / Windows Task Scheduler) — currently run manually.
