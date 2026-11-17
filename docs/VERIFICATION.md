# Verification scope

## Current source release candidate

The runtime, static UI, demo and license are byte-identical to the independently reviewed candidate that passed private browser CI at commit b15c9a65645ca40c8601d010766cead0a1798483. Only documentation and a newly written public synthetic test suite are added/updated.

Run `python -m unittest discover -s tests -v` from the extracted source folder with Python 3.11+. The 31 included tests cover models/imports/exports/feeds and seven real loopback HTTP checks. They are newly written tests, **not the original 53-case private suite**. The final candidate ZIP is freshly extracted and tested locally before handoff. A local run does not imply new Windows/macOS/browser CI for this package.

## Historical evidence for the unchanged runtime

- Original private model/HTTP/UI-expression suite: 53 checks passed during development; that suite is not included.
- Last private browser CI: 30 desktop checks at 1500px and 40 narrow checks at 390px passed with Chromium sandbox enabled. Actual screenshots were independently inspected, including withholding decision, neutral re-review wording, stale warning and disabled stale approval.
- Narrow cards, selected keyboard/Enter flows, simulated touch access and viewport-matched final export were tested. This is not full accessibility certification or real-phone testing. Withheld HTML content was asserted; it did not receive a dedicated rendered screenshot.
- Initial defects in persistent review invalidation, incomplete imports and deep JSON handling were fixed and independently re-reviewed.
- FactCircuit offline quickstart/trace and same-corpus editorial replay were executed; no verification superiority was shown. TrendRadar's isolated feed parser was tested; its complete application was not. AIHOT was not executed.

## Not established

No real-user study, speed advantage, fact-checking accuracy, full competitor GUI comparison, source authenticity, growth or adoption is established. Windows, macOS and non-Chromium runtime/browser acceptance remain untested for Horizon. The current candidate packaging check does not replace that missing coverage.

Tests use fictional sources and editor judgments. Private logs, competitor checkouts and personal workspaces are excluded from the distribution.
