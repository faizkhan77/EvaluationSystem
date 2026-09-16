"""
format_scorer.py
=================
Deterministic, rule-based checks against IRIS Dubai's formatting rules.
No LLM call — pure regex/string checks. Fast, free, 100% reproducible.

Returns a fraction-passed score (0.0-1.0) plus a comment listing exactly
which checks failed, so a human can see *why* at a glance in the Langfuse
UI without re-deriving it themselves.
"""
import re

# Routes where the final response is expected to be free plain prose,
# subject to paragraph-count rules. Visual/table-heavy routes are excluded.
PROSE_ROUTES = {"fundamentals", "technicals", "sentiment", "cross_agent", "general", "concept_explainer"}

_AI_FILLER_OPENERS = [
    "certainly!", "of course!", "sure!", "absolutely!", "great question!",
    "i'd be happy", "as an ai",
]
_ROBOTIC_HEDGES = [
    "it is worth noting that", "it is important to note that", "please be aware that",
]
_TEAL_SPAN_RE = re.compile(r'<span style="color:\s*#14b8a6;?">', re.IGNORECASE)
_PARAGRAPH_SPLIT_RE = re.compile(r"\n\s*\n")


def _count_paragraphs(text: str) -> int:
    return len([p for p in _PARAGRAPH_SPLIT_RE.split(text.strip()) if p.strip()])


def score_format(final_response: str, route: str) -> dict:
    """Returns {"score": float 0-1, "checks": {name: bool}, "violations": [str]}."""
    if not final_response or not final_response.strip():
        return {"score": 0.0, "checks": {}, "violations": ["empty final_response"]}

    text = final_response
    lower = text.lower()
    checks = {}
    violations = []

    # 1. Exactly one teal highlight span (prose routes only).
    if route in PROSE_ROUTES:
        teal_count = len(_TEAL_SPAN_RE.findall(text))
        checks["exactly_one_teal_span"] = teal_count == 1
        if not checks["exactly_one_teal_span"]:
            violations.append(f"expected exactly 1 teal span, found {teal_count}")

    # 2. No en dash / em dash.
    checks["no_en_em_dash"] = ("–" not in text) and ("—" not in text)
    if not checks["no_en_em_dash"]:
        violations.append("contains an en dash (–) or em dash (—)")

    # 3. No double-hyphen used as a dash substitute.
    checks["no_double_hyphen"] = "--" not in text
    if not checks["no_double_hyphen"]:
        violations.append("contains '--' used as a dash substitute")

    # 4. No AI filler openers.
    checks["no_ai_filler_opener"] = not any(lower.strip().startswith(p) for p in _AI_FILLER_OPENERS)
    if not checks["no_ai_filler_opener"]:
        violations.append("opens with an AI filler phrase (e.g. 'Certainly!', 'Of course!')")

    # 5. No robotic hedging phrases.
    checks["no_robotic_hedge"] = not any(p in lower for p in _ROBOTIC_HEDGES)
    if not checks["no_robotic_hedge"]:
        violations.append("contains a robotic hedge phrase (e.g. 'it is worth noting that')")

    # 6. Paragraph count (3-4), only for plain-prose routes.
    if route in PROSE_ROUTES and "<div" not in lower and "<table" not in lower:
        n = _count_paragraphs(text)
        checks["paragraph_count_3_to_4"] = 3 <= n <= 4
        if not checks["paragraph_count_3_to_4"]:
            violations.append(f"expected 3-4 paragraphs for route={route!r}, found {n}")

    passed = sum(1 for v in checks.values() if v)
    total = len(checks)
    score = passed / total if total else 0.0
    return {"score": score, "checks": checks, "violations": violations}
