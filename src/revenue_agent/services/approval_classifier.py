"""Classify user messages as approval, rejection, or new queries.

When the graph is paused at a human-review interrupt, incoming chat
messages are classified so the system can resume automatically instead of
requiring button clicks.

Strategy:
    1. Fast keyword / regex matching (no API call)
    2. LLM fallback for ambiguous messages
"""

import logging
import re
from enum import Enum

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from revenue_agent.config import settings

logger = logging.getLogger(__name__)


class ApprovalIntent(str, Enum):
    """Possible user intents when there is a pending approval."""

    APPROVE = "approve"
    REJECT = "reject"
    NEW_QUERY = "new_query"


# ---------------------------------------------------------------------------
# Keyword patterns (case-insensitive)
# ---------------------------------------------------------------------------

_APPROVE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"\byes\b", r"\byep\b", r"\byeah\b", r"\bsure\b",
        r"\bapprov\w*\b",          # approve, approved, approving, approval
        r"\bgo ahead\b", r"\bconfirm\w*\b", r"\bproceed\b",
        r"\bapply\b", r"\bapplying\b", r"\bdo it\b", r"\baccept\w*\b",
        r"\blooks good\b", r"\bi like it\b", r"\bsounds good\b",
        r"\bok\b", r"\bokay\b", r"\blet'?s do it\b",
        r"\bagree\b", r"\bagreed\b", r"\bplease do\b",
        r"\bgo for it\b", r"\blet'?s go\b",
        r"\bgreat\b", r"\bperfect\b", r"\babsolutely\b",
        r"\bdefinitely\b", r"\bfor sure\b",
    ]
]

_REJECT_PATTERNS: list[re.Pattern[str]] = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"\bno\b", r"\bnope\b", r"\breject\w*\b",
        r"\bcancel\w*\b", r"\bdon'?t\b", r"\bdo not\b",
        r"\bstop\b", r"\babort\b", r"\bnevermind\b",
        r"\bnever mind\b", r"\bdecline\w*\b", r"\bdisapprov\w*\b",
        r"\bhold off\b", r"\bnot now\b",
        r"\bno thanks\b", r"\bno thank you\b",
    ]
]


def _keyword_classify(message: str) -> ApprovalIntent | None:
    """Attempt to classify intent via keyword matching.

    Returns:
        An intent if a clear signal is found, otherwise ``None`` (ambiguous).
    """
    text = message.strip()

    approve_hits = sum(1 for p in _APPROVE_PATTERNS if p.search(text))
    reject_hits = sum(1 for p in _REJECT_PATTERNS if p.search(text))

    if approve_hits > 0 and reject_hits == 0:
        return ApprovalIntent.APPROVE
    if reject_hits > 0 and approve_hits == 0:
        return ApprovalIntent.REJECT

    # Both matched (contradictory) or neither matched — ambiguous
    return None


# ---------------------------------------------------------------------------
# LLM fallback
# ---------------------------------------------------------------------------

_CLASSIFICATION_PROMPT = (
    "You are a classifier. A user has been presented with proposed financial "
    "actions (make-good invoices, credit memos, or plan amendments) and asked "
    "to approve or reject them.\n\n"
    "The user's response is below. Classify their intent as one of:\n"
    "- APPROVE — the user wants to proceed with the proposed actions\n"
    "- REJECT  — the user does not want to proceed\n"
    "- NEW_QUERY — the user is asking a completely different / unrelated question\n\n"
    "Reply with EXACTLY one word: APPROVE, REJECT, or NEW_QUERY."
)

_INTENT_MAP: dict[str, ApprovalIntent] = {
    "APPROVE": ApprovalIntent.APPROVE,
    "REJECT": ApprovalIntent.REJECT,
    "NEW_QUERY": ApprovalIntent.NEW_QUERY,
}


async def _llm_classify(message: str) -> ApprovalIntent:
    """Use the LLM to classify an ambiguous message."""
    try:
        llm = ChatOpenAI(
            model=settings.openai_model,
            api_key=settings.openai_api_key,
            temperature=0,
            max_tokens=10,
        )
        response = await llm.ainvoke([
            SystemMessage(content=_CLASSIFICATION_PROMPT),
            HumanMessage(content=message),
        ])

        token = response.content.strip().upper()
        for key, intent in _INTENT_MAP.items():
            if key in token:
                return intent

        logger.warning("LLM returned unexpected classification: %s", token)
        return ApprovalIntent.NEW_QUERY

    except Exception as e:
        logger.warning("LLM classification failed (%s) — treating as new query", e)
        return ApprovalIntent.NEW_QUERY


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def classify_approval_intent(message: str) -> ApprovalIntent:
    """Classify whether a user message is an approval, rejection, or new query.

    1. Try keyword matching first (fast, no API call).
    2. If ambiguous, fall back to LLM classification.

    Args:
        message: The raw user message text.

    Returns:
        The classified ``ApprovalIntent``.
    """
    intent = _keyword_classify(message)
    if intent is not None:
        logger.info(
            "Keyword classifier → %s for message: %.50s",
            intent.value,
            message,
        )
        return intent

    logger.info("Keyword classifier ambiguous, falling back to LLM: %.50s", message)
    return await _llm_classify(message)
