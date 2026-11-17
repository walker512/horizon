# Verification scope

## Original editorial-desk release (historical)

The runtime, static UI, demo and license are byte-identical to the independently reviewed candidate that passed private browser CI at commit b15c9a65645ca40c8601d010766cead0a1798483. Only documentation and a newly written public synthetic test suite are added/updated.

Run `python -m unittest discover -s tests -v` from the extracted source folder with Python 3.11+. The 31 included tests cover models/imports/exports/feeds and seven real loopback HTTP checks. They are newly written tests, **not the original 53-case private suite**. The final candidate ZIP is freshly extracted and tested locally before handoff. A local run does not imply new Windows/macOS/browser CI for this package.

## Historical evidence for the unchanged editorial/browser runtime

- Original private model/HTTP/UI-expression suite: 53 checks passed during development; that suite is not included.
- Last private browser CI: 30 desktop checks at 1500px and 40 narrow checks at 390px passed with Chromium sandbox enabled. Actual screenshots were independently inspected, including withholding decision, neutral re-review wording, stale warning and disabled stale approval.
- Narrow cards, selected keyboard/Enter flows, simulated touch access and viewport-matched final export were tested. This is not full accessibility certification or real-phone testing. Withheld HTML content was asserted; it did not receive a dedicated rendered screenshot.
- Initial defects in persistent review invalidation, incomplete imports and deep JSON handling were fixed and independently re-reviewed.
- FactCircuit offline quickstart/trace and same-corpus editorial replay were executed; no verification superiority was shown. TrendRadar's isolated feed parser was tested; its complete application was not. AIHOT was not executed.

## Not established

No real-user study, speed advantage, fact-checking accuracy, full competitor GUI comparison, source authenticity, growth or adoption is established. Windows, macOS and non-Chromium runtime/browser acceptance remain untested for Horizon. The current candidate packaging check does not replace that missing coverage.

Tests use fictional sources and editor judgments. Private logs, competitor checkouts and personal workspaces are excluded from the distribution.

## Subsequent CLI extensions

Local source tracking added 22 public tests; GitHub discovery adds 28 public tests. The current source has 81 passing synthetic/local tests (31 original + 22 local tracking + 28 radar), zero skips on Linux/Python 3.12. Existing model, server and browser files remain unchanged. New CLI modules are not covered by the old browser CI. See LOCAL_TRACKING.md and GITHUB_RADAR.md for exact behavior and separate real-network validation; no new cross-platform or hosted CI claim is made.

## Evidence-to-action extension

The local action-planning CLI adds 23 synthetic tests. The current full suite has 104 passing tests on Linux/Python 3.12, zero skips. It covers actual SQLite transactions, source/review changes, completion gates, checklist resets on basis change, historical completion warnings, restart persistence, export escaping and real CLI commands. No new browser UI files or network requests are involved; historical browser checks are not represented as new action-UI acceptance.

## Event timeline extension

26 new public synthetic tests exercise event-window normalization, DST day lengths, skipped dates, offset rejection, interval overlap/unknown ordering, source observation vs event times, retained withdrawals/revisions, stale basis, atomic updates and real CLI export. The full candidate suite has 130 passing tests on Linux/Python 3.12, zero skips. Named zones require an installed IANA timezone database. No new browser code, live event collection or factual chronology verification is implied.

## Integrated HTTP workflow service

13 new tests exercise the loopback service and direct service dispatch, bringing the full suite to 143 passed on Linux/Python 3.12, zero skips. Real HTTP covers source→claim→review→action/event→source correction→stale completion refusal→human re-review→completion/withdrawal, consent boundaries, pagination and Host/Origin/media-type checks. External transport is mocked in new dispatch tests, not contacted. The server routing changed, but static UI/model and individual CLI engines are unchanged. No new workflow frontend, browser run or cross-platform CI is claimed.

## Full-workspace backup and recovery

18 new public synthetic tests verify SQLite structural/schema checks, real full-table backup, live committed WAL contents, concurrent transactional consistency, safe restore resets, preserved workflow histories, exclusive destinations, failed-publication cleanup and real CLI. The complete current suite has 161 passing tests on Linux/Python 3.12, zero skips. This is not an untrusted SQLite sanitizer, new browser verification or cross-platform certification.

## Official-policy collector increment

183 public tests pass locally on Linux/Python 3.12, zero skips, including 22 new original-synthetic-page tests. The tests mock the HTTP boundary, not the extractor/storage/approval/change-report engines. One separate final-collector HTTPS observation of the Anthropic catalogue page succeeded; no real change, effective-date interpretation, or OpenAI collector success is claimed. Private raw workspace/body is excluded from the release. Prior GUI tests do not constitute acceptance of this CLI increment; original frontend code is unchanged. No new Windows/macOS or browser run.

RC2 adds declared-length/framing checks and four tests using the actual http.client.HTTPResponse over synthetic bytes. The live official-page observation was on RC1; RC2 was not newly exercised online.

## Structured product-field increment

204 public tests pass locally on Linux/Python 3.12 with zero skips, including 21 new synthetic tests. Actual CLI add/list/show/compare/withdraw and full-backup restoration are exercised. The original-synthetic demo was executed and retained both historical evidence and the needs-review warning with an exact 0.50 price difference. Official pricing/model/rate-limit/license documentation informed schema dimensions, not a claim to auto-extract current facts. No new online collection, browser or cross-platform run for this increment. The backup allowlist now includes product_observations; legacy/editorial-only portability limitations are documented.
