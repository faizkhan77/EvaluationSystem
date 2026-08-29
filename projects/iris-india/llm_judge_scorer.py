"""
llm_judge_scorer.py
=====================
LLM-as-judge scorer: does the final response actually address the user's
original question, and is anything in it plausibly fabricated? Unlike
format_scorer.py, this genuinely requires judgment, so it costs one extra
LLM call per trace — kept as a separate scorer specifically so it can be
run less often / disabled independently of the free, instant format checks.

Prompt design lifted directly from IRIS India's own
utils/query_validator.py::validate_query_response, which already has this
exact judgment call well-tuned for this specific product (out-of-domain
refusal handling, "assume DB numbers are correct" calibration, etc.) —
reused rather than re-invented from scratch.

Uses the SAME ApiLens proxy credentials IRIS India itself uses (see that
repo's agents/config/model.py) — a temporary reuse, per instruction, until
the eval system gets its own dedicated key (just swap ANTHROPIC_API_KEY/
ANTHROPIC_BASE_URL in .env when that's ready, nothing else changes).
"""
import json
import logging
import os
import re
from typing import Any, Dict, Optional

from anthropic import Anthropic

logger = logging.getLogger(__name__)

JUDGE_MODEL = os.environ.get("JUDGE_MODEL", "claude-haiku-4-5-20251001")

_PROMPT_TEMPLATE = """You are a query validation expert. Analyze if the AI response correctly answers the user's question.

User Query: {query}

AI Response: {response}

Task:
1. Determine if the response correctly addresses the query.
   IMPORTANT: The AI system has access to a secure, real-time internal database.
   - If the AI provides specific numbers, dates, or financial metrics (e.g., "P/E ratio is 33.53"), ASSUME THIS DATA IS CORRECT and retrieved from the database.
   - Do NOT mark a response as 'partial' or 'incorrect' simply because it doesn't provide a "citation", "source", or "evidence".
   - Failure to provide external verification is NOT an error.

   CRITICAL - OUT-OF-DOMAIN QUERIES:
   - IRIS India is a stock market analysis AI that ONLY covers Indian equities (NSE/BSE).
   - If the user asks about non-stock-market topics, non-Indian markets, crypto/commodities/forex,
     AND the AI correctly refuses or states it cannot help with that query, THEN mark status as
     'correct' with high confidence (0.9+) — refusing out-of-domain queries is success, not failure.

2. Also flag anything that reads as an UNSUPPORTED/FABRICATED claim: a specific number, date, or
   fact stated with confidence that doesn't plausibly come from a real database lookup implied by
   the query (e.g. a suspiciously precise stat with no clear data source context). Set
   "possible_fabrication" true only if something genuinely looks invented, not merely because a
   number can't be independently verified from this prompt alone.

3. Provide reasoning for your assessment (1-2 sentences).
4. Assign a confidence score (0.0-1.0) where:
   - 1.0 = Perfect answer, or correct refusal of an out-of-domain query
   - 0.7-0.9 = Good answer, minor issues (e.g. missed a minor sub-part of the question)
   - 0.4-0.6 = Partial answer, missing key info the user explicitly asked for
   - 0.0-0.3 = Wrong answer, failed to address the question, or a real fabrication concern

Respond ONLY in valid JSON format, no other text:
{{
    "status": "correct" | "incorrect" | "partial",
    "possible_fabrication": true | false,
    "reasoning": "brief explanation",
    "confidence_score": 0.85
}}
"""


def _get_client() -> Anthropic:
    return Anthropic(
        api_key=os.environ["ANTHROPIC_API_KEY"],
        base_url=os.environ.get("ANTHROPIC_BASE_URL") or None,
    )


def _strip_html(text: str) -> str:
    """The judge only needs to read the actual words, not IRIS's own HTML
    styling (teal spans, hyperlinks, badges) — stripping it keeps the judge
    prompt smaller and stops HTML noise from confusing the judgment."""
    return re.sub(r"<[^>]+>", " ", text)


def score_relevance_and_groundedness(user_query: str, final_response: str) -> Optional[Dict[str, Any]]:
    """Returns {"score": float, "possible_fabrication": bool, "reasoning": str}
    or None if the judge call itself failed (network/parsing) — a judge
    failure must never crash the whole batch run, just skip that trace."""
    if not user_query or not final_response:
        return None

    prompt = _PROMPT_TEMPLATE.format(query=user_query, response=_strip_html(final_response)[:6000])

    try:
        client = _get_client()
        message = client.messages.create(
            model=JUDGE_MODEL,
            max_tokens=300,
            temperature=0,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = message.content[0].text.strip()
        # Judges occasionally wrap JSON in a code fence despite instructions — strip it defensively.
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip())
        parsed = json.loads(raw)

        return {
            "score": float(parsed.get("confidence_score", 0.5)),
            "possible_fabrication": bool(parsed.get("possible_fabrication", False)),
            "reasoning": parsed.get("reasoning", ""),
            "status": parsed.get("status", "unknown"),
        }
    except Exception as e:
        logger.warning(f"LLM judge call failed, skipping this trace: {e}")
        return None
