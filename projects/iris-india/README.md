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

## Not yet built

- **Route-accuracy replay runner** — actually POSTing each golden query to
  IRIS India's own `/chat/send` and comparing the route taken against
  `expected_route`. Needs auth wiring (a valid user token) since that's a
  real authenticated endpoint, not yet built.
- Scheduling (cron / Windows Task Scheduler) — currently run manually.
- Dedicated eval-only LLM key (currently reusing IRIS India's own ApiLens
  proxy credentials per instruction — swap `ANTHROPIC_API_KEY`/
  `ANTHROPIC_BASE_URL` in `.env` when a separate one is issued).
