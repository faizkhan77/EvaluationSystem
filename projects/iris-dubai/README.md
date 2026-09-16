# IRIS Dubai Evaluator

Standalone evaluation project that reads already-ingested IRIS Dubai traces
back out of the self-hosted Langfuse instance and writes quality/format scores
onto them. Runs completely decoupled from IRIS Dubai itself — a crash or
slowness here can never affect a live response.

## Architecture

In production (Linux server), this runs as a Docker container alongside the
Langfuse stack:

```
docker compose up -d   # starts everything including evaluation-runner-iris-dubai
docker compose logs -f evaluation-runner-iris-dubai   # watch scoring logs
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
# Run golden dataset replay against a live IRIS Dubai instance
docker compose run --rm evaluation-runner-iris-dubai python run_golden_dataset.py

# Upload golden_dataset.json to Langfuse Datasets tab (idempotent)
docker compose run --rm evaluation-runner-iris-dubai python upload_golden_dataset.py

# Dry-run: format scorer only (no LLM calls, no cost)
docker compose run --rm evaluation-runner-iris-dubai python run_evaluations.py --skip-judge --hours 24
```

## Scorers

| Name | Type | What it checks |
|---|---|---|
| `format_compliance` | Deterministic (regex) | No en/em dash, no AI filler openers, no robotic hedges, teal span present (prose routes), 3-4 paragraphs (prose routes) |
| `relevance_groundedness` | LLM-as-judge (claude-haiku, via ApiLens) | Does the response address the user's GCC market query; any plausible fabrications |
| `possible_fabrication` | LLM-as-judge (boolean, same call) | Split out separately so fabrication concerns aren't averaged away |
| `route_plausibility` | LLM-as-judge, every live trace | Does the route IRIS picked look reasonable for this query |
| `route_accuracy` | Exact match vs golden_dataset.json | Strong ground-truth check — only for the 36 hand-authored golden queries |

## Golden dataset

`golden_dataset.json` — 36 hand-authored queries covering every major route
(fundamentals, technicals, sentiment, cross_agent, screener, ranking,
concept_explainer, out_of_domain, general, broad_search) for GCC markets
(DFM, ADX, UAE stocks: Emaar, Emirates NBD, FAB, DEWA, Aldar, e&, DIB, ADNOC).

```bash
# Upload to Langfuse Datasets tab (one-time, idempotent)
docker compose run --rm evaluation-runner-iris-dubai python upload_golden_dataset.py
```

## Files

| File | Purpose |
|---|---|
| `scheduler.py` | Docker entrypoint — runs evaluations on a schedule |
| `run_evaluations.py` | Main evaluation script (fetch traces → score → push) |
| `run_golden_dataset.py` | Golden dataset replay against a live IRIS Dubai instance |
| `upload_golden_dataset.py` | Pushes golden_dataset.json to Langfuse as a Dataset |
| `format_scorer.py` | Deterministic format checks |
| `llm_judge_scorer.py` | LLM-as-judge relevance + fabrication scorer |
| `route_plausibility_scorer.py` | LLM-as-judge route plausibility scorer |
| `iris_client.py` | HTTP client to call IRIS Dubai's /auth + /chat endpoints |
| `langfuse_client.py` | Langfuse SDK wrapper (fetch traces, push scores) |
| `golden_dataset.json` | 36 hand-authored GCC market queries with expected routes |
| `Dockerfile` | Container definition |
| `requirements.txt` | Python dependencies |
