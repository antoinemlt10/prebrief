"""The privacy gate.

These briefs are about organizations: mandates, money, timelines. They are never
about the people you are meeting. That rule is worth nothing as a convention and
everything as a build failure, so it is a build failure.

The gate runs over the *rendered* brief, not over intermediate data, because
that is the only text that actually reaches a reader. A detected person name
raises; it does not warn. A brief that fails this check is not written to disk.

Organization names that contain a personal name — Khosla Ventures, Booz Allen
Hamilton — are the obvious false positive. They are allowed when the personal
name falls inside a span that is recognisably an organization: either one the
run already knows about, or one the tagger itself labelled ORG.
"""

from __future__ import annotations

import functools
import re

__all__ = ["PersonNameFound", "PrivacyGate", "MissingNERModel"]

_MODEL = "en_core_web_sm"

# Organization names whose personal-name component would otherwise trip the
# gate. Extend this rather than loosening the check.
_KNOWN_EPONYMS = frozenset(
    {
        "khosla ventures",
        "booz allen hamilton",
        "lloyd's",
        "lloyds",
        "goldman sachs",
        "morgan stanley",
        "lockheed martin",
        "raytheon",
        "l3harris",
        "bloomberg",
        "moody's",
        "mcKinsey".casefold(),
        "andreessen horowitz",
        "kleiner perkins",
        "bessemer",
        "draper",
        "founders fund",
    }
)


# Tokens that make a span a legal entity rather than a person, whatever a
# statistical tagger concludes from its capitalisation.
_CORPORATE_TOKENS = frozenset(
    {
        "corp", "corporation", "inc", "llc", "llp", "lp", "plc", "ltd", "co",
        "company", "holdings", "group", "subsidiary", "systems", "technologies",
        "technology", "solutions", "services", "global", "international",
        "industries", "enterprises", "partners", "associates", "labs",
        "laboratories", "institute", "university", "foundation", "trust",
        "fund", "capital", "ventures", "administration", "agency", "bureau",
        "department", "office", "council", "commission", "authority",
    }
)


class MissingNERModel(Exception):
    """The gate cannot run, so nothing may be published."""


class PersonNameFound(Exception):
    """A person's name reached the rendered output. The build stops here."""

    def __init__(self, names: list[str], where: str) -> None:
        self.names = names
        listed = ", ".join(sorted(set(names)))
        super().__init__(
            f"privacy gate: person name(s) in {where}: {listed}. "
            "Briefs describe organizations, mandates and money — never the "
            "people in the room. Fix the extractor or add the organization to "
            "the eponym allowlist; do not disable the gate."
        )


@functools.lru_cache(maxsize=1)
def _nlp():
    try:
        import spacy
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise MissingNERModel(
            "spaCy is required for the privacy gate. `pip install spacy` and "
            f"`python -m spacy download {_MODEL}`. The gate is not optional: "
            "without it nothing can be published."
        ) from exc
    try:
        return spacy.load(_MODEL, disable=["lemmatizer", "textcat"])
    except OSError as exc:  # pragma: no cover - environment dependent
        raise MissingNERModel(
            f"spaCy model {_MODEL} is not installed. Run "
            f"`python -m spacy download {_MODEL}`."
        ) from exc


class PrivacyGate:
    def __init__(self, allow: list[str] | None = None) -> None:
        """`allow` should carry the entity's own name and aliases — the strings
        this particular run already knows to be organizations."""
        self.allow = {a.casefold() for a in (allow or []) if a} | set(_KNOWN_EPONYMS)

    def find(self, text: str) -> list[str]:
        """Return every person name in `text` that is not explainable as part of
        an organization name."""
        doc = _nlp()(text)

        org_spans = {
            ent.text.casefold() for ent in doc.ents if ent.label_ in ("ORG", "NORP")
        }
        permitted = self.allow | org_spans

        offenders = []
        for ent in doc.ents:
            if ent.label_ != "PERSON":
                continue
            name = ent.text.strip()
            if self._explained(name, permitted):
                continue
            offenders.append(name)
        return offenders

    def assert_clean(self, text: str, where: str = "rendered brief") -> None:
        if names := self.find(text):
            raise PersonNameFound(names, where)

    @staticmethod
    def _explained(name: str, permitted: set[str]) -> bool:
        """A person span is fine if it is explainable as an organization:
        either it sits inside one the run knows about — 'Khosla' inside 'Khosla
        Ventures' — or it carries a legal-entity designator of its own."""
        needle = name.casefold()
        if needle in permitted:
            return True
        if any(word.strip(".,") in _CORPORATE_TOKENS for word in needle.split()):
            return True
        return any(needle in org for org in permitted if len(org) > len(needle))


def redact(text: str, names: list[str]) -> str:
    """Escape hatch for diagnostics only. The pipeline never publishes redacted
    text — it fails instead, because a brief that needed redaction was built
    from the wrong extraction."""
    for name in sorted(set(names), key=len, reverse=True):
        text = re.sub(rf"\b{re.escape(name)}\b", "[person]", text)
    return text
