"""GDELT — what moved, and when.

A free, dated index of world news. It answers exactly one question well: has
anything about this organization been reported recently, and where can I read
it. Everything from here is tier `reported`, and GDELT returns headlines rather
than body text, so the snippet a claim carries is the headline itself. That is a
thinner form of evidence than a filing and the brief says so by printing the
tier.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from urllib.parse import urlencode

from ..claims import Claim, Tier
from ..entities import Entity
from .base import RunContext, SourceResult, clean, relevant, stamped, unreachable

API = "https://api.gdeltproject.org/api/v2/doc/doc"
MAX_ARTICLES = 6

# GDELT refuses bursts: fired 0.34s apart in a batch run, every query came back
# non-2xx while the same query alone succeeded. It wants ~5s between requests.
MIN_INTERVAL = 5.0

# A headline built around one of these verbs is about a person — a hire, a
# promotion, a departure. Briefs describe organizations, mandates and money,
# never the people in the room, and the NER gate cannot be trusted to spot
# every name in an all-titlecase headline. Over-broad is cheap: it drops a
# claim the brief did not need. Under-broad puts a person in the output.
_PERSONNEL = re.compile(
    r"\b(?:names|named|appoints?|appointed|hires?|hired|promotes?|promoted|"
    r"taps|joins|resigns?|resigned|retires?|retired|steps\s+down|"
    r"succeeds?|welcomes)\b",
    re.IGNORECASE,
)

# Aggregators and syndication mills. They restate other people's reporting and
# crowd out the primary account.
_LOW_VALUE_DOMAINS = frozenset(
    {
        "finance.yahoo.com",
        "msn.com",
        "news.google.com",
        "marketscreener.com",
        "stocktitan.net",
        "simplywall.st",
        "insidermonkey.com",
    }
)


class GdeltSource:
    name = "gdelt"
    covers = ("recent activity",)
    env_key = None

    def url_for(self, term: str, ctx: RunContext) -> str:
        query = {
            "query": f'"{term}"',
            "mode": "artlist",
            "maxrecords": 40,
            "format": "json",
            "sort": "datedesc",
            "startdatetime": _stamp(ctx.window_start, end=False),
            "enddatetime": _stamp(ctx.as_of, end=True),
        }
        return f"{API}?{urlencode(query)}"

    def collect(self, entity: Entity, ctx: RunContext) -> SourceResult:
        ladder = entity.query_terms()
        refused: int | None = None
        for term in ladder:
            try:
                response = ctx.cache.fetch(
                    self.url_for(term, ctx),
                    refresh=ctx.refresh,
                    min_interval=MIN_INTERVAL,
                )
            except Exception as exc:
                return SourceResult(self.name, note=unreachable("GDELT", exc))
            if not response.ok:
                refused = response.status
                continue
            # GDELT answers "nothing found" with an empty body and a rate limit
            # with plain text. Only the empty body means the corpus is empty.
            if not response.body.strip():
                continue
            try:
                articles = response.json().get("articles") or []
            except ValueError:
                refused = response.status
                continue

            if claims := self._select(articles, entity, term):
                return SourceResult(
                    self.name, claims=stamped(claims, response), matched=term
                )

        if refused is not None:
            # A refused query is not an empty corpus. Only the status code may
            # appear — never the response body, which the name tagger would read.
            return SourceResult(
                self.name,
                note=(
                    f"GDELT refused this run's queries (HTTP {refused}); "
                    f"its coverage is missing from this brief."
                ),
            )
        # Precisely what was tested: coverage that only mentions the entity in
        # passing may exist, but no headline was about it.
        return SourceResult(
            self.name,
            note=(
                f"No English-language headline names {entity.name} in the "
                f"{ctx.window_days} days to {ctx.as_of.isoformat()}. "
                f"Searched: {', '.join(ladder)}."
            ),
        )

    def _select(self, articles: list[dict], entity: Entity, term: str) -> list[Claim]:
        seen_domains: set[str] = set()
        claims: list[Claim] = []
        for article in articles:
            if len(claims) >= MAX_ARTICLES:
                break
            domain = (article.get("domain") or "").lower()
            if domain in _LOW_VALUE_DOMAINS or domain in seen_domains:
                continue
            if (article.get("language") or "English") != "English":
                continue
            # GDELT matches article bodies, but the headline is all a claim can
            # quote. A headline that never names the entity — a syndicated
            # census piece that mentions NOAA in paragraph nine, a funding
            # roundup that lists the fund once — is not a statement about the
            # entity, whatever the body says. Even on an exact-term hit.
            if not relevant(article.get("title", ""), entity):
                continue
            # Personnel news is never extracted — see _PERSONNEL above.
            if _PERSONNEL.search(article.get("title", "")):
                continue
            if claim := self._to_claim(article, domain):
                seen_domains.add(domain)
                claims.append(claim)
        return claims

    def _to_claim(self, article: dict, domain: str) -> Claim | None:
        title = clean(article.get("title", ""))
        url = article.get("url")
        if not title or not url:
            return None
        published = _parse_stamp(article.get("seendate"))
        text = f'{domain} reported "{title}"'
        if published:
            text += f" on {published.isoformat()}"
        text += "."
        return Claim(
            text=text,
            snippet=title,  # GDELT gives the headline and nothing more
            source_url=url,
            source_title=f"{domain} — {title[:70]}",
            tier=Tier.REPORTED,
            published=published,
        )


def _stamp(day: date, *, end: bool) -> str:
    return day.strftime("%Y%m%d") + ("235959" if end else "000000")


def _parse_stamp(value: str | None) -> date | None:
    if not value:
        return None
    for fmt in ("%Y%m%dT%H%M%SZ", "%Y%m%d%H%M%S", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None
