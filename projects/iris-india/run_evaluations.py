"""
run_evaluations.py
====================
The decoupled, scheduled entry point — run this manually or on a cron/Task
Scheduler interval. Deliberately NOT part of IRIS India's own process: it
only ever reads already-ingested traces back out of Langfuse and writes
scores onto them, completely after the fact. A crash or slowness here can
never affect a live IRIS response.

Usage:
    .venv/Scripts/python.exe run_evaluations.py [--hours 24]
"""
import argparse
import logging

from dotenv import load_dotenv

load_dotenv()

from format_scorer import score_format
from langfuse_client import fetch_recent_traces, get_already_scored_trace_ids, get_client, push_score
from llm_judge_scorer import score_relevance_and_groundedness
from route_plausibility_scorer import score_route_plausibility

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("run_evaluations")

FORMAT_SCORE_NAME = "format_compliance"
JUDGE_SCORE_NAME = "relevance_groundedness"
FABRICATION_SCORE_NAME = "possible_fabrication"
ROUTE_PLAUSIBILITY_SCORE_NAME = "route_plausibility"


def run_format_scorer(lf, traces, hours: int) -> None:
    already_scored = get_already_scored_trace_ids(lf, FORMAT_SCORE_NAME, hours=hours)
    logger.info(f"[{FORMAT_SCORE_NAME}] {len(already_scored)} already scored, skipping those.")

    scored = 0
    for t in traces:
        if t["trace_id"] in already_scored:
            continue
        result = score_format(t["final_response"], t["route"])
        comment = "; ".join(result["violations"]) if result["violations"] else "all checks passed"
        push_score(lf, t["trace_id"], FORMAT_SCORE_NAME, result["score"], comment=comment)
        scored += 1
        logger.info(f"[{FORMAT_SCORE_NAME}] trace_id={t['trace_id']} route={t['route']} -> {result['score']:.2f} ({comment})")
    logger.info(f"[{FORMAT_SCORE_NAME}] scored {scored} new trace(s).")


def run_llm_judge(lf, traces, hours: int) -> None:
    already_scored = get_already_scored_trace_ids(lf, JUDGE_SCORE_NAME, hours=hours)
    logger.info(f"[{JUDGE_SCORE_NAME}] {len(already_scored)} already scored, skipping those.")

    scored = 0
    for t in traces:
        if t["trace_id"] in already_scored:
            continue
        result = score_relevance_and_groundedness(t["user_query"], t["final_response"])
        if result is None:
            continue  # judge call itself failed — skip, don't crash the batch
        push_score(lf, t["trace_id"], JUDGE_SCORE_NAME, result["score"], comment=result["reasoning"])
        push_score(
            lf, t["trace_id"], FABRICATION_SCORE_NAME,
            1.0 if result["possible_fabrication"] else 0.0,
            comment=result["reasoning"], data_type="BOOLEAN",
        )
        scored += 1
        logger.info(f"[{JUDGE_SCORE_NAME}] trace_id={t['trace_id']} -> {result['score']:.2f} (fabrication={result['possible_fabrication']})")
    logger.info(f"[{JUDGE_SCORE_NAME}] scored {scored} new trace(s).")


def run_route_plausibility(lf, traces, hours: int) -> None:
    already_scored = get_already_scored_trace_ids(lf, ROUTE_PLAUSIBILITY_SCORE_NAME, hours=hours)
    logger.info(f"[{ROUTE_PLAUSIBILITY_SCORE_NAME}] {len(already_scored)} already scored, skipping those.")

    scored = 0
    for t in traces:
        if t["trace_id"] in already_scored:
            continue
        result = score_route_plausibility(t["user_query"], t["route"])
        if result is None:
            continue
        push_score(lf, t["trace_id"], ROUTE_PLAUSIBILITY_SCORE_NAME, result["score"], comment=result["reasoning"])
        scored += 1
        logger.info(f"[{ROUTE_PLAUSIBILITY_SCORE_NAME}] trace_id={t['trace_id']} route={t['route']} -> {result['score']:.0f} ({result['reasoning']})")
    logger.info(f"[{ROUTE_PLAUSIBILITY_SCORE_NAME}] scored {scored} new trace(s).")


def main(hours: int, skip_judge: bool) -> None:
    lf = get_client()

    logger.info(f"Fetching traces from the last {hours}h...")
    traces = fetch_recent_traces(lf, hours=hours)
    logger.info(f"Found {len(traces)} scoreable trace(s).")

    run_format_scorer(lf, traces, hours)
    if skip_judge:
        logger.info("Skipping LLM judge (--skip-judge).")
    else:
        run_llm_judge(lf, traces, hours)
        run_route_plausibility(lf, traces, hours)

    lf.flush()
    logger.info("Done.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--hours", type=int, default=24, help="Look-back window in hours")
    parser.add_argument("--skip-judge", action="store_true", help="Only run the free deterministic format scorer")
    args = parser.parse_args()
    main(args.hours, args.skip_judge)
