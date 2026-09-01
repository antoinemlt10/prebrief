"""Wikidata — what the organization is.

Entity resolution already queries Wikidata; this source turns what it learned
into claims, so the one fact every brief should open with — what this
organization actually is — carries a URL like everything else instead of
living only in resolution metadata. Without it, "Who they are" can only ever
hold procurement leftovers.

Tier is `self-reported`: a crowd-curated description is closer to what an
organization says about itself than to a statutory record, and the claim text
names Wikidata so the reader can discount accordingly.
"""

from __future__ import annotations

from ..claims import Claim, Tier
from ..entities import WIKIDATA_ENTITY, Entity
from .base import RunContext, SourceResult, stamped, unreachable

PAGE = "https://www.wikidata.org/wiki/{qid}"


class WikidataSource:
    name = "wikidata"
    # Covers no gap topic: a one-line description is not a mandate, and this
    # source must not silence the questions the gaps generate.
    covers: tuple[str, ...] = ()
    env_key = None

    def collect(self, entity: Entity, ctx: RunContext) -> SourceResult:
        if not entity.qid:
            return SourceResult(
                self.name,
                note=f"Wikidata holds no record of {entity.name}; "
                f"what it is stays unstated in this brief.",
            )
        try:
            response = ctx.cache.fetch(
                WIKIDATA_ENTITY.format(qid=entity.qid), refresh=ctx.refresh
            )
        except Exception as exc:
            return SourceResult(self.name, note=unreachable("Wikidata", exc))

        url = PAGE.format(qid=entity.qid)
        title = f"Wikidata — {entity.name} ({entity.qid})"
        claims = []
        if entity.description:
            # The description is quoted: it is Wikidata's wording, not ours.
            claims.append(
                Claim(
                    text=f'Wikidata describes {entity.name} as "{entity.description}".',
                    snippet=entity.description,
                    source_url=url,
                    source_title=title,
                    tier=Tier.SELF,
                )
            )
        if entity.homepage:
            claims.append(
                Claim(
                    text=f"{entity.name} lists {entity.homepage} as its official website.",
                    snippet=entity.homepage,
                    source_url=url,
                    source_title=title,
                    tier=Tier.SELF,
                )
            )
        if not claims:
            return SourceResult(
                self.name,
                note=f"Wikidata's record for {entity.name} carries no description.",
            )
        return SourceResult(
            self.name, claims=stamped(claims, response), matched=entity.name
        )
