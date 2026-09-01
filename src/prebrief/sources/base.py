"""What a source is.

A source knows how to query one public corpus for one entity and turn what it
finds into Claims. It never returns prose — only Claims, each carrying the span
of source text that supports it.

Sources fail soft. A dead API, a rate limit, a missing key: the run continues,
the source records why it produced nothing, and that reason ends up in the
brief's "what I could not find" section. A brief that silently omits a source is
worse than one that says the source was unreachable.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field, replace
from datetime import date
from typing import Protocol, runtime_checkable

from ..cache import Cache, Response
from ..claims import Claim
from ..entities import Entity

__all__ = [
    "RunContext",
    "SourceResult",
    "Source",
    "snippet_around",
    "clean",
    "relevant",
    "stamped",
    "titlecase_org",
    "unreachable",
]


# Legal-entity designators that stay upper-case when a shouted name is calmed.
_KEEP_UPPER = frozenset(
    {"LLC", "L.L.C.", "INC", "INC.", "LP", "LLP", "PLC", "PBC", "USA", "US",
     "LTD", "AG", "SA", "NV", "BV", "SE", "GMBH", "AS", "OY", "AB"}
)


def titlecase_org(name: str) -> str:
    """USAspending and SAM return recipient names in block capitals.

    Two reasons to calm them down. A brief reads better in prose case, and a
    name tagger reads ALL CAPS as a person — "SPIRE GLOBAL SUBSIDIARY" tripped
    the privacy gate and blocked a legitimate brief from being written.
    """
    if not name or not name.isupper():
        return name
    words = []
    for word in name.split():
        core = word.strip(".,")
        words.append(word if core in _KEEP_UPPER else word.title())
    return " ".join(words)


_FOLD = re.compile(r"[^a-z0-9]+")


def _fold(text: str) -> str:
    """Lowercase, punctuation to single spaces. "In - Q - Tel" and "In-Q-Tel"
    fold to the same string, so a source's spacing quirks cannot hide a name."""
    return _FOLD.sub(" ", text.casefold()).strip()


def relevant(document_text: str, entity) -> bool:
    """Is this document actually about the entity? Runs on every match.

    An exact-term match proves nothing: the Federal Register searches full
    text, so a document that lists an organization once among three hundred
    licensees comes back as a hit. FCC fee schedules filled the Spire brief
    that way. A document qualifies only when the entity is named in the text
    given here — for the Register that is title plus abstract, never the body.

    "Named" means: the full name, an adjacent word-pair from it, the derived
    initialism (NOAA for the seven-word official name — three letters minimum,
    so "Spire Global" never becomes "SG" and matches everything), or a Wikidata
    alias of three or more characters. All matched on word boundaries.
    """
    haystack = f" {_fold(clean(document_text))} "
    needles = [entity.name, *entity.name_bigrams()]
    if initialism := entity.initialism():
        needles.append(initialism)
    needles.extend(a for a in entity.aliases if len(a) >= 3)
    return any(f" {_fold(n)} " in haystack for n in needles if n and _fold(n))


def stamped(claims: list[Claim], response: Response) -> list[Claim]:
    """Stamp claims with the moment their evidence was actually fetched.

    A claim built from a cached response was retrieved when the cache fetched
    it, not when this run constructed the object. Using the cache's clock is
    also what keeps brief.json byte-identical on a warm cache."""
    return [replace(c, retrieved=response.fetched_at) for c in claims]


def unreachable(source_name: str, exc: Exception) -> str:
    """A note a reader can understand, from an exception they cannot.

    Never interpolate an exception's message into a brief. A urllib traceback
    carries hostnames, proxy strings and capitalised fragments that a name
    tagger reads as people — which is how the privacy gate first caught this.
    Only the exception's type survives.
    """
    return (
        f"{source_name} could not be reached from this machine "
        f"({type(exc).__name__}); its coverage is missing from this brief."
    )


@dataclass(slots=True)
class RunContext:
    cache: Cache
    as_of: date
    window_days: int = 365  # one federal procurement cycle; see cli.py
    refresh: bool = False

    @property
    def window_start(self) -> date:
        return date.fromordinal(max(1, self.as_of.toordinal() - self.window_days))

    def key(self, env_var: str) -> str | None:
        value = os.environ.get(env_var, "").strip()
        return value or None


@dataclass(slots=True)
class SourceResult:
    """What one source produced, and — when it produced nothing — why."""

    source: str
    claims: list[Claim] = field(default_factory=list)
    note: str | None = None  # only set when the source could not do its job
    matched: str | None = None  # the query term that actually answered

    @property
    def ok(self) -> bool:
        return self.note is None

    def widened(self, entity_name: str) -> bool:
        """True when the hit came from a broader term than the name asked for.
        The brief flags this: a match on the parent organization is weaker
        evidence than a match on the entity itself."""
        return bool(self.matched) and self.matched.casefold() != entity_name.casefold()


@runtime_checkable
class Source(Protocol):
    name: str
    covers: tuple[str, ...]  # gap topics this source can speak to
    env_key: str | None  # environment variable holding an API key, if any

    def collect(self, entity: Entity, ctx: RunContext) -> SourceResult: ...


_WHITESPACE = re.compile(r"\s+")
_TAGS = re.compile(r"<[^>]+>")


def clean(text: str) -> str:
    """Collapse a fragment of source text into one line, so a snippet stored
    today still matches the same passage fetched tomorrow."""
    return _WHITESPACE.sub(" ", _TAGS.sub(" ", text or "")).strip()


def snippet_around(haystack: str, needle: str, width: int = 220) -> str:
    """A verbatim span from the source containing `needle`.

    This is the evidence a Claim carries, so it is taken from the document as it
    was fetched, never reworded. If the needle is not present we return the head
    of the document rather than inventing support.
    """
    text = clean(haystack)
    if not text:
        return ""
    position = text.casefold().find(needle.casefold())
    if position < 0:
        return text[:width].strip()
    start = max(0, position - width // 3)
    return text[start : start + width].strip()
