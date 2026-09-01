"""Federal Register — what an agency has formally published.

Free, no key, and the highest-signal source for a government counterparty: a
notice or rule in the Register is the agency committing itself in public, with a
date. When a program office is about to change how it buys something, this is
usually where it shows up first.
"""

from __future__ import annotations

from datetime import date, datetime
from urllib.parse import urlencode

from ..claims import Claim, Tier
from ..entities import Entity
from .base import (
    RunContext,
    SourceResult,
    clean,
    relevant,
    snippet_around,
    stamped,
    unreachable,
)

API = "https://www.federalregister.gov/api/v1/documents.json"
MAX_DOCS = 6


class FederalRegisterSource:
    name = "federal register"
    covers = ("mandate", "timeline", "procurement route", "recent activity")
    env_key = None

    def url_for(self, term: str, ctx: RunContext) -> str:
        query = {
            "per_page": 20,
            "order": "newest",
            "conditions[term]": f'"{term}"',
            "conditions[publication_date][lte]": ctx.as_of.isoformat(),
            "fields[]": [
                "title",
                "publication_date",
                "html_url",
                "abstract",
                "type",
                "agency_names",
            ],
        }
        return f"{API}?{urlencode(query, doseq=True)}"

    def collect(self, entity: Entity, ctx: RunContext) -> SourceResult:
        ladder = entity.query_terms()
        for term in ladder:
            try:
                response = ctx.cache.fetch(self.url_for(term, ctx), refresh=ctx.refresh)
            except Exception as exc:
                return SourceResult(self.name, note=unreachable("Federal Register", exc))
            if not response.ok or not response.body.strip():
                continue
            try:
                documents = response.json().get("results") or []
            except ValueError:
                continue

            # The Register sometimes carries the same notice twice under two
            # document numbers. Two claims with the same title and date read as
            # a copy-paste error, so only the first survives.
            seen: set[tuple[str, str]] = set()
            on_topic = []
            for d in documents:
                # Title plus abstract only — the Register matched the body, and
                # a body mention proves nothing about what the document is about.
                if not relevant(f"{d.get('title', '')} {d.get('abstract') or ''}", entity):
                    continue
                key = (clean(d.get("title", "")), d.get("publication_date") or "")
                if key in seen:
                    continue
                seen.add(key)
                on_topic.append(d)
            claims = [c for d in on_topic[:MAX_DOCS] if (c := self._to_claim(d, term))]
            if claims:
                return SourceResult(
                    self.name, claims=stamped(claims, response), matched=term
                )

        return SourceResult(
            self.name,
            note=(
                f"No Federal Register document is about {entity.name}. "
                f"Searched: {', '.join(ladder)}."
            ),
        )

    def _to_claim(self, document: dict, term: str) -> Claim | None:
        title = clean(document.get("title", ""))
        url = document.get("html_url")
        if not title or not url:
            return None

        published = _parse_date(document.get("publication_date"))
        doc_type = (document.get("type") or "document").lower()
        agencies = document.get("agency_names") or []
        publisher = clean(agencies[0]) if agencies else "A federal agency"

        # Templated from structured fields — never written freehand. The title is
        # quoted because it is the agency's own wording.
        text = f'{publisher} published a {doc_type} titled "{title}"'
        if published:
            text += f" on {published.isoformat()}"
        text += "."

        body = clean(document.get("abstract") or "") or title
        return Claim(
            text=text,
            snippet=snippet_around(body, term) or title,
            source_url=url,
            source_title=f"Federal Register — {title[:70]}",
            tier=Tier.FILED,
            published=published,
        )


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").date()
    except ValueError:
        return None
