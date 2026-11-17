# GitHub discovery observations

This Horizon extension provides an actual public-search → observation history → explicit star-count comparison → selected evidence-import workflow. It advances the GitHub early-discovery direction without pretending that the whole topic is finished. It does not guarantee early discovery, global coverage, future popularity, project quality or trustworthy stars.

## Quick start

Choose your own public search criteria. Example (adjust the date for your intended window):

```sh
python -m horizon.radar --data-dir ./radar-workspace add --label "Recent Python projects" --query "created:>=2026-11-01 language:Python stars:>=10 archived:false" --per-page 20
python -m horizon.radar --data-dir ./radar-workspace list
```

Copy the returned `query_id` in place of `QUERY_ID` below:

```sh
python -m horizon.radar --data-dir ./radar-workspace collect QUERY_ID --allow-network
python -m horizon.radar --data-dir ./radar-workspace review QUERY_ID --out discovery-review.json
# After a meaningful interval, explicitly run collect again to obtain another observation.
python -m horizon.radar --data-dir ./radar-workspace collect QUERY_ID --allow-network
```

`add`, `list`, `review` and `import` are local. **Only `collect` sends the saved query text to GitHub**, and requires `--allow-network` each invocation. Do not put private project names or secrets in queries. It is one request, with no automatic retries, background scheduler or notification registration. You can invoke it from your own scheduler; respect GitHub's service limits. A failure is recorded rather than silently replaced by old successful results.

Select a numeric repository ID from the latest returned page:

```sh
python -m horizon.radar --data-dir ./radar-workspace import QUERY_ID REPO_ID
python -m horizon --data-dir ./radar-workspace
```

Refresh an already-open Horizon page after importing. The selected API metadata appears as a **summary source**, not a quality review or factual approval. Read the actual project separately before making claims about usefulness, code, licensing or safety. This command does not fetch README files, clone projects, execute code, star repositories or create issues. It does not automatically generate or approve claims. Reimporting the same observation is idempotent.

## Observation rules

- Endpoint is fixed to `https://api.github.com/search/repositories`. Requests use public unauthenticated access, sort by stars descending, page 1 only, and 1..50 records per page. There is no token/account lookup or private repository access. TLS validation is not disabled. Standard environment proxy configuration can apply; redirect responses are errors, not followed.
- API response size is bounded to 2 MiB, connection/read socket timeout is 15 seconds and the read loop checks a 30-second elapsed deadline between chunks. A blocking read may take its socket timeout beyond that check, and DNS resolution is not a hard wall-clock budget. This is not an unlimited crawler or a custom network sandbox.
- Search text is 1..256 characters without control characters. GitHub can reject otherwise syntactically unsupported queries; the tool does not pretend to validate every GitHub qualifier. Query definitions are immutable. Create another labelled query to change criteria/page size; results from separate query IDs are not mixed for growth comparisons.
- Returned `total_count`, `incomplete_results`, page limit, returned count and page truncation are explicitly included. GitHub search has its own search/time/coverage constraints; **`incomplete_results: false` does not make our single page exhaustive**.
- Stable numeric repository IDs link observations even if the repository name changes. “First seen” means first returned in **this local query's history**, not newly created globally and not a previously undiscovered project.
- Raw star delta is only calculated between two successful observations of the same repository ID in the same query. Negative deltas are retained. Reappearing repositories use their last actually observed count and interval, not an invented count for missing observations.
- Per-day rate is an arithmetic normalization of observed delta, **not a forecast**. It is omitted for intervals under one hour. If the local clock is non-increasing, the raw count difference remains but elapsed/rate are unavailable with an explicit clock status.
- IDs absent from a later page are `not_returned_since_previous`, not deleted repositories or negative growth. Search ranking changes, pagination truncation, renamed criteria matches and API incompleteness can change membership.
- A failed latest attempt returns no current candidate list. The last successful observation ID is provided for context, but stale candidates are not presented as fresh. Import requires the latest attempt to be successful.

The output is not a statistical causal model, manipulation detector, recommendation guarantee, ranking of all open source, or GitHub Trending replacement. The creation time and counts are GitHub-reported metadata; no independent authentication of these claims is attempted.

## Stored data and Horizon integration

`radar_queries` and `radar_runs` are additional SQLite tables. Maximum 20 saved queries and 200 observations (including failed attempts) per workspace. Use a new workspace/archive when full. No automatic deletion of older history is performed. A run saves only a selected metadata projection plus the original response-byte SHA-256; the complete raw API body is **not retained**, so that hash cannot be recomputed from the projection. Hashes/history are not signed attestations.

Selected fields are ID, name/derived GitHub URL, star count, creation time, description, language, fork and archived flags. API data is untrusted metadata, never executable instructions. URLs are generated from validated repository names. A displayed rank is its place in the returned API page, not a full-site rank.

Selected import stores query, observation time, coverage and candidate fields in an immutable Horizon summary snapshot. The provenance group is `github-repository-ID` based on API identity, not a claim of independent corroboration. A renamed repository has a new URL and can therefore create another Horizon source; its origin group still records the shared repository ID. Current Horizon source deduplication is exact-URL, not a universal repository entity database.

Portable Horizon project JSON includes imported source summaries and evidence, but intentionally does **not** include the radar registry or full search history. Full SQLite backups include those tables. Review exports (`--out`) are standalone JSON, not an import/restore format or a signature. Output creates a new file exclusively, with a 4 MiB bound and LF bytes; no overwriting existing files. Protect backups and review queries, descriptions and imported evidence before sharing. Normal Horizon source-text/copyright/privacy warnings continue to apply.

## Errors and exit codes

- 0: local operation completed, or a successful API observation (which can still be empty/incomplete/truncated).
- 2: invalid invocation, missing network consent, unknown query/ID, invalid local output/workspace or quota failure.
- 3: the explicit collection attempt failed, such as API rate limiting, service/network failure or malformed response. The failed observation is recorded and earlier observations remain.

No access denial is retried via another service, proxy or endpoint. This tool does not request broad authentication as a fallback. Stop and inspect the error; do not treat a failed collection as “no new projects.”

## Validation and alternatives

28 public synthetic/local tests cover strict metadata typing, empty/incomplete/truncated results, duplicate IDs, fixed endpoint/no redirect handler, first observations without invented growth, exact intervals, negative counts, reappearance, rename identity, clock regression, failure/recovery, query isolation, summary import/idempotency, portable-export boundary and real CLI consent/export handling. Combined Horizon suite: **81 tests passed on Linux/Python 3.12, zero skips**. These tests make no network requests.

Separate implementation validation actually called the official unauthenticated public search API with a three-result query, persisted two observations about three minutes apart, checked that measured deltas had no short-interval per-day rate, and imported one selected metadata summary into a fresh local Horizon database. This confirms that code path worked for that request, not all repositories, rate-limit conditions or continuous monitoring. Live responses/private workspaces are not distributed as test fixtures. No real-user adoption or star-growth benefit has been measured. Existing browser files are unchanged; no new browser acceptance, cross-platform run or hosted CI is claimed for this module.

[GitHub's search API documentation](https://docs.github.com/en/rest/search/search?apiVersion=2022-11-28#search-repositories) describes search ranking, limits and incomplete responses. [OSS Insight](https://github.com/pingcap/ossinsight) already provides richer open-source analysis and rankings, while [RSSHub](https://github.com/DIYgod/RSSHub) offers broad feed aggregation. Only their primary documentation was read; no runtime head-to-head comparison was run. This integration's implemented benefit is connecting explicitly scoped observations with Horizon's evidence/review workflow, not inventing repository discovery or proving superiority.

Remaining topic gaps include scheduled delivery, broad coverage across discovery sources, durable repository watchlists outside page membership, adoption/quality evaluation and a dedicated interactive discovery interface. Other approved topics (#4 event timeline and #5 evidence-to-action workflow) are not completed by these observations.

### Response-framing correction

The transport now rejects conflicting/duplicate framing headers, invalid or oversized Content-Length, unsupported Transfer-Encoding and premature EOF relative to declared length, even if the truncated bytes form a complete JSON document. Actual HTTPResponse regressions cover successful length/chunked/close-delimited bodies and a prior-success→truncated-response→persisted-failure path. A failed latest observation still has no current candidates and cannot be imported. This adds no retries, redirects or network privileges.
