"""The scope gate.

This tool prepares the CEO's side of a meeting: who the organization is, what it
is mandated to do, what it has bought or filed, what moved recently. It has no
business having a view on atmospheric science, forecast skill, or model
benchmarks. That subject belongs to people who are qualified to hold it.

So claims that wander into it are dropped before rendering. Unlike the privacy
gate this one excludes rather than fails — a source document will naturally
contain technical material, and discarding it is the correct, quiet outcome.
Every drop is recorded so the run can explain itself.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .claims import Claim, ClaimSet

__all__ = ["ScopeGate", "ScopeReport"]

# Terms that mean a sentence is making a claim about atmospheric data or
# forecast quality. Being over-broad here is cheap: it drops a claim we did not
# need. Being under-broad puts an opinion in the brief we have no standing for.
#
# Disjoint by design from reader.yaml: that file holds the market-and-
# procurement words that define the reader's business; this regex holds the
# science the tool must not touch. Never let a term appear in both.
_OUT_OF_SCOPE = re.compile(
    r"\b(?:"
    r"forecast(?:ing)?\s+(?:skill|accuracy|error|quality|performance)|"
    r"model\s+(?:skill|accuracy|error|resolution|benchmark)|"
    r"anomaly\s+correlation|RMSE|MAE|bias\s+correction|hindcast|reanalysis|"
    r"radiosonde|dropsonde|sounding|radio\s+occultation|GNSS-?RO|"
    r"assimilat\w+|ensemble\s+member|lead\s+time|"
    r"troposphere|stratosphere|atmospheric\s+(?:profile|column|sounding)|"
    r"geopotential|dewpoint|wind\s+shear|"
    r"beats?\s+(?:the\s+)?(?:IFS|GFS|ECMWF|HRRR)|"
    r"more\s+accurate\s+than"
    r")\b",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class ScopeReport:
    kept: ClaimSet
    dropped: list[tuple[Claim, str]]

    @property
    def summary(self) -> str:
        if not self.dropped:
            return "scope gate: nothing dropped"
        return (
            f"scope gate: dropped {len(self.dropped)} claim(s) about "
            f"atmospheric data or forecast quality"
        )


class ScopeGate:
    """Drops claims that stray into the science. Also usable as a predicate."""

    def out_of_scope(self, claim: Claim) -> str | None:
        """Return the offending phrase, or None if the claim is in scope.
        Both the claim text and its supporting snippet are checked — a neutral
        sentence quoting a technical passage is still importing the subject."""
        for field_name, value in (("text", claim.text), ("snippet", claim.snippet)):
            if match := _OUT_OF_SCOPE.search(value):
                return f"{match.group(0)!r} in {field_name}"
        return None

    def filter(self, claims: ClaimSet) -> ScopeReport:
        kept, dropped = ClaimSet(), []
        for claim in claims:
            if reason := self.out_of_scope(claim):
                dropped.append((claim, reason))
            else:
                kept.add(claim)
        return ScopeReport(kept=kept, dropped=dropped)
