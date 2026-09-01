"""Claims — the only unit of fact in prebrief.

Nothing reaches a rendered brief except through a Claim, and every Claim carries
the verbatim span of source text that supports it. If you find yourself wanting
to write a sentence that is not a Claim, that is the design telling you the fact
is not sourced.

Claim IDs are content-derived, so the same fact from the same source gets the
same ID on every run. That is what makes a brief diffable across dates.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from enum import Enum

__all__ = ["Tier", "Claim", "ClaimSet", "UnsourcedText"]


class UnsourcedText(Exception):
    """Raised when text reaches the renderer without a Claim behind it."""


class Tier(str, Enum):
    """Where a fact comes from, ranked by how much weight it can bear.

    A number in an SEC filing and a number in a press release are not the same
    kind of fact. The brief prints the tier so the reader can discount
    accordingly instead of trusting everything equally.
    """

    FILED = "filed"  # statutory record: EDGAR, USAspending, Federal Register
    REPORTED = "reported"  # third-party press
    SELF = "self-reported"  # the organization's own site or release

    @property
    def rank(self) -> int:
        return {"filed": 0, "reported": 1, "self-reported": 2}[self.value]


# A claim's text is a statement of record, not an assessment. These words are
# how opinion sneaks into something that is supposed to be a transcript.
_EDITORIALS = re.compile(
    r"\b(?:crucial|critical|vital|impressive|leading|best-in-class|world-class|"
    r"cutting-edge|revolutionary|significant|major|strong|weak|promising|"
    r"troubling|exciting|remarkable)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class Claim:
    """One sourced statement.

    text     — a single sentence of record, no adjectives of appreciation
    snippet  — the verbatim span from the source that supports `text`
    tier     — provenance, see Tier
    """

    text: str
    snippet: str
    source_url: str
    source_title: str
    tier: Tier
    published: date | None = None
    retrieved: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ValueError("claim text is empty")
        if not self.snippet.strip():
            raise ValueError(f"claim has no supporting snippet: {self.text!r}")
        if not self.source_url.startswith(("http://", "https://")):
            raise ValueError(f"claim source is not a URL: {self.source_url!r}")
        # Quoted spans are somebody else's words — a filing titled "Significant
        # New Use Rule" is a fact, not an opinion. Only unquoted text is judged.
        unquoted = re.sub(r"[\"“][^\"”]*[\"”]", "", self.text)
        if editorial := _EDITORIALS.search(unquoted):
            raise ValueError(
                f"claim text editorializes ({editorial.group(0)!r}): {self.text!r}. "
                "State the record; let the reader judge."
            )

    @property
    def id(self) -> str:
        """Deterministic, content-derived. Same fact + same source = same ID."""
        digest = hashlib.sha256(
            f"{self.source_url}\x00{self.snippet}".encode()
        ).hexdigest()
        return digest[:12]

    def supported_by(self, document_text: str) -> bool:
        """Is the snippet still present in the source? Used by `prebrief verify`
        to catch silent edits and link rot."""
        return _normalize(self.snippet) in _normalize(document_text)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "text": self.text,
            "snippet": self.snippet,
            "source_url": self.source_url,
            "source_title": self.source_title,
            "tier": self.tier.value,
            "published": self.published.isoformat() if self.published else None,
            "retrieved": self.retrieved.isoformat(),
        }


def _normalize(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().casefold()


class ClaimSet:
    """An ordered, de-duplicated collection of claims for one entity.

    Ordering is deterministic — newest first, then by tier, then by ID — so two
    runs over the same inputs produce byte-identical output.
    """

    def __init__(self, claims: list[Claim] | None = None) -> None:
        self._by_id: dict[str, Claim] = {}
        for claim in claims or []:
            self.add(claim)

    def add(self, claim: Claim) -> Claim:
        """Add a claim. A duplicate ID keeps whichever claim has the better tier
        — the same fact reported by the press and filed with a regulator should
        read as filed."""
        existing = self._by_id.get(claim.id)
        if existing is None or claim.tier.rank < existing.tier.rank:
            self._by_id[claim.id] = claim
        return self._by_id[claim.id]

    def extend(self, claims: list[Claim]) -> None:
        for claim in claims:
            self.add(claim)

    def get(self, claim_id: str) -> Claim:
        try:
            return self._by_id[claim_id]
        except KeyError:
            raise UnsourcedText(f"no claim with id {claim_id!r}") from None

    def since(self, cutoff: date) -> list[Claim]:
        return [c for c in self if c.published and c.published >= cutoff]

    def as_of(self, cutoff: date) -> "ClaimSet":
        """Drop anything published after `cutoff`. This is what makes a run
        reproducible: pin the date, get the same brief forever."""
        return ClaimSet([c for c in self if not c.published or c.published <= cutoff])

    def __iter__(self):
        return iter(
            sorted(
                self._by_id.values(),
                key=lambda c: (
                    -(c.published.toordinal() if c.published else 0),
                    c.tier.rank,
                    c.id,
                ),
            )
        )

    def __len__(self) -> int:
        return len(self._by_id)

    def __contains__(self, claim_id: object) -> bool:
        return claim_id in self._by_id
