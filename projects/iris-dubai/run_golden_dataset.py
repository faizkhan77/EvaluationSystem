"""
run_golden_dataset.py
========================
Replays every item in golden_dataset.json against a REAL, running IRIS Dubai
instance and checks whether it picked the expected route. This costs real
IRIS LLM calls — run deliberately, not on a tight schedule.

Usage:
    python run_golden_dataset.py [--limit 5] [--base-url http://your-iris-dubai:8000]
    # or inside Docker:
    docker compose run --rm evaluation-runner-iris-dubai python run_golden_dataset.py
"""
import argparse
import json
import logging
import os
import time

from dotenv import load_dotenv

load_dotenv()

from iris_client import create_conversation, login, send_message
from langfuse_client import get_client, push_score

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("run_golden_dataset")

ROUTE_ACCURACY_SCORE_NAME = "route_accuracy"
TRACE_LOOKUP_RETRIES = 8
TRACE_LOOKUP_DELAY_S = 3


def find_trace_by_thread_id(lf, thread_id: str):
    """Poll briefly — trace export is async and may not be queryable immediately."""
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
                logger.warning(f"query={query!r}: no trace found for thread_id={thread_id} after retries, skipping")
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
    logger.info(f"\n=== Route accuracy: {correct}/{total} ({(correct / total * 100 if total else 0):.1f}%) ===")
    for r in results:
        if not r["match"]:
            logger.info(f"  MISS: {r['query']!r} expected={r['expected']} actual={r['actual']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0, help="Only replay the first N items (0 = all)")
    parser.add_argument("--base-url", default=os.environ.get("IRIS_API_URL", "http://localhost:8000"))
    args = parser.parse_args()
    main(args.limit, args.base_url)
