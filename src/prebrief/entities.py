"""Entity resolution — turning a name someone typed into something addressable.

The honest failure mode matters more than the happy path. "NOAA NESDIS
Commercial Data Program" resolves to a federal program with a budget line and an
award history; a private fund may resolve to almost nothing. When resolution is
thin, that fact travels with the entity and lands in the brief's "what I could
not find" section, instead of being papered over.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from enum import Enum

from .cache import Cache

__all__ = ["Kind", "Entity", "resolve", "slugify"]

WIKIDATA_SEARCH = (
    "https://www.wikidata.org/w/api.php?action=wbsearchentities"
    "&search={q}&language=en&format=json&limit=5&type=item"
)
WIKIDATA_ENTITY = "https://www.wikidata.org/wiki/Special:EntityData/{qid}.json"


class Kind(str, Enum):
    """What kind of counterparty this is. Drives which sources are worth
    querying and which questions are worth asking."""

    GOVERNMENT = "government"  # agency, program office, procurement vehicle
    PUBLIC_COMPANY = "public company"
    PRIVATE_COMPANY = "private company"
    INVESTOR = "investor"  # fund, family office
    NONPROFIT = "nonprofit"
    UNKNOWN = "unknown"


# Wikidata "instance of" QIDs → our coarse kinds. Deliberately small: a wrong
# confident answer is worse than UNKNOWN, which at least prompts the reader.
_INSTANCE_OF = {
    "Q327333": Kind.GOVERNMENT,  # government agency
    "Q20857065": Kind.GOVERNMENT,  # United States federal agency (NOAA's P31)
    "Q2659904": Kind.GOVERNMENT,  # government organization
    "Q1530022": Kind.GOVERNMENT,  # regulatory agency
    "Q891723": Kind.PUBLIC_COMPANY,  # public company
    "Q4830453": Kind.PRIVATE_COMPANY,  # business
    "Q783794": Kind.PRIVATE_COMPANY,  # company
    "Q5341295": Kind.INVESTOR,  # venture capital firm
    "Q163740": Kind.NONPROFIT,  # nonprofit organization
    "P1454": Kind.UNKNOWN,
}

# When an entity carries several matching "instance of" values — Wikidata lists
# Spire Global as both "business" and "public company" — the specific kind
# beats the generic one, whatever order the statements arrive in.
_KIND_PRECEDENCE = (
    Kind.GOVERNMENT,
    Kind.PUBLIC_COMPANY,
    Kind.INVESTOR,
    Kind.NONPROFIT,
    Kind.PRIVATE_COMPANY,
)


@dataclass(slots=True)
class Entity:
    """A counterparty, at organization level. Never a person — see privacy.py."""

    name: str
    slug: str
    kind: Kind = Kind.UNKNOWN
    qid: str | None = None
    cik: str | None = None  # SEC filer number, if any
    homepage: str | None = None
    aliases: list[str] = field(default_factory=list)
    description: str | None = None
    resolution_notes: list[str] = field(default_factory=list)

    @property
    def thin(self) -> bool:
        """True when we could not pin the entity down. A thin entity still gets
        a brief — a short and mostly negative one, which is the correct output,
        not a failure."""
        return self.qid is None and self.cik is None

    def initialism(self) -> str | None:
        """The initialism a document would actually use, derived from the name.

        First letters of the significant words — stopwords skipped, so
        "National Oceanic and Atmospheric Administration" gives NOAA, not
        NOAAA. Three letters minimum: "Spire Global" must not become "SG"
        and start matching everything.
        """
        stop = {"and", "of", "the", "for", "in", "on", "at", "to", "a", "an"}
        words = [w for w in re.split(r"[\s\-]+", self.name) if w]
        letters = "".join(
            w[0].upper() for w in words if w.casefold() not in stop and w[0].isalpha()
        )
        return letters if len(letters) >= 3 else None

    def name_bigrams(self) -> list[str]:
        """Adjacent word pairs from the name, lowercased.

        These are the relevance test for a widened match: a document found by
        searching "NOAA" is only about the Commercial Data Program if it says
        something like "commercial data" somewhere. One shared word is not
        enough — "commercial" alone matches half the fisheries register.
        """
        words = [w.casefold().strip(",.;:()") for w in self.name.split()]
        words = [w for w in words if w]
        return [f"{a} {b}" for a, b in zip(words, words[1:])]

    def query_terms(self) -> list[str]:
        """Query strings to try, widest match last.

        Searching a public corpus for the exact string someone typed is the
        single biggest cause of an empty brief. "NOAA NESDIS Commercial Data
        Program" appears in no headline and no Wikidata label; "Commercial Data
        Program" and "NOAA" both do. So an entity carries a ladder of terms and
        sources climb it until something answers — recording which rung worked,
        because a match on a broader term is weaker evidence and the brief
        should say so.
        """
        return _term_ladder(self.name, self.aliases)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "slug": self.slug,
            "kind": self.kind.value,
            "qid": self.qid,
            "cik": self.cik,
            "homepage": self.homepage,
            "aliases": self.aliases,
            "description": self.description,
            "thin": self.thin,
            "resolution_notes": self.resolution_notes,
        }


# Words that carry no search signal at the end of an organization's name.
_GENERIC_TAIL = frozenset(
    {
        "program",
        "programme",
        "office",
        "solutions",
        "systems",
        "services",
        "ventures",
        "partners",
        "capital",
        "group",
        "holdings",
        "international",
        "global",
        "inc",
        "inc.",
        "llc",
        "ltd",
        "corp",
        "corp.",
        "corporation",
        "company",
        "co",
        "co.",
    }
)


def _term_ladder(name: str, aliases: list[str] | None = None) -> list[str]:
    """Widest match last. Order is deterministic, and duplicates are dropped."""
    terms: list[str] = [name, *(aliases or [])]
    words = name.split()

    # Progressively drop trailing filler: "Galvanize Climate Solutions" →
    # "Galvanize Climate". Never strip down to a single generic word.
    trimmed = list(words)
    while len(trimmed) > 2 and trimmed[-1].casefold().strip(",.") in _GENERIC_TAIL:
        trimmed = trimmed[:-1]
        terms.append(" ".join(trimmed))

    # Acronyms usually are the searchable handle for a government entity.
    acronyms = [w for w in words if w.isupper() and 2 <= len(w) <= 6]
    if acronyms:
        if len(acronyms) > 1:
            terms.append(" ".join(acronyms))
        # The descriptive tail on its own — "Commercial Data Program" — is what
        # a Federal Register title actually says.
        tail = [w for w in words if w not in acronyms]
        if len(tail) >= 2:
            terms.insert(1, " ".join(tail))
        # A bare acronym is only safe for a short name. Falling back from
        # "NOAA NESDIS Commercial Data Program" to "NOAA" returns everything
        # the agency does — fisheries rules, marine mammal notices — and an
        # off-topic brief is worse than an empty one.
        if len(words) <= 2:
            terms.append(acronyms[0])

    seen, ladder = set(), []
    for term in terms:
        key = term.casefold().strip()
        if key and key not in seen:
            seen.add(key)
            ladder.append(term.strip())
    return ladder


def slugify(name: str) -> str:
    ascii_name = (
        unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    )
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_name.casefold()).strip("-")
    return slug or "unnamed"


def resolve(name: str, cache: Cache) -> Entity:
    """Best-effort resolution against Wikidata. Never raises on a miss — an
    unresolved entity is a legitimate result that the brief will report."""
    entity = Entity(name=name.strip(), slug=slugify(name))
    ladder = _term_ladder(entity.name)

    hits, matched = [], None
    for term in ladder:
        try:
            response = cache.fetch(WIKIDATA_SEARCH.format(q=_quote(term)))
        except Exception as exc:  # fails soft: an unresolved entity is a result
            entity.resolution_notes.append(
                f"Wikidata could not be queried ({type(exc).__name__}); entity type "
                f"and aliases are unresolved."
            )
            return entity
        if not response.ok:
            continue
        try:
            hits = response.json().get("search", [])
        except ValueError:
            continue
        if hits:
            matched = term
            break

    if not hits:
        entity.resolution_notes.append(
            f"No Wikidata match for any of: {', '.join(ladder)}. Treated as a thin "
            f"entity — the brief leans on filings and awards, and says what it "
            f"could not establish."
        )
        return entity

    if matched and matched.casefold() != entity.name.casefold():
        # Transparency: a broader term matched, so the record below may describe
        # a parent organization rather than the exact one asked for.
        entity.resolution_notes.append(
            f'Resolved on the broader term "{matched}", not the full name. '
            f"Confirm the record below describes the right body."
        )

    top = hits[0]
    entity.qid = top.get("id")
    entity.description = top.get("description")
    entity.aliases = [a for a in top.get("aliases", []) if a]

    _enrich_from_wikidata(entity, cache)
    return entity


def _enrich_from_wikidata(entity: Entity, cache: Cache) -> None:
    if not entity.qid:
        return
    try:
        response = cache.fetch(WIKIDATA_ENTITY.format(qid=entity.qid))
        if not response.ok:
            return
        claims = response.json()["entities"][entity.qid].get("claims", {})
    except Exception as exc:
        entity.resolution_notes.append(
            f"Wikidata entity record could not be read ({type(exc).__name__})."
        )
        return

    kinds = {
        _INSTANCE_OF[qid]
        for statement in claims.get("P31", [])  # instance of
        if (qid := _value(statement, "id")) in _INSTANCE_OF
    }
    for kind in _KIND_PRECEDENCE:
        if kind in kinds:
            entity.kind = kind
            break

    entity.homepage = entity.homepage or _first_string(claims.get("P856", []))  # website


def _value(statement: dict, key: str):
    return statement.get("mainsnak", {}).get("datavalue", {}).get("value", {}).get(key)


def _first_string(statements: list[dict]) -> str | None:
    for statement in statements:
        value = statement.get("mainsnak", {}).get("datavalue", {}).get("value")
        if isinstance(value, str):
            return value
    return None


def _quote(s: str) -> str:
    from urllib.parse import quote

    return quote(s)
