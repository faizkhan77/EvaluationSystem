"""
llm_judge_scorer.py
=====================
LLM-as-judge scorer: does the final response actually address the user's
original question, and is anything in it plausibly fabricated?

Adapted for IRIS Dubai — covers GCC equities (DFM, ADX, MSM, BHB, KSE)
rather than Indian equities (NSE, BSE).
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
   IMPORTANT: The AI system has access to a secure, real-time internal database covering GCC equity markets.
   - If the AI provides specific numbers, dates, or financial metrics, ASSUME THIS DATA IS CORRECT and retrieved from the database.
   - Do NOT mark a response as 'partial' or 'incorrect' simply because it doesn't provide a "citation" or "source".

   CRITICAL - OUT-OF-DOMAIN QUERIES:
   - IRIS Dubai is a stock market analysis AI that ONLY covers GCC equities (DFM, ADX, MSM, BHB, KSE — UAE, Saudi, Oman, Bahrain, Kuwait markets).
   - If the user asks about non-GCC markets (Indian stocks, US stocks, crypto, commodities, weather, etc.)
     AND the AI correctly refuses or states it cannot help, mark status as 'correct' with high confidence (0.9+).
     Refusing out-of-domain queries is success, not failure.

2. Flag UNSUPPORTED/FABRICATED claims: specific numbers or facts stated with confidence that don't
   plausibly come from a real database lookup implied by the query. Set "possible_fabrication" true
   only if something genuinely looks invented.

3. Provide reasoning for your assessment (1-2 sentences).
4. Assign a confidence score (0.0-1.0) where:
   - 1.0 = Perfect answer, or correct refusal of an out-of-domain query
   - 0.7-0.9 = Good answer, minor issues
   - 0.4-0.6 = Partial answer, missing key info the user asked for
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
    return re.sub(r"<[^>]+>", " ", text)


def score_relevance_and_groundedness(user_query: str, final_response: str) -> Optional[Dict[str, Any]]:
    """Returns {"score": float, "possible_fabrication": bool, "reasoning": str}
    or None if the judge call itself failed — never crashes the batch."""
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
