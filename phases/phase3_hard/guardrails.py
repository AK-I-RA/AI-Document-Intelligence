from __future__ import annotations
import re


class GuardrailError(Exception):
    def __init__(self, reason: str, code: str):
        self.reason = reason
        self.code = code
        super().__init__(reason)


# prompt injection pattern

_INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions?",
    r"disregard\s+(all\s+)?(previous|prior|above)",
    r"forget\s+(everything|all|your\s+instructions?)",
    r"you\s+are\s+now\s+(a\s+)?(different|new|evil|unrestricted)",
    r"act\s+as\s+(if\s+you\s+are\s+)?(a\s+)?(jailbreak|dan|evil)",
    r"system\s*:\s*(you|ignore|forget)",
    r"<\s*system\s*>",
    r"\[\s*system\s*\]",
    r"pretend\s+(you\s+are|to\s+be)\s+.{0,40}(no\s+restrictions|no\s+limits)",
    r"do\s+anything\s+now",
    r"developer\s+mode",
]

_INJECTION_RE = re.compile(
    "|".join(_INJECTION_PATTERNS),
    re.IGNORECASE | re.DOTALL,
)

# pii patterns

_PII_PATTERNS = {
    "email": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
    "phone_in": r"\b[6-9]\d{9}\b",                                    # Indian mobile
    "phone_intl": r"\+?1?\s?\(?\d{3}\)?[\s.\-]?\d{3}[\s.\-]?\d{4}\b",
    "aadhaar": r"\b\d{4}\s?\d{4}\s?\d{4}\b",
    "pan": r"\b[A-Z]{5}[0-9]{4}[A-Z]\b",
    "ssn": r"\b\d{3}-\d{2}-\d{4}\b",
    "credit_card": r"\b(?:\d{4}[\s\-]?){3}\d{4}\b",
}

_PII_RE = {
    name: re.compile(pattern, re.IGNORECASE)
    for name, pattern in _PII_PATTERNS.items()
}

def redact_pii(text: str) -> tuple[str, list[str]]:
    found = []
    for pii_type, pattern in _PII_RE.items():
        if pattern.search(text):
            found.append(pii_type)
            text = pattern.sub(f"[REDACTED_{pii_type.upper()}]", text)
    return text, found


# offtopic

_OFFTOPIC_PATTERNS = [
    r"\b(write\s+(me\s+)?(a\s+)?(poem|story|song|joke|essay))\b",
    r"\b(generate\s+(code|script|program))\b",
    r"\b(what\s+is\s+the\s+(weather|time|date|news))\b",
    r"\b(who\s+(is|was)\s+(the\s+)?(president|prime\s+minister|ceo))\b",
    r"\b(translate\s+(this|to|into))\b",
    r"\b(tell\s+me\s+(a\s+)?(joke|story|fun\s+fact))\b",
]

_OFFTOPIC_RE = re.compile(
    "|".join(_OFFTOPIC_PATTERNS),
    re.IGNORECASE,
)

def check_input(question: str) -> str:
    if not question or not question.strip():
        raise GuardrailError("Empty Question.", "empty")

    if _INJECTION_RE.search(question):
        raise GuardrailError(
            "Your query contains patterns that look like prompt injection. "
            "Please ask a genuine question about your documents.",
            "injection",
        )

    if _OFFTOPIC_RE.search(question):
        raise GuardrailError(
            "DocuMind only answers questions about uploaded documents. "
            "This query appears to be outside that scope.",
            "off_topic",
        )

    clean_question, found_pii = redact_pii(question)

    return clean_question

def check_output(answer: str, retrieved_chunks: list[dict]) -> str:
    if not answer or not answer.strip():
        raise GuardrailError("Empty ans found from LLM.", "empty_output")

    refusal_phrases = [
        "couldn't find", "cannot find", "not found in",
        "no information", "don't have information",
        "not mentioned", "not available in",
    ]

    answer_lower = answer.lower()
    if any(p in answer_lower for p in refusal_phrases):
        return answer

    if retrieved_chunks:
        doc_names = [c.get("doc_name", "").lower() for c in retrieved_chunks]
        answer_has_citation = any(
            doc in answer.lower() for doc in doc_names
            if doc
        ) or "source:" in answer.lower() or "p." in answer

        if not answer_has_citation:
            answer += "\n\n⚠️ *Note: This answer may not be fully grounded in the source documents.*"

    return answer
