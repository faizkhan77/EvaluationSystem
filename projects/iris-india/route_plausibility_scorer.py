"""
route_plausibility_scorer.py
==============================
LLM-as-judge check that runs on EVERY live trace automatically (unlike
route_accuracy, which only ever covers the 36 fixed golden_dataset.json
queries). Deliberately a DIFFERENT, weaker claim than route_accuracy:

- route_accuracy: "IRIS's router is DEFINITELY wrong here" (ground truth
  was written by a human in advance, so a mismatch is real evidence).
- route_plausibility: "does this route choice look reasonable for this
  query, in a generic judge's opinion" — the judge doesn't know IRIS's
  actual routing rules/edge cases, so a low score here is a "maybe worth
  a look," not proof of a bug. Two AI opinions disagreeing isn't the same
  as one being provably wrong.

Both are useful; neither replaces the other. This one's value is coverage
(every real query, not just 36 known ones) and it needs no pre-written
expected answer to run.
"""
import json
import logging
import os
import re
from typing import Any, Dict, Optional

from anthropic import Anthropic

logger = logging.getLogger(__name__)

JUDGE_MODEL = os.environ.get("JUDGE_MODEL", "claude-haiku-4-5-20251001")

# Kept in sync by hand with agents/iris_india/states.py::IrisIndiaRoute in
# irisbackend-india — only the routes a real /chat/send query can actually
# land on (skips internal-only ones like ERROR, PREFERENCE_CONFIRMATION).
_ROUTE_GLOSSARY = """
- fundamentals: company financials, ratios, balance sheet, P&L, board of directors, shareholding pattern, valuation
- technicals: price-derived indicators (RSI, MACD, moving averages, support/resistance, chart patterns)
- sentiment: news-driven sentiment/opinion about a specific company
- cross_agent: a buy/sell/hold investment DECISION, or "give me a full/detailed report", or comparing 2+ stocks as investments — combines fundamentals+technicals+sentiment
- screener: filtering/finding a LIST of stocks matching multiple criteria (e.g. "find stocks with X and Y")
- ranking: ordering/ranking a list of stocks by ONE specific metric (e.g. "top 5 by market cap")
- peer_analysis: comparing a company against its direct competitors
- concept_explainer: educational "what is X" / "how does X work" questions with no specific company
- broad_search: macro/real-world finance news needing live web context (e.g. RBI policy, budget announcements)
- portfolio: questions specifically about the user's own held/watchlisted stocks
- general: greetings, capability questions, small talk
- out_of_domain: anything NOT about Indian stock markets (weather, crypto, other countries' markets, etc.) — IRIS should refuse these
- formatting_only: a follow-up asking to reformat/re-present the PREVIOUS answer (e.g. "show that as a table")
"""

_PROMPT_TEMPLATE = """You are reviewing whether a stock-market chatbot's routing decision looks reasonable for a given question. You do NOT know the chatbot's exact internal rules — just judge from the query's plain meaning.

Route glossary:
{glossary}

User query: {query}

The chatbot routed this query to: {actual_route}

Does that route choice look reasonable for this query? Minor judgment calls (e.g. a query that could plausibly fit two routes) should be marked plausible — only flag a route that looks like a clear mismatch to the query's actual intent.

Respond ONLY in valid JSON, no other text:
{{
    "plausible": true | false,
    "reasoning": "one sentence"
}}
"""


def _get_client() -> Anthropic:
    return Anthropic(
        api_key=os.environ["ANTHROPIC_API_KEY"],
        base_url=os.environ.get("ANTHROPIC_BASE_URL") or None,
    )


def score_route_plausibility(user_query: str, actual_route: str) -> Optional[Dict[str, Any]]:
    """Returns {"score": 1.0 or 0.0, "reasoning": str} or None on judge failure
    (network/parsing) — never crashes the batch over one bad judge call."""
    if not user_query or not actual_route:
        return None

    prompt = _PROMPT_TEMPLATE.format(glossary=_ROUTE_GLOSSARY, query=user_query, actual_route=actual_route)

    try:
        client = _get_client()
        message = client.messages.create(
            model=JUDGE_MODEL,
            max_tokens=150,
            temperature=0,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = message.content[0].text.strip()
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip())
        parsed = json.loads(raw)

        return {
            "score": 1.0 if parsed.get("plausible") else 0.0,
            "reasoning": parsed.get("reasoning", ""),
        }
    except Exception as e:
        logger.warning(f"Route plausibility judge call failed, skipping this trace: {e}")
        return None
