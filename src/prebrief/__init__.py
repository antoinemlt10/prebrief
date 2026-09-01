"""prebrief — one-page meeting briefs on organizations, from public sources only.

Three properties the rest of the package exists to guarantee:

1. Nothing is asserted without a source. Every factual sentence in a rendered
   brief is a Claim carrying the verbatim snippet that supports it, its URL, its
   date, and its provenance tier. See `claims.py` and `render.assert_sourced`.

2. Briefs are about organizations, never people. A person's name in the output
   is a build failure, not a warning. See `privacy.py`.

3. A run is reproducible. Fetches are content-cached, documents are filtered by
   an explicit `--as-of` date, and iteration is sorted throughout, so the same
   command produces the same bytes. See `cache.py`.
"""

__version__ = "0.1.0"
