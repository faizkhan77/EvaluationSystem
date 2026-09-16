# IRIS India Evaluator

Standalone evaluation project that reads already-ingested IRIS India traces
back out of the self-hosted Langfuse instance and writes quality/format scores
onto them. Runs completely decoupled from IRIS India itself — a crash or
slowness here can never affect a live response.

## Architecture

In production (Linux server), this runs as a Docker container alongside the
Langfuse stack:

```
docker compose up -d   # starts everything including evaluation-runner-iris-india
docker compose logs -f evaluation-runner-iris-india   # watch scoring logs
```

The scheduler runs `run_evaluations.py` every `EVAL_INTERVAL_HOURS` hours
(default: 1h). All environment variables are injected by docker-compose via
the root `.env` file — no local `.env` needed on the server.

## Local development

```bash
python -m venv .venv
.venv/Scripts/activate      # Windows
# source .venv/bin/activate  # Linux/Mac
pip install -r requirements.txt
cp .env.example .env        # fill in Langfuse keys + Anthropic key
python run_evaluations.py --hours 24
```

## One-off commands via Docker

```bash
# Run golden dataset replay against a live IRIS India instance
docker compose run --rm evaluation-runner-iris-india python run_golden_dataset.py

# Upload golden_dataset.json to Langfuse Datasets tab (idempotent)
docker compose run --rm evaluation-runner-iris-india python upload_golden_dataset.py

# Dry-run: format scorer only (no LLM calls, no cost)
docker compose run --rm evaluation-runner-iris-india python run_evaluations.py --skip-judge --hours 24
```

## Scorers

| Name | Type | What it checks |
|---|---|---|
| `format_compliance` | Deterministic (regex) | Exactly one teal verdict span (prose routes), no en/em dash, no double-hyphen, no AI filler openers, no robotic hedges, 3-4 paragraphs (prose routes only) |
| `relevance_groundedness` | LLM-as-judge (claude-haiku, via ApiLens) | Does the response actually address the user's Indian market query; is anything a plausible fabrication |
| `possible_fabrication` | LLM-as-judge (boolean, same call) | Split out separately so a fabrication concern doesn't get averaged away inside one blended number |
| `route_plausibility` | LLM-as-judge, every live trace | Does the route IRIS picked look reasonable for this query. Deliberately a WEAKER claim than `route_accuracy` — the judge doesn't know IRIS's exact routing rules |
| `route_accuracy` | Exact match vs golden_dataset.json | Strong, ground-truth check — only for the 36 hand-authored golden queries |

## Golden dataset

`golden_dataset.json` — 36 hand-authored queries covering every major route
(fundamentals, technicals, sentiment, cross_agent, screener, ranking,
concept_explainer, out_of_domain, general, broad_search), written against
the real Accord Fintech schema (real companies, real ratios, real exchanges).

```bash
# Upload to Langfuse Datasets tab (one-time, idempotent)
docker compose run --rm evaluation-runner-iris-india python upload_golden_dataset.py
```

## Files

| File | Purpose |
|---|---|
| `scheduler.py` | Docker entrypoint — runs evaluations on a schedule |
| `run_evaluations.py` | Main evaluation script (fetch traces → score → push) |
| `run_golden_dataset.py` | Golden dataset replay against a live IRIS India instance |
| `upload_golden_dataset.py` | Pushes golden_dataset.json to Langfuse as a Dataset |
| `format_scorer.py` | Deterministic format checks |
| `llm_judge_scorer.py` | LLM-as-judge relevance + fabrication scorer |
| `route_plausibility_scorer.py` | LLM-as-judge route plausibility scorer |
| `iris_client.py` | HTTP client to call IRIS India's /auth + /chat endpoints |
| `langfuse_client.py` | Langfuse SDK wrapper (fetch traces, push scores) |
| `golden_dataset.json` | 36 hand-authored Indian market queries with expected routes |
| `Dockerfile` | Container definition |
| `requirements.txt` | Python dependencies |
