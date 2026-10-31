"""Turn a failure message into a signature, so the same root cause seen in different
tests and runs groups together: numbers, hex addresses, temporary paths, quoted values
and timings are replaced with placeholders before comparing."""

from __future__ import annotations

import hashlib
import re

_RULES = [
    (re.compile(r"0x[0-9a-fA-F]+"), "<hex>"),
    (re.compile(r"(/tmp|/var/folders|/private)[^\s'\"]*"), "<tmp>"),
    (re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b"), "<uuid>"),
    (re.compile(r"'[^']*'|\"[^\"]*\""), "<str>"),
    (re.compile(r"\b\d+(\.\d+)?\s*(ms|s|sec|seconds)\b"), "<time>"),
    (re.compile(r"\b\d+(\.\d+)?\b"), "<n>"),
]


def normalise(message: str) -> str:
    first = message.strip().splitlines()[0] if message.strip() else ""
    for pattern, repl in _RULES:
        first = pattern.sub(repl, first)
    return re.sub(r"\s+", " ", first).strip()


def signature(message: str) -> str:
    norm = normalise(message)
    return hashlib.sha1(norm.encode()).hexdigest()[:10] if norm else ""
