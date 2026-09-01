# prebrief

![tests](https://github.com/antoinemlt10/prebrief/actions/workflows/test.yml/badge.svg)

One-page briefs on organizations you are about to meet, built only from public
sources, with every sentence traceable to a URL.

```
prebrief run "National Oceanic and Atmospheric Administration" --as-of 2026-08-31
```

---

## Why this one first

A chief-of-staff function splits on one question, and it is not chief of staff
versus EA. It is whether "done" is checkable by someone other than the CEO.

Where the output is an artifact you can check against a written rule — meeting
prep, commitments extracted after a meeting, chasing decks owned by people who
do not report to you — a system can own it end to end today. Where the output
carries the CEO's authority, or is a judgment with no ground truth, or rests on
a relationship, it needs a person: responsibility has to be assignable, and a
tool cannot be held to a commitment. In between sits a large third category that
is automatable but blocked — not by the model, but by one of three concrete
things: write access, a source of truth, or a feedback loop.

So the rule I would use: **automate a task when it recurs at least weekly, when
"done" is checkable by someone other than you, and when a wrong output is caught
before it leaves the building.** If the third fails, a human keeps the hand no
matter how often it recurs. That last criterion is why calendar and travel are
not the first thing to automate even though they look the most rule-like — a
wrong calendar action is in an investor's inbox in three seconds. A human covers
them from day one; this is about what a machine takes over, not what gets done.

Meeting pre-briefs pass all three criteria, which is why this is the piece that
exists rather than a slide about the piece. A bad brief dies in the room.

---

## What it guarantees

**Nothing is asserted without a source.** Every factual sentence is a `Claim`
carrying the verbatim snippet that supports it, its URL, its date, and a
provenance tier — `filed` for a statutory record, `reported` for press,
`self-reported` for the organization's own words. The renderer refuses to emit a
sentence with no claim behind it, and `assert_sourced` re-parses the finished
markdown to prove it. A language model in this pipeline can order and select
claims; it cannot introduce a fact.

**Briefs are about organizations, never people.** A person's name in the output
fails the build. Not a warning, not a redaction — the brief is not written.
Eponymous organizations are allowlisted; everything else stops the run. Meetings
with government and investor counterparties are exactly where a people-dossier
habit would be both a privacy problem and a bad signal.

**Runs are reproducible.** Fetches are content-addressed and cached, documents
are filtered by an explicit `--as-of` date, and iteration is sorted throughout.
Same name, same date, warm cache: byte-identical output, checked in CI.

**It stays in its lane.** Any claim touching atmospheric data or forecast quality
is dropped before rendering. This tool prepares the business side of a meeting.
The science belongs to people qualified to hold a view on it.

**It says what it could not find.** Every brief ends with the gaps: what was
looked for, in which sources, and came back empty. The questions to ask are
derived from those gaps — a question is well-formed exactly when the public
record cannot answer it.

---

## What a brief looks like

```markdown
# Example Procurement Program

As of 2026-08-31 · government · 3 sourced statements

## Who they are
- Example Department published a notice titled "Notice of Intent To Procure
  Commercial Data" on 2026-02-04. [^a81f954b802c]

## Why they matter
> The one inference in this brief. Everything else is sourced.

- Example Procurement Program appears on the buying side: it holds a mandate
  and a budget for what we sell.
Resting on: [^e97f38e2824f]

## What moved
- Example Procurement Program awarded Northbridge Data Systems $3,671,880,
  with a period beginning 2026-07-18. [^e97f38e2824f]

## Questions to ask
1. Which office signs off, and who else has to agree before it does?

## What I could not find
- decision route — no source in this run covers it

[^a81f954b802c]: [Federal Register — Notice of Intent…](https://example.gov/…) · filed · 2026-02-04
[^e97f38e2824f]: [USAspending award — EPP-2026-0006](https://www.usaspending.gov/…) · filed · 2026-07-18
```

Every run writes three files: `brief.md` for the reader, `brief.json` for
whatever automation comes next, and `sources.csv`.

---

## Sources

Four, no key required: **Wikidata** (entity resolution), **Federal Register**
(what an agency has formally published), **USAspending** (what was actually
bought, from whom, for how much), and **GDELT** (dated news index).

The cache for the example briefs is committed, so they reproduce byte-for-byte
with no network access at all.

---

## Install and run

```bash
make setup      # virtualenv, dependencies, the NER model the privacy gate needs
make test       # the guarantees above, as tests
make briefs     # regenerate the example briefs from live public sources
```

Under the hood that is a normal console script:

```bash
prebrief run "National Oceanic and Atmospheric Administration" --as-of 2026-08-31
prebrief verify briefs/national-oceanic-and-atmospheric-administration/2026-08-31
prebrief doctor "National Oceanic and Atmospheric Administration" --as-of 2026-08-31
```

`doctor` prints what every source returned, term by term — an empty brief has
several possible causes and this says which one it was.

Python 3.10 or newer. The virtualenv matters on macOS, where the system
interpreter is not writable.

`verify` re-fetches every cited source and checks the quoted snippet is still
there. Link rot and silent edits both show up as failures — that is the feedback
loop, and it is the part most tools skip.

---

## What this does not do

It touches nothing behind a login, so it is useless for the internal half of a
chief-of-staff job. It knows nothing that is not publicly written, so an agency
whose real decision happens in an unpublished meeting stays opaque — and the
brief says so rather than filling in. It is organization-level by design, which
caps how useful it is for relationship prep. That is a trade, not an oversight.
