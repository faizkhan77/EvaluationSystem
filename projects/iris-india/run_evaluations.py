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

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("run_evaluations")

FORMAT_SCORE_NAME = "format_compliance"


def main(hours: int) -> None:
    lf = get_client()

    logger.info(f"Fetching traces from the last {hours}h...")
    traces = fetch_recent_traces(lf, hours=hours)
    logger.info(f"Found {len(traces)} scoreable trace(s).")

    already_scored = get_already_scored_trace_ids(lf, FORMAT_SCORE_NAME, hours=hours)
    logger.info(f"{len(already_scored)} already have a '{FORMAT_SCORE_NAME}' score, skipping those.")

    scored, skipped = 0, 0
    for t in traces:
        if t["trace_id"] in already_scored:
            skipped += 1
            continue

        result = score_format(t["final_response"], t["route"])
        comment = "; ".join(result["violations"]) if result["violations"] else "all checks passed"
        push_score(lf, t["trace_id"], FORMAT_SCORE_NAME, result["score"], comment=comment)
        scored += 1
        logger.info(
            f"trace_id={t['trace_id']} route={t['route']} query={t['user_query']!r} "
            f"-> score={result['score']:.2f} ({comment})"
        )

    lf.flush()
    logger.info(f"Done. Scored {scored} trace(s), skipped {skipped} already-scored.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--hours", type=int, default=24, help="Look-back window in hours")
    args = parser.parse_args()
    main(args.hours)
