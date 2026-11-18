# Production catalog health

`python3 scripts/catalog_health.py` monitors https://ziontechgroup.com, which is
published by Zion-support/zion-support.github.io. It does not test this repository's
build. Run deterministic tests with:

```
python3 -m unittest discover -s scripts -p 'test_catalog_health.py' -v
```

The watchdog checks real GET responses, follows at most five HTTP redirects on
the same origin, requires final HTTP 200 and rejects unrelated destinations.
Transport/HTTP failures are reported separately from content failures. Every
probe is bounded by a 20-second socket timeout and a 4 MB response limit; the
workflow also has an overall timeout. Failures remain nonzero, with no automated
writes, email, lead submissions, or issue creation.

Contracts:
- Current visible homepage offerings, free Discovery CTA to the actual Discovery
  route, no conflicting dollar-priced Discovery CTA, and current agents/FinOps links.
- Commercial routes retain real HTML headings and do not resolve to soft 404s or
  unrelated pages. The legacy `/agents/` alias must resolve to the canonical
  autonomous agents destination; static meta refresh aliases also need the
  correct canonical and a usable fallback anchor. The destination is probed
  independently.
- All five current FinOps estimator languages need the form, numeric inputs and
  submit button inside it, output, valid copy JSON, and the current JS reference.
  The JS is fetched independently and checked for calculation and submit wiring.
  A placeholder page plus a separately reachable JS file is not healthy.

The retired `/assets/js/zion-catalog.js` is not a production dependency and is
intentionally not checked. The homepage language is not forced to Portuguese.
This is a read-only HTTP/DOM monitor, not a browser integration test; it does not
execute calculator JavaScript or prove third-party Discovery email delivery.
The site's own calculator behavior tests should continue testing numerical and
browser behavior. Discovery provider checks belong to that site's tests, not
unrequested production submissions from this monitor.

PRs only run offline selftests. Schedule (every six hours), dispatch, and relevant
pushes to main additionally probe production. A passing PR selftest does not
claim production is healthy. Production defects must be fixed in the publishing
repository, not papered over by relaxing this monitor.
