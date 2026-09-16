"""
route_plausibility_scorer.py
==============================
LLM-as-judge check that runs on EVERY live trace automatically.
Checks whether the route IRIS Dubai chose looks reasonable for the query,
in a generic judge's opinion.

Deliberately a WEAKER claim than route_accuracy:
- route_accuracy: "IRIS's router is DEFINITELY wrong" (ground truth from human labels)
- route_plausibility: "does this route look reasonable" — judge doesn't know IRIS's
  exact internal rules, so a low score means "maybe worth a look," not "definitely wrong."
"""
import json
import logging
import os
import re
from typing import Any, Dict, Optional

from anthropic import Anthropic

logger = logging.getLogger(__name__)

JUDGE_MODEL = os.environ.get("JUDGE_MODEL", "claude-haiku-4-5-20251001")

# Keep in sync with the actual routes in the IRIS Dubai backend.
_ROUTE_GLOSSARY = """
- fundamentals: company financials, ratios, balance sheet, P&L, valuation for GCC-listed companies (DFM, ADX, MSM, BHB, KSE)
- technicals: price-derived indicators (RSI, MACD, moving averages, support/resistance, Bollinger Bands) for GCC stocks
- sentiment: news-driven sentiment/opinion about a specific GCC-listed company
- cross_agent: a buy/sell/hold investment DECISION, or "give me a full report", or comparing 2+ GCC stocks as investments
- screener: filtering/finding a LIST of GCC stocks matching multiple criteria
- ranking: ordering/ranking a list of GCC stocks by ONE specific metric
- concept_explainer: educational "what is X" / "how does X work" questions with no specific company
- broad_search: macro/real-world GCC finance news needing live context (oil prices, OPEC, UAE Vision 2030, Saudi Aramco, Central Bank decisions)
- portfolio: questions specifically about the user's own held/watchlisted GCC stocks
- general: greetings, capability questions, small talk
- out_of_domain: anything NOT about GCC stock markets (Indian markets, US markets, crypto, weather, etc.) — IRIS should refuse these
"""

_PROMPT_TEMPLATE = """You are reviewing whether a GCC stock-market chatbot's routing decision looks reasonable for a given question. You do NOT know the chatbot's exact internal rules — just judge from the query's plain meaning.

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
    """Returns {"score": 1.0 or 0.0, "reasoning": str} or None on judge failure."""
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
