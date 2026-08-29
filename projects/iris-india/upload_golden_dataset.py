"""
upload_golden_dataset.py
==========================
Pushes golden_dataset.json into Langfuse as a proper Dataset — a first-class
object in the dashboard (Datasets tab), ready for Langfuse's own "Datasets +
Experiments" replay feature once IRIS India can be called programmatically
from here (not yet built — see README "Not yet built").

Safe to re-run: creating the dataset again is a no-op if it already exists,
and dataset items aren't de-duplicated by Langfuse, so this checks for an
existing item with the same query text first to avoid piling up duplicates
on repeated runs.

Usage:
    .venv/Scripts/python.exe upload_golden_dataset.py
"""
import json
import logging

from dotenv import load_dotenv

load_dotenv()

from langfuse_client import get_client

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("upload_golden_dataset")

DATASET_NAME = "iris-india-golden-queries"


def main() -> None:
    lf = get_client()

    lf.create_dataset(
        name=DATASET_NAME,
        description="Representative queries per route for IRIS India, hand-authored against the "
                     "real Accord Fintech schema (see irismcp-ind/skills/wealth-india-query-writer/references). "
                     "Used for route-accuracy regression testing.",
    )
    logger.info(f"Dataset '{DATASET_NAME}' ready.")

    with open("golden_dataset.json", encoding="utf-8") as f:
        items = json.load(f)

    existing = lf.api.dataset_items.list(dataset_name=DATASET_NAME, limit=100)
    existing_queries = {json.loads(i.input).get("user_query") if isinstance(i.input, str) else (i.input or {}).get("user_query") for i in existing.data}

    added, skipped = 0, 0
    for item in items:
        if item["query"] in existing_queries:
            skipped += 1
            continue
        lf.create_dataset_item(
            dataset_name=DATASET_NAME,
            input={"user_query": item["query"]},
            expected_output={"route": item["expected_route"]},
            metadata={"notes": item.get("notes", "")},
        )
        added += 1

    lf.flush()
    logger.info(f"Added {added} new item(s), skipped {skipped} already present.")


if __name__ == "__main__":
    main()
