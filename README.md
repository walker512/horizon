# Horizon

**Keep the source. Show the reasoning.**

Horizon is a local, human-operated editorial evidence desk by **walker512**. Save source text as immutable snapshots, select exact passages, connect them to claims, and record an editorial decision. When a linked source changes, the earlier approval no longer applies.

**A human evidence-maintenance workbench, not a fact-checking engine, news crawler, or proven superior verifier.** The included example is entirely fictional. No claims about real events, model accuracy, adoption, or star growth are made.

## Run from the extracted folder

Python 3.11 or later; no third-party runtime dependencies.

```sh
python -m horizon
```

Open **http://127.0.0.1:8769**. On systems where `python` is not Python 3, use `python3` or Windows `py -3`.

```sh
python -m horizon --port 8769 --data-dir ./my-local-workspace
```

The default data location is `~/.horizon/workspace.sqlite3`. Choose a different data directory for a separate project. The server is single-user and binds only to `127.0.0.1`. Do not expose it through a public proxy.

## The normal workflow

1. **Load example** in an empty workspace. It contains a synthetic announcement, a relay of that announcement, and a failed retrieval record. Two passages are grouped under one declared common origin, not counted as independent corroboration.
2. Select the launch claim. Read its linked passages and add a review note. **Editorial approve** records your decision, not a factual verdict.
3. Click **Simulate correction**. The announcement receives a new immutable snapshot. Old quotations remain inspectable; the claim becomes **Needs review**, and another approval is blocked until stale evidence is addressed.
4. Read the latest revision. Edit the claim wording, unlink outdated passages, select the exact current passage and link it. You choose whether it supports, refutes, or merely provides context. Horizon checks that the selected text is present, not whether your interpretation is sound.
5. Approve revised wording or withhold it. Export a standalone HTML brief, a Markdown brief, or a portable project JSON.

A passage can be selected only after choosing a claim. Changing the selected claim clears the previous selection, so reselect the passage before linking.

## Complete workspace backup and safe restore

The original portable editorial JSON does not contain every workflow table. Use [docs/BACKUP.md](docs/BACKUP.md) for consistent full SQLite backups including discovery history, actions and timelines, and new-directory recovery with old approvals reset and machine-local file registrations removed. Backups contain private data and are not sanitized sharing formats.

## Integrated local workflow API

The running loopback server now exposes bounded workflow reads and explicit operations connecting discovery, registered-file scans, reviewed claims, actions and timeline events. See [docs/WORKFLOW_API.md](docs/WORKFLOW_API.md) for exact routes and a real tested end-to-end correction flow. This is service integration only: no new workflow frontend or browser acceptance is claimed.

## Evidence-linked event timeline (new local CLI)

Record a declared event time separately from source observation and local entry times. Use explicit offset instants, named-zone calendar windows or unknown time; overlapping windows do not invent a definite order. Corrections/withdrawals preserve history and source changes flag the captured editorial basis. See [docs/TIMELINE.md](docs/TIMELINE.md).

## Evidence-to-action planning (new local CLI)

Turn an editor-approved claim into a human-owned plan with rationale, checklist and optional due date. Record progress, block completion when its evidence basis is no longer current, and preserve historical completion with a visible re-review warning after source changes. See [docs/ACTIONS.md](docs/ACTIONS.md). No task, email, deployment or purchase is executed.

## GitHub discovery observations (optional network CLI)

Register a bounded public GitHub search, collect one page through the official API with explicit `--allow-network`, compare repository-ID observations over time, and import selected metadata summaries into the evidence desk. See [docs/GITHUB_RADAR.md](docs/GITHUB_RADAR.md). Only this separate command contacts GitHub; adding a source URL in the browser still never fetches it. It is not global Trending or a prediction of future stars.

## Local policy/source-file tracking (new CLI)

Register an explicitly authorized local text file, rescan after your own acquisition process updates it, and inspect version changes plus affected claims. No URL is fetched. See [docs/LOCAL_TRACKING.md](docs/LOCAL_TRACKING.md) for registration, scan, diff/export, failure/recovery and privacy details. This adds local-file tracking, not public-web subscriptions or semantic policy interpretation.

## Real inputs without hidden fetching

- **Add source:** paste text you have permission to process and record its URL, source type and availability. A URL is metadata only. It is never fetched.
- **Add revision:** save new text, a summary, or a failed-retrieval record. Prior versions are never overwritten. Identical latest text and availability are idempotent.
- **RSS / Atom import:** read a supplied XML file locally. Entry links are resolved against the feed URL, but no articles are downloaded. Feed content is labelled **summary**, even when lengthy. The preview supports URL deduplication, not GUID-based identity, JSON Feed, subscriptions, or scheduled refresh.
- **Common origin group:** a manual provenance label. Give known relays the same label only when you have evidence of the relationship. Empty means unknown. These counts are not a measure of independent sources or truth.

No AI model, API key, remote inference, telemetry, push notification, or automatic publishing is used.

## Editorial states

- **Not reviewed:** no applicable editorial decision.
- **Editor-approved wording:** a human supplied an approval and at least one supporting passage. It is not world-truth verification.
- **Needs review:** a linked source version, claim wording, source metadata or evidence selection changed after review, or a link points at an older snapshot.
- **Conflicting passages:** both supporting and refuting links exist. Horizon cannot decide which is right.
- **Withheld:** an editor chose not to approve the claim. A later material change can still require re-review.

Approvals are blocked for missing support, linked older versions, or an unresolved refuting passage. This does **not** detect misleading quotations, invented source text, wrong source classifications, unlinked contradictions, or incorrect human interpretation. A source labelled `primary` is not independently authenticated.

## Export, import and privacy

HTML and Markdown briefs display all claims, their status, quotations, source limitations and stale-version warnings. Withheld and unreviewed items are not silently turned into approved news. The HTML viewer has no scripts or remote assets; following a source link is a deliberate external navigation.

Project JSON contains source text, URLs, snapshots, claims, notes and the audit trail. Import is permitted only into an empty workspace and is transactional. Imported previous approvals reset to unreviewed. Imported audit records are supplied history, not authenticated provenance.

**Review your export before sharing.** It may contain private material, copyrighted text, URLs with sensitive parameters, or unverified assertions you supplied. Horizon is not a sanitizer or secret scanner. Hashes identify stored content; they are not digital signatures or proof that a publisher produced it. The audit trail records application operations but is editable by anyone controlling the local database.

## Comparison and verification

See [docs/COMPARISON.md](docs/COMPARISON.md) for pinned competing projects and actual limited tests. FactCircuit already implements immutable versions, evidence spans and correction tracing. TrendRadar is a substantially more capable feed aggregation product. Horizon does not claim either capability is novel or superior.

Its practical offering is a ready-to-use local editor connecting immutable source versions, exact passage selection, review invalidation and readable brief exports without writing an integration script. These functions are implemented and exercised, not claimed to be novel. FactCircuit's tested offline workflow has richer typed evidence lineage and cutoff semantics; Horizon does not replace them. Faster human work or superior verification has not been demonstrated.

The included synthetic tests cover state transitions, Unicode selections, import rollback, feed handling, export escaping and real loopback HTTP boundaries. Run `python -m unittest discover -s tests -v` from the extracted folder. No external services or dependencies are needed. The HTTP tests require permission to bind a temporary loopback port; a restricted environment can fail this stage, and no security settings should be changed to force a pass. See [docs/VERIFICATION.md](docs/VERIFICATION.md) for historical browser acceptance and the current package checks. No real personal data, private CI artifacts, browser profiles or private workspaces are included.

## Limitations

This is not the completed suite of news subscriptions, policy monitoring, timelines and action automation. Those overlapping directions should share an evidence model rather than become duplicate repositories. This version has no public-web subscriptions, source authentication, automated origin tracing, semantic fact evaluation, translation, scheduled delivery, rich collaboration, cross-browser certification, or real-device mobile acceptance. Narrow Chromium layouts were tested, not real phones.

Source URLs are deduplicated by exact URL. Query parameters, aliases or changing GUID/URL mappings may produce separate records. Snapshot timestamps record when the editor imported text, not verified publication times. Source metadata can change, with affected approvals invalidated; source snapshots remain immutable.

## License

Original Horizon code: MIT, copyright walker512. No competing project code is included. Competing source checkouts, comparison fixture adaptations and private evaluation runs are not distributed. Included tests use original fictional fixtures. Third-party source content remains subject to its own rights and licenses.

## Installation and local data

This is a source ZIP distribution, not a PyPI package. Extract it, enter its `horizon` folder and use the commands above; no `pip install` is necessary. For a first run, choose a new data directory and use the built-in fictional example. Use the SQLite backup CLI for a consistent live copy, or stop every server/CLI process before manually copying database files. No delete/reset command is provided; use a separate data directory to start another project. An occupied port is an error, not an invitation to terminate another application: choose a different `--port`.
