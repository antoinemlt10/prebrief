"""Command line.

    prebrief run "NOAA NESDIS Commercial Data Program" --as-of 2026-08-31
    prebrief run --batch orgs.txt --as-of 2026-08-31
    prebrief verify briefs/noaa-nesdis-commercial-data-program/2026-08-31

`run` is idempotent: same name, same --as-of, warm cache, byte-identical output.
`verify` re-fetches every cited source and checks the quoted snippet is still
there — link rot and silent edits both show up as failures.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime
from pathlib import Path

from .brief import Brief
from .cache import Cache
from .pipeline import build, default_sources
from .privacy import MissingNERModel, PersonNameFound, PrivacyGate
from .render import render_json, render_markdown, render_sources_csv
from .sources.base import RunContext

DEFAULT_CACHE = Path("cache")
DEFAULT_OUT = Path("briefs")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="prebrief", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="generate one brief, or a batch")
    run.add_argument("organization", nargs="?", help="name of the organization")
    run.add_argument("--batch", type=Path, help="file with one organization per line")
    run.add_argument(
        "--as-of",
        type=_day,
        default=date.today(),
        help="only consider documents published on or before this date",
    )
    # 365, not 180: federal procurement moves on annual cycles — option years
    # and fiscal-year funding — so a shorter window can miss the current cycle.
    run.add_argument("--window-days", type=int, default=365)
    run.add_argument("--out", type=Path, default=DEFAULT_OUT)
    run.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    run.add_argument(
        "--offline", action="store_true", help="fail on a cache miss instead of fetching"
    )
    run.add_argument("--refresh", action="store_true", help="bypass the cache")

    verify = sub.add_parser("verify", help="re-check every source behind a brief")
    verify.add_argument("brief_dir", type=Path)
    verify.add_argument("--cache", type=Path, default=DEFAULT_CACHE)

    doctor = sub.add_parser(
        "doctor", help="show what each source actually returned, term by term"
    )
    doctor.add_argument("organization")
    doctor.add_argument("--as-of", type=_day, default=date.today())
    doctor.add_argument("--window-days", type=int, default=365)
    doctor.add_argument("--cache", type=Path, default=DEFAULT_CACHE)

    args = parser.parse_args(argv)
    if args.command == "run":
        return _run(args)
    if args.command == "doctor":
        return _doctor(args)
    return _verify(args)


def _doctor(args) -> int:
    """An empty brief has many possible causes — a name that resolves to
    nothing, a query the API rejects, a corpus that genuinely has no record.
    Guessing between them from the outside wastes a round trip each time, so
    this prints what every source saw."""
    from .entities import resolve
    from .sources.usaspending import API as US_API, USASpendingSource

    cache = Cache(args.cache)
    ctx = RunContext(cache=cache, as_of=args.as_of, window_days=args.window_days)
    entity = resolve(args.organization, cache)
    ladder = entity.query_terms()

    print(f"\n{entity.name}")
    print(f"  resolved  {entity.kind.value}"
          f"{' · ' + entity.qid if entity.qid else ''}"
          f"{'  (thin)' if entity.thin else ''}")
    print(f"  terms     {' → '.join(ladder)}")
    for note in entity.resolution_notes:
        print(f"            {note}")

    for source in default_sources():
        print(f"\n  [{source.name}]")
        for term in ladder:
            try:
                if isinstance(source, USASpendingSource):
                    payload = source.payload_for(
                        term, ctx, agency=entity.kind.value == "government"
                    )
                    response = cache.fetch(US_API, payload=payload)
                else:
                    response = cache.fetch(source.url_for(term, ctx))
            except Exception as exc:
                print(f"    {term!r:52s} unreachable ({type(exc).__name__})")
                break
            print(f"    {term!r:52s} HTTP {response.status}  {_shape(response.body)}")

        result = source.collect(entity, ctx)
        verdict = (
            f"✓ {len(result.claims)} claims on {result.matched!r}"
            if result.claims
            else f"✗ {result.note}"
        )
        print(f"    → {verdict}")
    print()
    return 0


def _shape(body: str) -> str:
    import json as _json

    if not body.strip():
        return "empty body"
    try:
        parsed = _json.loads(body)
    except ValueError:
        return f"non-JSON ({len(body)}b): {body[:60]!r}"
    for key in ("results", "articles", "search"):
        if key in parsed:
            return f"{key}={len(parsed[key])}"
    return f"json keys: {', '.join(sorted(parsed)[:4])}"


def _run(args) -> int:
    names = _names(args)
    if not names:
        print("nothing to do: pass an organization name or --batch", file=sys.stderr)
        return 2

    cache = Cache(args.cache, offline=args.offline)
    ctx = RunContext(
        cache=cache,
        as_of=args.as_of,
        window_days=args.window_days,
        refresh=args.refresh,
    )

    failures = 0
    for name in names:
        try:
            brief, results = build(name, ctx, default_sources())
            path = _write(brief, args.out)
        except PersonNameFound as exc:
            print(f"✗ {name}\n  {exc}", file=sys.stderr)
            failures += 1
            continue
        except MissingNERModel as exc:
            print(f"✗ {name}\n  {exc}", file=sys.stderr)
            return 3
        except Exception as exc:
            print(f"✗ {name}\n  {type(exc).__name__}: {exc}", file=sys.stderr)
            failures += 1
            continue

        quiet = [r.source for r in results if not r.ok]
        summary = f"{len(brief.used_claim_ids)} claims, {len(brief.gaps)} gaps"
        if quiet:
            summary += f", silent: {', '.join(sorted(quiet))}"
        print(f"✓ {path}  ({summary})")

    return 1 if failures else 0


def _write(brief: Brief, root: Path) -> Path:
    markdown = render_markdown(brief)

    # The gate runs on the text a reader would actually see, and nothing is
    # written to disk until it passes.
    PrivacyGate(allow=[brief.entity.name, *brief.entity.aliases]).assert_clean(
        markdown, where=f"{brief.entity.slug} brief"
    )

    directory = root / brief.entity.slug / brief.as_of.isoformat()
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "brief.md").write_text(markdown, encoding="utf-8")
    (directory / "brief.json").write_text(render_json(brief), encoding="utf-8")
    (directory / "sources.csv").write_text(render_sources_csv(brief), encoding="utf-8")
    return directory / "brief.md"


def _verify(args) -> int:
    import json

    payload = json.loads((args.brief_dir / "brief.json").read_text(encoding="utf-8"))
    cache = Cache(args.cache)

    stale = 0
    for record in payload["claims"]:
        try:
            response = cache.fetch(record["source_url"], refresh=True)
        except Exception as exc:
            print(f"✗ {record['id']}  unreachable: {exc}")
            stale += 1
            continue
        if not response.ok:
            print(f"✗ {record['id']}  HTTP {response.status}  {record['source_url']}")
            stale += 1
            continue
        if _normalize(record["snippet"]) not in _normalize(response.body):
            print(f"✗ {record['id']}  snippet no longer present  {record['source_url']}")
            stale += 1
            continue
        print(f"✓ {record['id']}  {record['source_url']}")

    total = len(payload["claims"])
    print(f"\n{total - stale}/{total} sources still support their claim")
    return 1 if stale else 0


def _normalize(s: str) -> str:
    import re

    return re.sub(r"\s+", " ", s).strip().casefold()


def _names(args) -> list[str]:
    if args.batch:
        lines = args.batch.read_text(encoding="utf-8").splitlines()
        return [ln.strip() for ln in lines if ln.strip() and not ln.startswith("#")]
    return [args.organization] if args.organization else []


def _day(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


if __name__ == "__main__":
    raise SystemExit(main())
