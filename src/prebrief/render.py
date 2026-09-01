"""Rendering, and the invariant that makes the output trustworthy.

`render_markdown` builds a brief out of two things only: chrome (headings and a
small closed set of fixed lines) and claim text. Nothing else can get in.

`assert_sourced` then re-reads the rendered markdown from scratch and checks that
every content line resolves either to chrome or to a claim in the set. It does
not trust the renderer; it parses the output the way a reader would. That is
what turns "the model cannot introduce facts" from a hope into a property.
"""

from __future__ import annotations

import csv
import io
import json
import re
from datetime import date

from .brief import MAX_CLAIMS, MAX_WORDS, Brief
from .claims import Claim, ClaimSet, UnsourcedText

__all__ = ["render_markdown", "render_json", "render_sources_csv", "assert_sourced"]

# Every fixed string the renderer is allowed to emit. If a line is not chrome
# and not a claim, the brief does not get written.
CHROME = frozenset(
    {
        "## Who they are",
        "## Why they matter",
        "## What moved",
        "## Questions to ask",
        "## Check before the meeting",
        "## What I could not find",
        "> The one inference in this brief. Everything else is sourced.",
        "---",
        "*Nothing above is asserted without a source. Numbers marked `filed` come "
        "from a statutory record; `reported` from press; `self-reported` from the "
        "organization itself.*",
    }
)

_CLAIM_LINE = re.compile(r"^- (?P<text>.+?) \[\^(?P<id>[0-9a-f]{12})\]$")
_QUESTION_LINE = re.compile(r"^\d+\. (?P<text>.+)$")
_FOOTNOTE = re.compile(r"^\[\^(?P<id>[0-9a-f]{12})\]: ")
_RESTING = re.compile(r"^Resting on: (?:\[\^[0-9a-f]{12}\](?:, )?)+$")


class BriefTooLong(Exception):
    """The one-page budget was blown. Cut claims, do not raise the ceiling."""


def render_markdown(brief: Brief) -> str:
    brief.validate()
    claims = brief.claims
    out: list[str] = []

    out.append(f"# {brief.entity.name}")
    out.append("")
    out.append(_header_line(brief))
    out.append("")

    if brief.identity:
        out.append("## Who they are")
        out.extend(_claim_lines(brief.identity, claims))
        out.append("")

    out.append("## Why they matter")
    out.append("> The one inference in this brief. Everything else is sourced.")
    out.append("")
    out.append(f"- {brief.relationship.sentence(brief.entity.name)}")
    if brief.relationship_support:
        refs = ", ".join(f"[^{cid}]" for cid in brief.relationship_support)
        out.append(f"Resting on: {refs}")
    out.append("")

    out.append("## What moved")
    out.extend(_claim_lines(brief.movement, claims) or ["- Nothing found in the window."])
    out.append("")

    if questions := brief.questions:
        out.append("## Questions to ask")
        out.extend(f"{i}. {q}" for i, q in enumerate(questions, 1))
        out.append("")

    if brief.check_first:
        out.append("## Check before the meeting")
        out.extend(_claim_lines(brief.check_first, claims))
        out.append("")

    out.append("## What I could not find")
    out.extend(f"- {gap.line}" for gap in brief.gaps)
    for note in brief.run_notes:
        out.append(f"- {note}")
    out.append("")

    out.append("---")
    out.append("")
    for claim_id in brief.used_claim_ids:
        out.append(_footnote(claims.get(claim_id)))
    out.append("")
    out.append(CHROME_PROVENANCE)

    markdown = "\n".join(out).rstrip() + "\n"
    _assert_within_budget(brief, markdown)
    assert_sourced(markdown, brief)
    return markdown


CHROME_PROVENANCE = (
    "*Nothing above is asserted without a source. Numbers marked `filed` come "
    "from a statutory record; `reported` from press; `self-reported` from the "
    "organization itself.*"
)


def _header_line(brief: Brief) -> str:
    bits = [
        f"As of {brief.as_of.isoformat()}",
        brief.entity.kind.value,
        f"{len(brief.used_claim_ids)} sourced statements",
    ]
    if brief.entity.thin:
        bits.append("thin public record")
    return " · ".join(bits)


def _claim_lines(claim_ids: list[str], claims: ClaimSet) -> list[str]:
    return [f"- {claims.get(cid).text} [^{cid}]" for cid in claim_ids]


def _footnote(claim: Claim) -> str:
    published = claim.published.isoformat() if claim.published else "undated"
    title = claim.source_title.replace("]", ")").replace("[", "(")
    return (
        f"[^{claim.id}]: [{title}]({claim.source_url}) · "
        f"{claim.tier.value} · {published}"
    )


def _assert_within_budget(brief: Brief, markdown: str) -> None:
    body = markdown.split("\n---\n", 1)[0]
    words = len(body.split())
    if words > MAX_WORDS:
        raise BriefTooLong(
            f"{brief.entity.slug}: {words} words, budget is {MAX_WORDS}. "
            "Drop the weakest claims rather than raising the ceiling — the "
            "budget is the product."
        )
    if len(brief.used_claim_ids) > MAX_CLAIMS:
        raise BriefTooLong(
            f"{brief.entity.slug}: {len(brief.used_claim_ids)} claims, "
            f"budget is {MAX_CLAIMS}."
        )


def assert_sourced(markdown: str, brief: Brief) -> None:
    """Re-read the rendered brief and prove every content line is either chrome
    or a claim. Parses the output rather than trusting how it was built."""
    allowed_questions = set(brief.questions)
    allowed_gaps = {f"- {gap.line}" for gap in brief.gaps}
    allowed_notes = {f"- {note}" for note in brief.run_notes}
    relationship = f"- {brief.relationship.sentence(brief.entity.name)}"
    header = _header_line(brief)
    title = f"# {brief.entity.name}"
    empty_movement = "- Nothing found in the window."

    for lineno, line in enumerate(markdown.splitlines(), 1):
        stripped = line.rstrip()
        if not stripped:
            continue
        if stripped in CHROME or stripped in (title, header, relationship):
            continue
        if stripped in allowed_gaps or stripped in allowed_notes:
            continue
        if stripped == empty_movement or _RESTING.match(stripped):
            continue
        if _FOOTNOTE.match(stripped):
            claim_id = _FOOTNOTE.match(stripped)["id"]
            brief.claims.get(claim_id)  # raises if unknown
            continue
        if match := _QUESTION_LINE.match(stripped):
            if match["text"] in allowed_questions:
                continue
            raise UnsourcedText(f"line {lineno}: invented question: {stripped!r}")
        if match := _CLAIM_LINE.match(stripped):
            claim = brief.claims.get(match["id"])
            if claim.text != match["text"]:
                raise UnsourcedText(
                    f"line {lineno}: text does not match claim {match['id']}. "
                    f"Rendered {match['text']!r}, claim says {claim.text!r}."
                )
            continue
        raise UnsourcedText(
            f"line {lineno}: prose with no claim behind it: {stripped!r}. "
            "Every factual sentence must be a Claim carrying its source."
        )


def render_json(brief: Brief) -> str:
    """The machine-readable twin. This, not the markdown, is what the next
    automation in the chain should read."""
    payload = {
        "entity": brief.entity.to_dict(),
        "as_of": brief.as_of.isoformat(),
        "relationship": {
            "value": brief.relationship.value,
            "inferred": True,
            "supported_by": brief.relationship_support,
        },
        "sections": {
            "identity": brief.identity,
            "movement": brief.movement,
            "check_first": brief.check_first,
        },
        "questions": brief.questions,
        "gaps": [
            {"topic": g.topic.value, "searched": list(g.searched)} for g in brief.gaps
        ],
        "run_notes": brief.run_notes,
        "claims": [brief.claims.get(cid).to_dict() for cid in brief.used_claim_ids],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def render_sources_csv(brief: Brief) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["claim_id", "tier", "published", "title", "url"])
    for claim_id in brief.used_claim_ids:
        claim = brief.claims.get(claim_id)
        writer.writerow(
            [
                claim.id,
                claim.tier.value,
                claim.published.isoformat() if claim.published else "",
                claim.source_title,
                claim.source_url,
            ]
        )
    return buffer.getvalue()
