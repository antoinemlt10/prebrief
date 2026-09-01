"""Content-addressed fetch cache.

Every network response is stored under the hash of its URL. A warm cache means
a run makes no network calls at all, which is what lets the three example briefs
in this repo reproduce byte-for-byte on a machine with no API keys.

`refresh=True` bypasses the cache for one URL. `offline=True` turns a miss into
an error rather than a request — used in CI so a test can never silently depend
on the network.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import requests

__all__ = ["Cache", "CacheMiss", "Response"]

USER_AGENT = (
    "prebrief/0.1 (public-source meeting brief generator; "
    "contact via repository issues)"
)
_MIN_INTERVAL = 0.34  # be a polite citizen of public APIs


class CacheMiss(Exception):
    """Offline mode, and the URL is not in the cache."""


@dataclass(frozen=True, slots=True)
class Response:
    url: str
    status: int
    body: str
    fetched_at: datetime
    from_cache: bool

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300

    def json(self):
        return json.loads(self.body)


class Cache:
    def __init__(self, root: Path, *, offline: bool = False) -> None:
        self.root = Path(root)
        self.offline = offline
        self._last_request = 0.0

    def path_for(self, url: str, payload: dict | None = None) -> Path:
        # A POST is only cacheable if its body is part of the key. Sorted keys
        # so an equivalent query always lands on the same cache entry.
        key = url
        if payload is not None:
            key += "\x00" + json.dumps(payload, sort_keys=True)
        digest = hashlib.sha256(key.encode()).hexdigest()
        return self.root / digest[:2] / f"{digest}.json"

    def fetch(
        self,
        url: str,
        *,
        payload: dict | None = None,
        headers: dict[str, str] | None = None,
        refresh: bool = False,
        timeout: float = 30.0,
        min_interval: float | None = None,
    ) -> Response:
        """GET, or POST when `payload` is given. Both are cached identically —
        several public APIs (USAspending among them) only answer to POST, and a
        query is a query.

        `min_interval` lets a source ask for slower pacing than the default —
        GDELT refuses bursts outright. A cache hit returns before any throttle,
        so warm runs stay instant."""
        path = self.path_for(url, payload)

        if not refresh and path.exists():
            record = json.loads(path.read_text(encoding="utf-8"))
            return Response(
                url=record["url"],
                status=record["status"],
                body=record["body"],
                fetched_at=datetime.fromisoformat(record["fetched_at"]),
                from_cache=True,
            )

        if self.offline:
            raise CacheMiss(
                f"{url} is not cached and this run is offline. "
                f"Re-run without --offline to fetch it."
            )

        self._throttle(min_interval or _MIN_INTERVAL)
        merged = {"User-Agent": USER_AGENT, "Accept-Encoding": "gzip"}
        merged.update(headers or {})
        # One retry, because a dropped connection is not a finding. Anything
        # beyond that is a real outage and belongs in the brief.
        for attempt in (1, 2):
            try:
                if payload is None:
                    http = requests.get(url, headers=merged, timeout=timeout)
                else:
                    http = requests.post(
                        url, json=payload, headers=merged, timeout=timeout
                    )
                break
            except (requests.Timeout, requests.ConnectionError):
                if attempt == 2:
                    raise
                time.sleep(1.5)

        response = Response(
            url=url,
            status=http.status_code,
            body=http.text,
            fetched_at=datetime.now(timezone.utc),
            from_cache=False,
        )
        # Only successful responses are cached. A 503 today should not become a
        # permanent fact about the world.
        if response.ok:
            self._write(path, response)
        return response

    def put(
        self, url: str, body: str, *, payload: dict | None = None, status: int = 200
    ) -> None:
        """Seed the cache directly. Used by tests, and by anyone who needs to
        pin a run to a response they already have."""
        self._write(
            self.path_for(url, payload),
            Response(
                url=url,
                status=status,
                body=body,
                fetched_at=datetime.now(timezone.utc),
                from_cache=False,
            ),
        )

    def _write(self, path: Path, response: Response) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "url": response.url,
            "status": response.status,
            "fetched_at": response.fetched_at.isoformat(),
            "body_sha256": hashlib.sha256(response.body.encode()).hexdigest(),
            "body": response.body,
        }
        # sort_keys so a cache file is diffable and stable across runs
        path.write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=1),
            encoding="utf-8",
        )

    def _throttle(self, interval: float) -> None:
        elapsed = time.monotonic() - self._last_request
        if elapsed < interval:
            time.sleep(interval - elapsed)
        self._last_request = time.monotonic()
