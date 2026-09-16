"""
langfuse_client.py
===================
Thin wrapper around the Langfuse v4 SDK for pulling recently-ingested IRIS
Dubai traces and writing scores back onto them.

v4 self-hosted runs in "events_only" mode by default, which removes the old
trace.list()/trace.get() endpoints entirely — the only way to read trace
content back is via the newer Observations API v2 (observations.get_many).
A "trace" is just its root observation (is_root_observation=True); the graph
state IRIS Dubai returns (route, final_response, etc.) lives in that root
observation's `output` field as a JSON string.

IMPORTANT: fields="basic,io,metadata" must be passed explicitly — the
default field set omits input/output/metadata entirely.
"""
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from langfuse import Langfuse

logger = logging.getLogger(__name__)


def get_client() -> Langfuse:
    """Reads LANGFUSE_PUBLIC_KEY/SECRET_KEY/HOST from the environment (.env)."""
    return Langfuse()


def fetch_recent_traces(lf: Langfuse, hours: int = 24, limit: int = 100) -> List[Dict[str, Any]]:
    """Returns a list of {trace_id, user_query, route, final_response, timestamp}
    for root observations ingested in the last `hours` hours."""
    from_ts = datetime.now(timezone.utc) - timedelta(hours=hours)

    resp = lf.api.observations.get_many(
        is_root_observation=True,
        fields="basic,io,metadata",
        from_start_time=from_ts,
        limit=limit,
    )

    traces = []
    for o in resp.data:
        try:
            input_data = json.loads(o.input) if o.input else {}
            output_data = json.loads(o.output) if o.output else {}
        except (json.JSONDecodeError, TypeError) as e:
            logger.warning(f"Skipping trace_id={o.trace_id}: input/output not valid JSON ({e})")
            continue

        final_response = output_data.get("final_response")
        route = output_data.get("route")
        user_query = input_data.get("user_query")

        if not final_response or not route:
            logger.debug(f"Skipping trace_id={o.trace_id}: missing final_response/route")
            continue

        traces.append({
            "trace_id": o.trace_id,
            "user_query": user_query,
            "route": route,
            "final_response": final_response,
            "start_time": o.start_time,
        })

    return traces


def get_already_scored_trace_ids(lf: Langfuse, score_name: str, hours: int = 24) -> set:
    """Which trace_ids already have a score with this name — so a re-run
    doesn't re-score the same trace."""
    from_ts = datetime.now(timezone.utc) - timedelta(hours=hours)
    resp = lf.api.scores_v3.get_many_v3(name=score_name, from_timestamp=from_ts, limit=100, fields="core,subject")
    return {
        s.subject.id for s in resp.data
        if s.subject is not None and getattr(s.subject, "kind", None) == "trace"
    }


def push_score(
    lf: Langfuse,
    trace_id: str,
    name: str,
    value: float,
    comment: Optional[str] = None,
    data_type: str = "NUMERIC",
) -> None:
    lf.create_score(trace_id=trace_id, name=name, value=value, comment=comment, data_type=data_type)
