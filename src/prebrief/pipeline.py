"""Assembly: sources in, brief out.

The selection rules here are deterministic and dull on purpose. No model is
required to produce a brief, and when one is added it will choose ordering
among already-collected claims — never wording, never facts. Dullness is what
makes two runs identical.

Where the rules cannot decide, they decline. An undetermined relationship and a
long "could not find" list are correct outputs, not failures.
"""

from __future__ import annotations

from datetime import date

from .brief import Brief, Gap, GapTopic, MAX_CLAIMS, Relationship
from .claims import Claim, ClaimSet, Tier
from .entities import Entity, Kind, resolve
from .scope import ScopeGate
from .sources.base import RunContext, Source, SourceResult
from .sources.federal_register import FederalRegisterSource
from .sources.gdelt import GdeltSource
from .sources.usaspending import USASpendingSource

__all__ = ["default_sources", "build"]

# How many claims each section may hold. Sums to under the page budget with room
# to spare, because a brief that hits its ceiling reads as padded.
IDENTITY_MAX = 3
MOVEMENT_MAX = 5
CHECK_MAX = 2

STALE_YEARS = 2


def default_sources() -> list[Source]:
    return [FederalRegisterSource(), USASpendingSource(), GdeltSource()]


def build(
    name: str, ctx: RunContext, sources: list[Source] | None = None
) -> tuple[Brief, list[SourceResult]]:
    sources = sources or default_sources()
    entity = resolve(name, ctx.cache)

    results = [source.collect(entity, ctx) for source in sources]

    pool = ClaimSet()
    for result in results:
        pool.extend(result.claims)

    scoped = ScopeGate().filter(pool)
    claims = scoped.kept.as_of(ctx.as_of)

    brief = Brief(entity=entity, as_of=ctx.as_of, claims=claims)
    _fill_sections(brief, ctx)
    brief.relationship, brief.relationship_support = _infer_relationship(brief, results)
    brief.gaps = _find_gaps(sources, results)
    brief.run_notes = _notes(entity, results, scoped)
    _trim_to_budget(brief)
    brief.validate()
    return brief, results


def _fill_sections(brief: Brief, ctx: RunContext) -> None:
    window_start = ctx.window_start
    stale_before = date(ctx.as_of.year - STALE_YEARS, ctx.as_of.month, ctx.as_of.day)

    recent, background, suspect = [], [], []
    for claim in brief.claims:  # already sorted newest-first, best-tier-first
        if claim.tier is Tier.SELF or (claim.published and claim.published < stale_before):
            suspect.append(claim)
        elif claim.published and claim.published >= window_start:
            recent.append(claim)
        else:
            background.append(claim)

    # Structural facts first; if nothing is structural, borrow the oldest recent
    # ones rather than leaving the section empty.
    identity_pool = background or list(reversed(recent))
    brief.identity = [c.id for c in identity_pool[:IDENTITY_MAX]]

    used = set(brief.identity)
    brief.movement = [c.id for c in recent if c.id not in used][:MOVEMENT_MAX]

    used |= set(brief.movement)
    brief.check_first = [c.id for c in suspect if c.id not in used][:CHECK_MAX]


def _infer_relationship(
    brief: Brief, results: list[SourceResult]
) -> tuple[Relationship, list[str]]:
    """The single inference the brief makes. Conservative by construction: when
    the record does not force a reading, it returns undetermined and the meeting
    gets a question instead of a guess."""
    awards = next(
        (r for r in results if r.source == "usaspending" and r.claims), None
    )
    support = [
        c.id for c in (awards.claims if awards else []) if c.id in brief.claims
    ][:2]

    if brief.entity.kind is Kind.INVESTOR:
        return Relationship.INVESTOR, []
    if brief.entity.kind is Kind.GOVERNMENT:
        # An agency that is actively awarding contracts is buying something.
        if support:
            return Relationship.BUYER, support
        return Relationship.REGULATOR, []
    if brief.entity.kind in (Kind.PUBLIC_COMPANY, Kind.PRIVATE_COMPANY) and support:
        # A company winning federal awards is competing for the same budgets.
        return Relationship.COMPETITOR, support
    return Relationship.UNKNOWN, []


def _find_gaps(sources: list[Source], results: list[SourceResult]) -> list[Gap]:
    """A topic is a gap when every source that could have covered it came back
    with nothing. The searched-source list is what makes the gap honest — it
    says where we looked, not just that we failed."""
    by_name = {r.source: r for r in results}
    gaps: list[Gap] = []
    for topic in GapTopic:
        covering = [s for s in sources if topic.value in s.covers]
        if not covering:
            gaps.append(Gap(topic=topic, searched=()))
            continue
        if any(by_name.get(s.name) and by_name[s.name].claims for s in covering):
            continue
        gaps.append(Gap(topic=topic, searched=tuple(sorted(s.name for s in covering))))
    return gaps


def _notes(entity: Entity, results: list[SourceResult], scoped) -> list[str]:
    notes = [r.note for r in results if r.note]
    for result in results:
        if result.widened(entity.name):
            notes.append(
                f'{result.source} matched on the broader term "{result.matched}", '
                f"not the full name — confirm these records describe the right body."
            )
    notes.extend(entity.resolution_notes)
    if scoped.dropped:
        notes.append(
            f"{len(scoped.dropped)} claim(s) about atmospheric data or forecast "
            f"quality were excluded — out of scope for this brief."
        )
    return notes


def _trim_to_budget(brief: Brief) -> None:
    """Cut from the least load-bearing section first. Identity is what makes the
    brief legible at all, so it is trimmed last."""
    while len(brief.used_claim_ids) > MAX_CLAIMS:
        for section in ("check_first", "movement", "identity"):
            bucket: list[str] = getattr(brief, section)
            if bucket:
                bucket.pop()
                break
        else:  # pragma: no cover - unreachable while any section is non-empty
            break
