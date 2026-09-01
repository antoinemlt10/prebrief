"""The two hard rules, as tests.

If these pass, the claims in the README are properties of the code rather than
promises about it.
"""

from __future__ import annotations

from datetime import date

import pytest

from prebrief.brief import Brief, Gap, GapTopic, Relationship
from prebrief.claims import Claim, ClaimSet, Tier, UnsourcedText
from prebrief.entities import Entity, Kind, _term_ladder
from prebrief.privacy import MissingNERModel, PersonNameFound, PrivacyGate
from prebrief.render import BriefTooLong, assert_sourced, render_markdown
from prebrief.sources.base import relevant
from prebrief.scope import ScopeGate


def claim(text: str, *, snippet: str | None = None, url: str | None = None) -> Claim:
    return Claim(
        text=text,
        snippet=snippet or text,
        source_url=url or "https://example.gov/record",
        source_title="A public record",
        tier=Tier.FILED,
        published=date(2026, 8, 13),
    )


# ---------------------------------------------------------------- claims


def test_a_claim_cannot_exist_without_a_snippet():
    with pytest.raises(ValueError, match="no supporting snippet"):
        Claim(
            text="The program awarded a contract.",
            snippet="   ",
            source_url="https://example.gov/x",
            source_title="t",
            tier=Tier.FILED,
        )


def test_a_claim_cannot_editorialize():
    with pytest.raises(ValueError, match="editorializes"):
        claim("This is a significant expansion of the program.")


def test_claim_ids_are_stable_across_runs():
    first = claim("The program published a delivery order.")
    second = claim("The program published a delivery order.")
    assert first.id == second.id
    assert len(first.id) == 12


def test_better_provenance_wins_on_duplicate():
    reported = Claim(
        text="x",
        snippet="same snippet",
        source_url="https://example.gov/a",
        source_title="t",
        tier=Tier.REPORTED,
    )
    filed = Claim(
        text="x",
        snippet="same snippet",
        source_url="https://example.gov/a",
        source_title="t",
        tier=Tier.FILED,
    )
    claims = ClaimSet([reported, filed])
    assert len(claims) == 1
    assert claims.get(filed.id).tier is Tier.FILED


def test_as_of_excludes_later_documents():
    claims = ClaimSet([claim("Published in August.")])
    assert len(claims.as_of(date(2026, 8, 1))) == 0
    assert len(claims.as_of(date(2026, 12, 1))) == 1


# ---------------------------------------------------------------- privacy


def _gate_or_skip(**kwargs) -> PrivacyGate:
    gate = PrivacyGate(**kwargs)
    try:
        gate.find("A sentence.")
    except MissingNERModel as exc:  # pragma: no cover - environment dependent
        pytest.skip(str(exc))
    return gate


def test_a_person_name_in_the_output_is_a_build_failure():
    gate = _gate_or_skip()
    with pytest.raises(PersonNameFound):
        gate.assert_clean(
            "The program office is led by Katherine Whitfield, who joined in 2024."
        )


def test_an_eponymous_organization_is_not_a_person():
    gate = _gate_or_skip(allow=["Khosla Ventures"])
    gate.assert_clean("Khosla Ventures co-led the round.")


def test_organization_only_text_passes():
    gate = _gate_or_skip()
    gate.assert_clean(
        "The Commercial Data Program announced two contract awards totaling "
        "$6.4 million on 13 August 2026."
    )


# ---------------------------------------------------------------- scope


def test_forecast_quality_claims_are_dropped():
    gate = ScopeGate()
    claims = ClaimSet(
        [
            claim("The agency awarded a delivery order worth $3.67 million."),
            claim("The vendor reported lower RMSE than the operational baseline."),
        ]
    )
    report = gate.filter(claims)
    assert len(report.kept) == 1
    assert len(report.dropped) == 1
    assert "RMSE" in report.dropped[0][1]


def test_scope_gate_also_reads_the_snippet():
    gate = ScopeGate()
    sneaky = claim(
        "The filing describes the company's data products.",
        snippet="Our radio occultation profiles improve assimilation.",
    )
    assert gate.out_of_scope(sneaky) is not None


# ---------------------------------------------------------------- rendering


def _brief(**overrides) -> Brief:
    facts = [
        claim("The program is directed by statute to procure commercial data."),
        claim("It announced $6.4 million in contract awards on 13 August 2026."),
    ]
    claims = ClaimSet(facts)
    brief = Brief(
        entity=Entity(
            name="A Federal Program", slug="a-federal-program", kind=Kind.GOVERNMENT
        ),
        as_of=date(2026, 8, 31),
        claims=claims,
        identity=[facts[0].id],
        relationship=Relationship.BUYER,
        relationship_support=[facts[0].id],
        movement=[facts[1].id],
        gaps=[Gap(topic=GapTopic.TIMELINE, searched=("usaspending", "federal register"))],
    )
    for key, value in overrides.items():
        setattr(brief, key, value)
    return brief


def test_a_rendered_brief_is_entirely_sourced():
    brief = _brief()
    markdown = render_markdown(brief)
    assert_sourced(markdown, brief)  # renders already assert; this is the reader's pass
    assert "[^" in markdown


def test_prose_smuggled_into_the_output_is_caught():
    brief = _brief()
    markdown = render_markdown(brief)
    tampered = markdown.replace(
        "## What moved",
        "## What moved\n- They are likely to expand the program next year.",
    )
    with pytest.raises(UnsourcedText, match="no claim behind it"):
        assert_sourced(tampered, brief)


def test_editing_a_claim_line_without_editing_the_claim_is_caught():
    brief = _brief()
    markdown = render_markdown(brief)
    tampered = markdown.replace("$6.4 million", "$64 million")
    with pytest.raises(UnsourcedText, match="does not match claim"):
        assert_sourced(tampered, brief)


def test_an_invented_question_is_caught():
    brief = _brief()
    markdown = render_markdown(brief)
    tampered = markdown.replace(
        "## Questions to ask", "## Questions to ask\n9. Who should we bribe?"
    )
    with pytest.raises(UnsourcedText, match="invented question"):
        assert_sourced(tampered, brief)


def test_the_one_page_budget_is_enforced():
    long_claims = [claim(f"Record number {i} was filed with the agency.") for i in range(20)]
    brief = _brief()
    brief.claims = ClaimSet(long_claims)
    brief.identity = [c.id for c in long_claims]
    brief.relationship_support = []
    brief.movement = []
    with pytest.raises(ValueError, match="budget is 14"):
        render_markdown(brief)


def test_rendering_is_byte_identical_across_runs():
    assert render_markdown(_brief()) == render_markdown(_brief())


def test_a_thin_entity_still_produces_a_brief():
    brief = _brief()
    brief.entity = Entity(name="A Private Fund", slug="a-private-fund")
    brief.gaps = [
        Gap(topic=t, searched=("wikidata", "edgar"))
        for t in (GapTopic.MANDATE, GapTopic.BUDGET, GapTopic.DECISION_ROUTE)
    ]
    markdown = render_markdown(brief)
    assert "thin public record" in markdown
    assert "## What I could not find" in markdown


# ---------------------------------------------------------------- query terms


def test_a_long_official_name_widens_to_searchable_terms():
    """The first live run returned two empty briefs because every source was
    queried with the exact string typed. This is the guard against that."""
    ladder = _term_ladder("NOAA NESDIS Commercial Data Program")
    assert ladder[0] == "NOAA NESDIS Commercial Data Program"
    assert "Commercial Data Program" in ladder
    assert "NOAA NESDIS" in ladder
    assert ladder == list(dict.fromkeys(ladder)), "terms must be de-duplicated"


def test_the_ladder_stops_before_a_bare_acronym():
    """The second live run over-corrected: falling back to "NOAA" filled the
    brief with Pacific cod reallocations and marine mammal notices. An off-topic
    brief is worse than an empty one."""
    assert "NOAA" not in _term_ladder("NOAA NESDIS Commercial Data Program")
    # A short name is different — there is nothing else to search on.
    assert "NASA" in _term_ladder("NASA")


def test_trailing_filler_is_dropped_but_the_name_survives():
    assert _term_ladder("Galvanize Climate Solutions") == [
        "Galvanize Climate Solutions",
        "Galvanize Climate",
    ]


def test_a_short_name_yields_only_itself():
    assert _term_ladder("Spire Global") == ["Spire Global"]


def test_the_ladder_never_strips_to_one_generic_word():
    for name in ("Data Systems", "Climate Solutions", "Acme Corp"):
        assert _term_ladder(name)[0] == name
        assert all(len(t.split()) >= 2 for t in _term_ladder(name))


# ---------------------------------------------------------------- relevance


def _entity(name: str) -> Entity:
    from prebrief.entities import slugify

    return Entity(name=name, slug=slugify(name))


def test_a_widened_match_must_still_be_about_the_entity():
    """Every string below came back from a real run against live APIs while
    searching for the Commercial Data Program."""
    cdp = _entity("NOAA NESDIS Commercial Data Program")
    noise = [
        "Fisheries of the Exclusive Economic Zone Off Alaska; Reallocation of "
        "Pacific Cod in the Bering Sea and Aleutian Islands Management Area",
        "Takes of Marine Mammals Incidental to Specified Activities",
        "North Pacific Fishery Management Council; Public Meeting",
        "PYMNTS | Optimization Strategies for Payment Performance",
        "Braintree Statistics By Country And Facts ( 2026 )",
    ]
    for headline in noise:
        assert not relevant(headline, cdp), headline


def test_a_widened_match_keeps_a_document_that_is_on_topic():
    cdp = _entity("NOAA NESDIS Commercial Data Program")
    assert relevant("NESDIS Commercial Data Program announces contract awards", cdp)
    assert relevant(
        "The agency will procure commercial data under an existing vehicle.", cdp
    )


def test_an_exact_term_match_is_not_trusted_blindly():
    """The Federal Register searches full text, so a document that mentions an
    organization once among three hundred licensees comes back as a match.
    Every title below is a real one that reached a brief this way. None is
    about the organization it was filed under."""
    spire = _entity("Spire Global")
    assert not relevant(
        "Review of the Commission's Assessment and Collection of Regulatory "
        "Fees for Fiscal Year 2025",
        spire,
    )
    iqt = _entity("In-Q-Tel")
    assert not relevant("Facilitating Opportunities for Advanced Air Mobility", iqt)
    assert not relevant("Advanced Technology Program Advisory Committee", iqt)


def test_the_derived_initialism_keeps_the_agency_notices():
    """Requiring the full name would silence every Federal Register notice
    that says NOAA — the fix for full-text noise must not blind the test to
    how documents actually name an agency."""
    noaa = _entity("National Oceanic and Atmospheric Administration")
    assert noaa.initialism() == "NOAA"
    assert relevant(
        "Solicitation of Nominations for Membership on the NOAA Science "
        "Advisory Board",
        noaa,
    )
    # Two-word names must not shrink to a two-letter net that catches everything.
    assert _entity("Spire Global").initialism() is None


def test_a_document_naming_the_entity_in_its_abstract_qualifies():
    """The 2002 committee notice names In-Q-Tel in its abstract — hyphens and
    a source's spacing quirks must not hide the name."""
    iqt = _entity("In-Q-Tel")
    assert relevant(
        "Advanced Technology Program Advisory Committee — a presentation on "
        "the In-Q-Tel, a venture capital organization",
        iqt,
    )
    assert relevant("A presentation on the In - Q - Tel venture model", iqt)


# ---------------------------------------------------------------- shouted names


def test_a_shouted_registry_name_is_calmed_down():
    """USAspending returns recipients in block capitals. Left alone, the name
    tagger reads them as people and blocks a legitimate brief."""
    from prebrief.sources.base import titlecase_org

    assert titlecase_org("SPIRE GLOBAL SUBSIDIARY CORP") == "Spire Global Subsidiary Corp"
    assert titlecase_org("NORTHBRIDGE DATA SYSTEMS LLC") == "Northbridge Data Systems LLC"
    assert titlecase_org("Already Fine Inc") == "Already Fine Inc"


def test_a_corporate_span_is_never_read_as_a_person():
    """The exact string that blocked the Spire brief on a live run."""
    gate = _gate_or_skip()
    gate.assert_clean(
        "The agency awarded Spire Global Subsidiary Corp $1,200,000 in June."
    )
    gate.assert_clean("SPIRE GLOBAL SUBSIDIARY was named as recipient.")


def test_hardening_the_gate_did_not_blind_it():
    gate = _gate_or_skip()
    with pytest.raises(PersonNameFound):
        gate.assert_clean("The award was signed by Katherine Whitfield last week.")
