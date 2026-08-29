# Nuqi Eval System

Self-hosted [Langfuse](https://github.com/langfuse/langfuse) (v4) as the shared LLM
observability/evaluation backbone for Nuqi's AI products — starting with IRIS India
and IRIS Dubai, built to onboard any future Nuqi product without standing up new
infrastructure.

## Why this exists

Both IRIS backends needed a way to measure latency, response quality/format
compliance, route accuracy, and "does it actually answer the user's question" —
without ever adding risk or latency to the live user-facing request path. Langfuse's
LangChain/LangGraph integration is a fire-and-forget async callback, so tracing can
never block or slow down a real IRIS response.

## Is this multi-tenant? Yes — natively, via Langfuse's own data model

Langfuse already has multi-tenancy built in: **one Organization → many Projects**,
each with its own API keypair, its own dashboards/datasets, its own custom
evaluator definitions, and its own configured LLM connection (for running
Langfuse's built-in LLM-as-judge evaluators/playground). Projects are isolated from
each other by Langfuse's own access control — a member of the `iris-dubai` project
cannot see `iris-india`'s traces unless explicitly added to both.

**There is exactly ONE deployment and ONE shared database stack** (Postgres +
ClickHouse + Redis + MinIO, all defined in `docker-compose.yml`) serving every
project — this is the same architecture Langfuse Cloud itself uses to serve
thousands of unrelated customers. A new Nuqi product does **not** need a new
server, a new database, or a new docker-compose — it needs one new Project inside
this same Org, created in under a minute from Settings -> Projects -> New (or
scripted the same way `iris-india` was auto-provisioned below, via
`LANGFUSE_INIT_*` env vars).

Each project can then:
- Bring their own LLM API key (Settings -> LLM Connections) for running judge
  evaluators/playground scoped to their project only.
- Define their own custom evaluator prompts/criteria (Evaluations -> Templates).
- See only their own traces, datasets, and dashboards.

The only thing genuinely shared across all tenants is the underlying infra — never
the data, credentials, or evaluation criteria.

## Structure

```
nuqi-eval-system/
├── docker-compose.yml   # Official Langfuse v4 self-host stack (Postgres, ClickHouse, Redis, MinIO, web, worker)
├── .env                 # Real secrets — gitignored, never committed
├── .env.example         # Blank template — copy to .env and fill in
└── projects/            # Per-tenant evaluator scripts (custom scoring logic Langfuse doesn't ship out of the box)
    ├── iris-india/       # format/route/groundedness scorers for IRIS India, run against its Project's traces
    └── iris-dubai/       # same, for IRIS Dubai
```

`docker-compose.yml` and the dashboard/tracing UI are Langfuse's own product —
nothing in this repo modifies them. `projects/*` is where the IRIS-specific (and
later, other-product-specific) evaluation logic actually lives: regex/format
checkers, route-accuracy comparators, and LLM-as-judge scripts that read traces via
the Langfuse SDK and write scores back onto them. These run on a schedule,
completely decoupled from IRIS's live request path.

## First-time setup

1. Copy `.env.example` to `.env` and fill in real secrets (already done for local
   dev — see `.env`, gitignored). `LANGFUSE_INIT_*` auto-provisions one Org (`nuqi`)
   and its first Project (`iris-india`) on first boot — no manual signup needed.
2. `docker compose up -d`
3. Open http://localhost:3000, log in with `LANGFUSE_INIT_USER_EMAIL` /
   `LANGFUSE_INIT_USER_PASSWORD` from `.env`.
4. Grab the `iris-india` project's public/secret API keypair (Settings -> API Keys,
   or read straight from `.env`'s `LANGFUSE_INIT_PROJECT_PUBLIC_KEY` /
   `_SECRET_KEY`).
5. Create a second Project for `iris-dubai` the same way (Settings -> Projects ->
   New), grab its keypair.
6. Wire each IRIS backend's LangGraph invocation with the Langfuse callback handler
   (see `projects/*/README.md` once added) — this is a one-line addition to the
   already-empty `"callbacks": []` list both backends pass into `app.ainvoke()`.

## Upgrading

```
docker compose pull
docker compose up -d
```
