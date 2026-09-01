"""USAspending — the money.

For a government counterparty this answers "what has this office actually
bought, from whom, for how much, and when". For a company it answers "what has
this vendor actually won". Both are the same question asked from opposite ends,
so the adapter queries by awarding agency for agencies and by recipient for
companies.

Free, no key, and it is a statutory record, so everything here is tier `filed`.
"""

from __future__ import annotations

from datetime import date, datetime

from ..claims import Claim, Tier
from ..entities import Entity, Kind
from .base import RunContext, SourceResult, clean, stamped, titlecase_org, unreachable

API = "https://api.usaspending.gov/api/v2/search/spending_by_award/"
AWARD_URL = "https://www.usaspending.gov/award/{id}"
MAX_AWARDS = 5

# Procurement contracts only. USAspending rejects a request that mixes contract
# codes with grant codes in one query — that rejection is what silenced this
# source on the first live run. Contracts are also the right scope: a grant is a
# different kind of relationship and would muddy the read.
AWARD_TYPES = ["A", "B", "C", "D"]


class USASpendingSource:
    name = "usaspending"
    covers = ("budget", "procurement route", "recent activity")
    env_key = None

    def collect(self, entity: Entity, ctx: RunContext) -> SourceResult:
        ladder = entity.query_terms()
        # When Wikidata could not say what this is, we do not get to guess. Ask
        # both sides of the ledger — an unresolved entity searched only as a
        # recipient is how a federal program came back with nothing.
        scopes = (
            (True, False) if entity.kind is Kind.UNKNOWN else (self._is_agency(entity),)
        )
        for term in ladder:
          for agency_scope in scopes:
              payload = self.payload_for(term, ctx, agency=agency_scope)
              try:
                  response = ctx.cache.fetch(API, payload=payload, refresh=ctx.refresh)
              except Exception as exc:
                  return SourceResult(self.name, note=unreachable("USAspending", exc))

              if not response.ok:
                  # A 4xx here means the query shape is wrong, not that the world
                  # is empty. Say which, so it is debuggable from the brief.
                  return SourceResult(
                      self.name,
                      note=(
                          f"USAspending rejected the query with HTTP "
                          f"{response.status}; award history is missing from this "
                          f"brief."
                      ),
                  )
              try:
                  rows = response.json().get("results") or []
              except ValueError:
                  return SourceResult(self.name, note="USAspending returned malformed JSON.")

              claims = [c for row in rows[:MAX_AWARDS] if (c := self._to_claim(row))]
              if claims:
                  return SourceResult(
                      self.name, claims=stamped(claims, response), matched=term
                  )

        side = "awarding agency or recipient"
        return SourceResult(
            self.name,
            note=(
                f"No federal contract in the {ctx.window_days} days to "
                f"{ctx.as_of.isoformat()} lists any of these as {side}: "
                f"{', '.join(ladder)}."
            ),
        )

    def payload_for(self, term: str, ctx: RunContext, *, agency: bool) -> dict:
        window = {
            "start_date": ctx.window_start.isoformat(),
            "end_date": ctx.as_of.isoformat(),
        }
        # `keywords` searches agency names and award descriptions, which is what
        # actually works for a program office. An exact subtier-agency name match
        # only works if the caller already knows the agency's registered name —
        # and if they knew that, they would not need the brief.
        scope = {"keywords": [term]} if agency else {"recipient_search_text": [term]}
        return {
            "filters": {
                "time_period": [window],
                "award_type_codes": AWARD_TYPES,
                **scope,
            },
            "fields": [
                "Award ID",
                "Recipient Name",
                "Awarding Agency",
                "Awarding Sub Agency",
                "Award Amount",
                "Start Date",
                "Description",
                "generated_internal_id",
            ],
            "page": 1,
            "limit": 10,
            "sort": "Award Amount",
            "order": "desc",
        }

    @staticmethod
    def _is_agency(entity: Entity) -> bool:
        return entity.kind is Kind.GOVERNMENT

    def _to_claim(self, row: dict) -> Claim | None:
        amount = row.get("Award Amount")
        recipient = titlecase_org(clean(row.get("Recipient Name") or ""))
        agency = titlecase_org(
            clean(row.get("Awarding Sub Agency") or row.get("Awarding Agency") or "")
        )
        internal_id = row.get("generated_internal_id")
        if amount is None or not recipient or not internal_id:
            return None

        started = _parse_date(row.get("Start Date"))
        description = clean(row.get("Description") or "")

        text = f"{agency or 'A federal agency'} awarded {recipient} ${amount:,.0f}"
        if started:
            text += f", with a period beginning {started.isoformat()}"
        text += "."

        # The snippet is the award record's own description where there is one,
        # otherwise the identifying fields as the API returned them.
        snippet = description or (
            f"{recipient} | {agency} | {amount} | {row.get('Award ID', '')}"
        )
        return Claim(
            text=text,
            snippet=snippet,
            source_url=AWARD_URL.format(id=internal_id),
            source_title=f"USAspending award — {row.get('Award ID', internal_id)}",
            tier=Tier.FILED,
            published=started,
        )


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").date()
    except ValueError:
        return None
