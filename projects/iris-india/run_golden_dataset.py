"""
run_golden_dataset.py
========================
Replays every item in golden_dataset.json against a REAL, running IRIS
India instance and checks whether it picked the expected route. This is
the one script in this project that actually costs real IRIS LLM calls —
run deliberately, not on a tight schedule like run_evaluations.py.

How it links a replay call back to a Langfuse trace: IRIS's /chat/send
final SSE event always includes `thread_id` (unconditionally, unlike
`agent_route` which is admin-only) — and that's exactly the value wired
into `langfuse_session_id` in api/chat/routes.py's config metadata. So
looking up observations by `session_id=thread_id` finds the exact trace
this call produced, without needing an admin account at all.

Usage:
    .venv/Scripts/python.exe run_golden_dataset.py [--limit 5] [--base-url http://127.0.0.1:8000]
"""
import argparse
import json
import logging
import time

from dotenv import load_dotenv

load_dotenv()

import os

from iris_client import create_conversation, login, send_message
from langfuse_client import get_client, push_score

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("run_golden_dataset")

ROUTE_ACCURACY_SCORE_NAME = "route_accuracy"
TRACE_LOOKUP_RETRIES = 8
TRACE_LOOKUP_DELAY_S = 3


def find_trace_by_thread_id(lf, thread_id: str):
    """The trace export is async (fire-and-forget), so it may not be queryable
    the instant the HTTP response finishes — poll briefly rather than fail."""
    for attempt in range(TRACE_LOOKUP_RETRIES):
        resp = lf.api.observations.get_many(
            session_id=thread_id, is_root_observation=True, fields="basic,io,metadata", limit=1,
        )
        if resp.data:
            return resp.data[0]
        time.sleep(TRACE_LOOKUP_DELAY_S)
    return None


def main(limit: int, base_url: str) -> None:
    email = os.environ["IRIS_TEST_EMAIL"]
    password = os.environ["IRIS_TEST_PASSWORD"]

    with open("golden_dataset.json", encoding="utf-8") as f:
        dataset = json.load(f)
    if limit:
        dataset = dataset[:limit]

    logger.info(f"Logging in as {email} against {base_url}...")
    token = login(base_url, email, password)

    lf = get_client()
    results = []

    for item in dataset:
        query, expected_route = item["query"], item["expected_route"]
        try:
            chat_session_id = create_conversation(base_url, token)
            final = send_message(base_url, token, chat_session_id, query)
            thread_id = final["thread_id"]

            observation = find_trace_by_thread_id(lf, thread_id)
            if observation is None:
                logger.warning(f"query={query!r}: no trace found for thread_id={thread_id} after {TRACE_LOOKUP_RETRIES * TRACE_LOOKUP_DELAY_S}s, skipping")
                continue

            output_data = json.loads(observation.output) if observation.output else {}
            actual_route = output_data.get("route")
            match = actual_route == expected_route

            push_score(
                lf, observation.trace_id, ROUTE_ACCURACY_SCORE_NAME,
                1.0 if match else 0.0,
                comment=f"expected={expected_route} actual={actual_route}",
            )
            results.append({"query": query, "expected": expected_route, "actual": actual_route, "match": match})
            logger.info(f"{'OK  ' if match else 'MISS'} query={query!r} expected={expected_route} actual={actual_route}")
        except Exception as e:
            logger.error(f"query={query!r}: replay failed: {e}")

    lf.flush()

    total = len(results)
    correct = sum(1 for r in results if r["match"])
    logger.info(f"\n=== Route accuracy: {correct}/{total} ({(correct/total*100 if total else 0):.1f}%) ===")
    for r in results:
        if not r["match"]:
            logger.info(f"  MISS: {r['query']!r} expected={r['expected']} actual={r['actual']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0, help="Only replay the first N items (0 = all)")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    main(args.limit, args.base_url)
