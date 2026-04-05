from __future__ import annotations

import hashlib
import re
from typing import Iterable


STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "how",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "to",
    "what",
    "when",
    "which",
    "with",
}


def normalize_question(text: str) -> str:
    normalized = re.sub(r"\s+", " ", text.strip())
    return normalized


def tokenize(text: str) -> list[str]:
    tokens = re.findall(r"[a-zA-Z0-9][a-zA-Z0-9\-\+]*", text.lower())
    return [token for token in tokens if token not in STOPWORDS]


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def stable_id(*parts: str) -> str:
    joined = "::".join(parts)
    return content_hash(joined)[:12]


def keyword_overlap(query: str, text: str) -> float:
    query_tokens = set(tokenize(query))
    text_tokens = set(tokenize(text))
    if not query_tokens or not text_tokens:
        return 0.0
    overlap = query_tokens & text_tokens
    return len(overlap) / len(query_tokens)


def split_sentences(text: str, chunk_size: int = 2, max_chunks: int = 4) -> list[str]:
    if not text:
        return []
    normalized = re.sub(r"\s+", " ", text).strip()
    sentences = re.split(r"(?<=[.!?])\s+", normalized)
    chunks: list[str] = []
    bucket: list[str] = []
    for sentence in sentences:
        cleaned = sentence.strip()
        if not cleaned:
            continue
        bucket.append(cleaned)
        if len(bucket) == chunk_size:
            chunks.append(" ".join(bucket))
            bucket = []
        if len(chunks) >= max_chunks:
            break
    if bucket and len(chunks) < max_chunks:
        chunks.append(" ".join(bucket))
    return chunks


def compact_text(parts: Iterable[str], separator: str = " ") -> str:
    return separator.join(part.strip() for part in parts if part and part.strip())
