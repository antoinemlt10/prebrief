"""The reader — whose meeting this brief is for.

The relevance gate tests whether a document is about the entity. That is not
enough for an agency that does a hundred things: every coral-reef notice is
genuinely about NOAA, and none of it belongs in a brief prepared for a
commercial-data meeting. The reader's domain says what business we are in;
"What moved" keeps only claims that touch it.

Disjoint by design from the scope gate (scope.py): the domain holds
market-and-procurement words, the scope gate holds the science this tool has
no standing to opine on. A term in both would be admitted by one filter and
dropped by the other.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .claims import Claim
from .sources.base import _fold

__all__ = ["Reader", "load_reader"]


@dataclass(frozen=True, slots=True)
class Reader:
    domain: tuple[str, ...]

    def in_domain(self, claim: Claim) -> bool:
        """Does this claim touch what the reader's organization actually does?
        Tested on the claim text and its snippet, word-bounded, punctuation
        folded — the same matching the relevance gate uses."""
        haystack = f" {_fold(claim.text)} {_fold(claim.snippet)} "
        return any(f" {_fold(term)} " in haystack for term in self.domain if term)


def load_reader(path: Path) -> Reader | None:
    """Read reader.yaml. A missing file means no reader is configured and
    "What moved" goes unfiltered — the tool never invents a domain."""
    if not path.exists():
        return None
    import yaml

    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    terms = tuple(t.strip() for t in data.get("domain") or [] if t and t.strip())
    return Reader(domain=terms) if terms else None
