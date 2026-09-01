"""The brief model.

A brief is not prose. It is a fixed set of sections, each holding claim IDs, plus
two things that are explicitly *not* claims and are labelled as such: one
inference about why the organization matters, and a list of gaps in the public
record. Everything a reader could mistake for a fact is a claim with a URL
behind it.

Structuring it this way is what lets the renderer guarantee that no sentence
reaches the page unsourced. It also means a language model, if one is in the
loop, chooses ordering and selection — never wording of facts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum

from .claims import ClaimSet
from .entities import Entity

__all__ = ["Relationship", "GapTopic", "Gap", "Brief", "MAX_CLAIMS", "MAX_WORDS"]

# A brief that does not fit on one page is not a brief. These are asserted at
# render time, and there is a test that fails if the budget is exceeded.
MAX_CLAIMS = 14
MAX_WORDS = 450

# Nothing is stale in the same way, so "recent" is a parameter, not a constant.
RECENT_DAYS = 180


class Relationship(str, Enum):
    """Why this organization is on the calendar. The one inference the brief
    makes, drawn from a closed vocabulary and always shown with the claims it
    rests on."""

    BUYER = "buyer"
    INVESTOR = "investor"
    COMPETITOR = "competitor"
    PARTNER = "partner"
    REGULATOR = "regulator"
    UNKNOWN = "undetermined"

    def sentence(self, org: str) -> str:
        return {
            "buyer": f"{org} appears on the buying side: it holds a mandate and a budget for what we sell.",
            "investor": f"{org} appears on the capital side: it holds or could hold a position.",
            "competitor": f"{org} competes for the same contracts or the same customers.",
            "partner": f"{org} sits adjacent: a supplier, reseller, or joint-delivery relationship.",
            "regulator": f"{org} sets or enforces rules that bind how we operate.",
            "undetermined": (
                f"The public record does not establish how {org} relates to us. "
                f"Treat the relationship as an open question in the meeting."
            ),
        }[self.value]


class GapTopic(str, Enum):
    """The things a brief looks for. When one comes back empty, that absence is
    itself the output — and it generates the question worth asking."""

    MANDATE = "mandate"
    BUDGET = "budget"
    TIMELINE = "timeline"
    PROCUREMENT = "procurement route"
    RECENT_ACTIVITY = "recent activity"
    DECISION_ROUTE = "decision route"
    RELATIONSHIP = "relationship to us"

    def question(self, org: str) -> str:
        """Templated, never generated. A question is well-formed exactly when
        the public record cannot answer it."""
        return {
            "mandate": f"What is {org} actually chartered to do, and what falls outside it?",
            "budget": "What budget line does this sit on, and for which fiscal year?",
            "timeline": "What is the next date on your side that we should be working back from?",
            "procurement route": "Through which vehicle would something like this actually get bought?",
            "recent activity": f"What has changed at {org} in the last six months that is not public?",
            "decision route": "Which office signs off, and who else has to agree before it does?",
            "relationship to us": "How do you see the relationship between our organizations today?",
        }[self.value]


@dataclass(frozen=True, slots=True)
class Gap:
    """A thing we looked for and did not find, with what was searched."""

    topic: GapTopic
    searched: tuple[str, ...]

    @property
    def line(self) -> str:
        if not self.searched:
            return f"{self.topic.value} — no source in this run covers it"
        return f"{self.topic.value} — searched {', '.join(self.searched)}, nothing found"


@dataclass(slots=True)
class Brief:
    entity: Entity
    as_of: date
    claims: ClaimSet

    # Section 1: who they are
    identity: list[str] = field(default_factory=list)
    # Section 2: why they matter — the inference, plus its supporting claims
    relationship: Relationship = Relationship.UNKNOWN
    relationship_support: list[str] = field(default_factory=list)
    # Section 3: what moved
    movement: list[str] = field(default_factory=list)
    # Set when the reader's domain filter emptied the section: says plainly
    # that things moved, just not in our market. Never a fallback to
    # unfiltered results.
    movement_note: str | None = None
    # Section 5: claims that are stale, self-reported only, or contradicted
    check_first: list[str] = field(default_factory=list)
    # Sections 4 and 6 both come from here
    gaps: list[Gap] = field(default_factory=list)

    # Anything the run wants the reader to know about how it went
    run_notes: list[str] = field(default_factory=list)

    @property
    def used_claim_ids(self) -> list[str]:
        seen, out = set(), []
        for group in (
            self.identity,
            self.relationship_support,
            self.movement,
            self.check_first,
        ):
            for claim_id in group:
                if claim_id not in seen:
                    seen.add(claim_id)
                    out.append(claim_id)
        return out

    @property
    def questions(self) -> list[str]:
        """At most five, derived from gaps in a stable order."""
        return [g.topic.question(self.entity.name) for g in self.gaps][:5]

    def validate(self) -> None:
        """Every ID referenced by a section must exist in the claim set, and the
        brief must fit on a page."""
        for claim_id in self.used_claim_ids:
            self.claims.get(claim_id)  # raises UnsourcedText if absent
        if len(self.used_claim_ids) > MAX_CLAIMS:
            raise ValueError(
                f"{len(self.used_claim_ids)} claims used, budget is {MAX_CLAIMS}. "
                "A brief that needs more than that is a research report, and "
                "nobody reads one of those before a meeting."
            )
