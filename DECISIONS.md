# Decisions

The code shows where this ended up. This file shows why, for the choices that
were not obvious at the time. Each one was forced by something the tool actually
did on a live run.

## An off-topic brief is worse than an empty one

The first run against real APIs returned two empty briefs out of three: every
source was being queried with the exact organization name, which appears in no
headline and few filings. Widening the query fixed the emptiness and produced
something worse — searching "NOAA" on behalf of a data-purchase programme filled
the brief with Pacific cod reallocations and marine mammal notices.

Both are failures, but they fail differently. An empty brief that says where it
looked costs the reader ten seconds. A brief full of plausible, irrelevant
records costs them the meeting. So the term ladder now stops before a bare
acronym, and a widened match must share an adjacent word-pair with the full name
(`sources/base.py::relevant`). The briefs got shorter. That was the point.

## Clean the input rather than loosen the gate

The privacy gate blocked a legitimate brief from being written. The offending
string was `SPIRE GLOBAL SUBSIDIARY` — USAspending returns recipients in block
capitals, and a statistical name tagger reads block capitals as a person.

The tempting fix is to relax the gate. The correct one is upstream: registry
names are normalised to prose case before they ever become a claim
(`titlecase_org`), which both reads better and stops the misfire. A second rule
allows spans carrying a legal-entity designator. And there is a test asserting
the gate still bites on a real personal name — hardening a filter without
checking that it has not gone blind is how filters get quietly disabled.

## A note may carry an exception's type, never its message

On the very first live run, a source that could not reach its API interpolated
the exception into the brief's notes. The traceback carried hostnames and
capitalised fragments; the tagger read "Max" and "Forbidden" as people, and the
build failed.

Nothing reached disk, which is the gate doing its job on a defect nobody had
anticipated. But the underlying fault was ours: a reader should never see a
stack trace, and a note should be a sentence a person would write. Notes now
carry the exception's class name and nothing else (`sources/base.py::unreachable`).

## A brief is prepared for someone

Relevance to the entity is not relevance to the reader. Every coral-reef notice
in NOAA's Federal Register output genuinely concerns NOAA. None of it concerns
anyone evaluating a commercial data relationship, and no gate keyed on the
entity could tell the difference.

`reader.yaml` names the market the brief is written from. It filters *what
moved* and nothing else — identity stays entity-level — and when it empties the
section, the brief says so and lists the terms it applied. It is deliberately
disjoint from the scope gate in `scope.py`: one file says what business we are
in, the other says what we have no standing to hold a view on. Each points at
the other in a comment, so they do not drift into overlap.

## Ask the corpus a question it can answer

"NOAA NESDIS Commercial Data Program" was the first example organization, and it
returned nothing. Correctly: the Federal Register indexes by agency and
USAspending by agency and recipient. Neither indexes programme offices.

The tool was not wrong; the question was. The examples now name the agency,
which is also the right granularity for a meeting — you meet an organization,
not one of its programmes. Two rounds were spent hardening the retrieval before
noticing the input was the problem.

## No fabricated sources, including for the demo

Part of this was built on a machine with no route to the public APIs. It would
have been easy to hand-write cache entries so the three example briefs looked
full, and no reader could have told.

They are not written. The test fixtures are explicitly synthetic and use
`example.gov`; the committed cache comes from real runs on a machine with
network access. A tool whose entire argument is provenance cannot ship invented
records as findings — least of all in its own shop window.

## What this cost, and what it bought

Six rounds against live data. The briefs went from empty, to off-topic, to
padded, to thirteen claims across three organizations. One of those briefs has
no recent activity at all and says why. Another has two claims and seven gaps.

Neither is a shortfall. The tool's only real asset is that a reader can trust
what it does say, and the fastest way to spend that asset is to fill a page.
