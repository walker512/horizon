# Explicit official-policy observations

This increment fills **one** gap in the AI product/policy tracker: getting an actual official-page observation into Horizon's evidence/version workflow. It does not complete price/context-window/license/quota field tracking, interpret legal effects, send notifications, or predict changes. Catalogue entries are fixed in code, not user-supplied URLs:

- `openai-usage`: https://openai.com/policies/usage-policies/
- `anthropic-usage`: https://www.anthropic.com/legal/aup

```sh
python -m horizon.policies catalogue
python -m horizon.policies collect anthropic-usage --data-dir ./workspace --allow-network
# Use the returned source_id to inspect its change/affected-claim record:
python -m horizon.watch --data-dir ./workspace changes SOURCE_ID --out ./change.json
python -m horizon --data-dir ./workspace
```

Each collect requires explicit permission and performs a single ordinary public HTTPS request, without cookies, account credentials, a browser, JavaScript, redirects, retries or challenge-solving. Standard TLS verification and the host's normal urllib proxy configuration apply. Never use proxies to evade access restrictions. A blocked/unsupported page is recorded unavailable; do not bypass it. The catalogue listing and missing-consent tests do not connect. There is no scheduled/background collection and no HTTP endpoint for this new command.

## What is compared

The collector rejects ambiguous/invalid Content-Length and Transfer-Encoding framing; declared Content-Length must match bytes received. A close-delimited response without Content-Length cannot prove that the origin sent all intended text.

The collector requires HTTP 200 at the exact configured URL, UTF-8 HTML, identity content encoding, one completed `main` element and the expected H1 text. It removes script/style/noscript/template/nav/footer content and normalizes whitespace in static text. The output is always a **summary**, not a claim to capture the full policy. CSS-hidden text, decorative labels and repeated mobile markup may remain; screenshots, JS-loaded text, linked documents, metadata, effective-date semantics and page completeness are not evaluated. A matching heading does not authenticate content. Site restructuring can make extraction fail or create a noisy diff. Review the original page yourself before approving claims.

The raw-response SHA-256 is recorded in the local audit log, but raw HTML is not retained. It cannot be independently recomputed from the normalized snapshot; it is not a signature, provenance certificate or proof of freshness. Observation time is local retrieval time, **not** policy publication/effective time. Version comparison uses extracted text, so HTML-only changes can be unchanged. The first observation has no before-version; unchanged observations do not create duplicate snapshots.

A changed, unsupported or failed observation permanently invalidates linked approvals through Horizon's existing source-version rules. A later recovery does not revive them. `horizon.watch changes` distinguishes failed retrieval from deletion and lists affected claims; plans and timeline records using those claims will need review. No plan is executed. Existing source metadata is retained if its URL already exists; adding an official catalogue observation does not certify manually entered metadata.

All database changes for one observation, its audit entry and approval invalidation commit together. Reads happen before the database transaction; concurrent users see the observation commit order, not a certified network ordering. Quota/database failures roll back rather than silently report success. A failed fetch may create an unavailable first source record. Exit status is 0 for an available observation, 3 for unavailable/unsupported, and 2 for permission/input/database failure. Inspect structured `result`, not only whether the command printed JSON.

## Bounds and safety

2 MiB HTTP response, 128-element nesting limit, 500,000 extracted characters, 15-second socket timeout and a 30-second deadline checked between reads. These are not a hard wall-clock limit for DNS/OS/proxy operations. Existing workspace limits (500 sources, 2,500 snapshots, 6 million stored text characters) apply. No arbitrary URL, crawler, attachment fetch, automatic source acceptance, or generated legal advice is introduced.

Snapshots and audit data are private workspace content. Public tests use original synthetic HTML, not copied policies. Backups include these observations; editorial portable exports keep snapshots but not the full audit log. Preview all exports before sharing. Restore resets editorial approval as documented in BACKUP.md.

## Verification and comparison boundaries

Public regression tests exercise synthetic HTML through the actual extractor, mock only the HTTP boundary, and test permission refusal, response limits, protocol failures (including real HTTPResponse parsing of premature EOF), failure/recovery, persistent approval invalidation, transaction rollback, change reports and backup/restore. These are not fresh online observations of either site's future layout. The documented live run below is a separate manual observation, not a CI guarantee.

The RC1 collector (before the additional RC2 framing checks) was exercised against Anthropic's public Usage Policy via ordinary HTTPS in this development environment. It produced a summary snapshot. The live workspace/body is **not distributed**. RC2 framing checks were verified on synthetic responses, not with a new online run. OpenAI's catalogue entry has not been exercised by this CLI in this increment; reading its page with a research tool is not collector acceptance. No assertion of a real policy change is made from these one-off reads.

[changedetection.io](https://github.com/dgtlmoon/changedetection.io) offers general website change monitoring, selectors and notifications. This increment does not claim better extraction, broader coverage or unique change detection. Its practical integration is feeding official observations into the already implemented quote/claim/approval/action history. No same-input competitive performance test or real-user adoption study was performed.
