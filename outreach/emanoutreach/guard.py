"""Untrusted-content handling.

Everything fetched from a prospect site or a search result is DATA. This module
flags instruction-like text so it is recorded, and makes sure only short,
sanitised UI labels (never free page text) can reach a draft.
"""
from __future__ import annotations

import re

INJECTION_PATTERNS = [
    r"ignore (all|any|previous|prior|the above) (instructions|rules)",
    r"disregard (your|all|previous) (instructions|rules|guidelines)",
    r"\b(ai|llm|language model|assistant|agent|chatgpt|claude)s?\b[^.]{0,60}\b(must|should|are instructed|please)\b",
    r"system prompt",
    r"you are now",
    r"do not (email|contact|flag|report)",
    r"(mark|score|rate) (this|us) (as )?(high|eligible|qualified|100)",
    r"send (an? )?(email|message) to",
    r"</?(system|instructions?)>",
]
_RX = [re.compile(p, re.I) for p in INJECTION_PATTERNS]


def scan(text: str | None) -> list[str]:
    """Return the instruction-like fragments found in untrusted text."""
    if not text:
        return []
    hits = []
    for rx in _RX:
        for m in rx.finditer(text):
            s = max(0, m.start() - 40)
            hits.append(text[s : m.end() + 40].strip())
    return hits


def safe_label(text: str | None, max_len: int = 40) -> str:
    """A UI label (button/link text) that may be quoted in a draft.

    Keeps letters, digits, spaces and light punctuation; drops anything that
    looks like an instruction; truncates.
    """
    if not text:
        return ""
    t = re.sub(r"[^\w\s&'’!?,.-]", "", text).strip()
    t = re.sub(r"\s+", " ", t)
    if scan(t) or len(t) > max_len:
        return ""
    return t
