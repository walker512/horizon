# Human-reviewed project dossiers

This extension connects a **selected GitHub radar candidate → explicit README/metadata observation → original claim/quote/editorial review → immutable project dossier → declared same-scope comparison**. It fills a concrete part of understanding what a discovered project solves, candidate alternatives, and stated entry barriers. It does not discover competitors automatically, extract facts with AI, install or test projects, recommend a winner, or infer quality from stars.

## One local end-to-end example

```sh
python examples/project_review_demo.py --data-dir ./new-project-demo
python -m horizon.projects --data-dir ./new-project-demo list
```

The new directory must not exist. This original synthetic example supplies fake transport responses locally, creates explicit synthetic claims/quotes and scripted fixture-only approvals, writes two comparison artifacts, then shows a local source correction and a dossier withdrawal in `after-correction.json`. No GitHub request or real-project capability is involved. The script's approval of its own fixture is not a production automatic approval workflow.

## Observe an explicitly selected real candidate

Use `horizon.radar` to register and explicitly collect a public search first (see GITHUB_RADAR.md). Select one numeric repository ID actually returned in its latest successful page:

```sh
python -m horizon.projects --data-dir ./workspace select QUERY_ID REPO_ID
python -m horizon.projects --data-dir ./workspace collect PROJECT_ID --allow-network
python -m horizon --data-dir ./workspace
```

`select` is local. `collect` alone contacts GitHub and requires the flag every time (the Python API requires exactly `True`, not truthy values). It fetches public, unauthenticated `https://api.github.com/repos/OWNER/REPO`, checks the numeric ID and `private: false`, then fetches its `/readme`. At most two ordinary requests, no retries, redirects, cookies, tokens, private repositories, clone, code execution, extra files, README link traversal, `download_url` fetching or fallback. TLS and normal environment proxies retain their standard behavior; do not use proxies to evade restrictions. Response denial is recorded as unavailable.

A renamed repository's old URL may redirect, which fails deliberately. Explicitly select the same numeric ID under its new name from a later successful radar observation, then collect again. Reselection retains historical runs; dossiers based on old source identity need review. Each part records its own request URL: metadata retains the requested registration name, while README uses the canonical name returned for the same numeric ID. A skipped README records its intended URL with `request_attempted=false`, not a claim that a request occurred. No stable endpoint is invented. Existing local source titles/origin groups are retained by Store; reported `full_name` is the observation identity, not certification of pre-existing human metadata.

## What was observed

Metadata projection: numeric repository ID, returned name, default branch name, archived flag, and API SPDX **label** if supplied. `release_version` is explicitly unknown. Releases/tags, complete LICENSE text, dependency files, install commands, linked docs, actual hardware/runtime requirements and downstream licensing are not collected. An SPDX label is not a legal opinion, proof of open-source compliance or permission for a use case.

README must be a single API `type: file`, base64-encoded UTF-8 response. Only CR/LF are removed before strict base64 decoding; declared file size and Git blob SHA-1 must match decoded bytes. The SHA check is a Git blob integrity consistency check, not a signature or commit pin. Metadata and README are **two non-atomic observations**: default branch can move between requests. No latest-release verification or atomic-version guarantee is claimed. README Markdown stays plain source text; links, images, HTML and instructions are not rendered or executed. Availability is `summary` because repository coverage is incomplete, even when the README bytes are complete.

Each attempt is retained. If metadata identity verification fails, the README request is not attempted; its unavailable source marker does not claim an HTTP request occurred. Metadata can succeed while README fails: `partial` is not a fully current project observation. Failed sources have empty text plus a failure marker. Old successful snapshots are retained as history, not substituted for current content. Stable contents reuse existing snapshots; local observation time and raw API hashes stay in the run, not mixed into source prose. Raw API bodies are not retained, so their response hashes cannot be recomputed from projections. Decoded README text is retained; no signed provenance is implied.

Source changes/failures invalidate existing claim approvals under Store rules. Dossiers also compare bound source identities/snapshot IDs and all subsequent project observations; a later recovery does not revive an older dossier. Editing/reviewing a claim again does not rewrite a saved dossier: create a new one and optionally withdraw the old. Database mutations and each ordinary observation commit atomically. If source storage fails, its transaction rolls back and the tool attempts to record a separate `failed/persistence_failed` run so old dossiers cannot look current. A completely unwritable database cannot record that failure; the command reports an error. Do not interpret the older stored run as proof of a later failed invocation's success. Full run quota is checked before network access; concurrent writers can still exhaust it during a fetch.

## Build a dossier in one spec

Read the imported sources in the existing Horizon editor. Write a claim in your own words, select its exact supporting passage, resolve conflicts and explicitly approve the wording. Editorial approval is not fact verification. Then prepare one JSON spec, using the generated synthetic `spec-1.json` as a structural template:

```json
{
  "project_version": null,
  "entries": [
    {
      "category": "purpose",
      "criterion": "primary-task",
      "definition": "The task the README explicitly states it addresses",
      "unit": "text",
      "platform": null,
      "version_scope": "Observed default branch; release version unverified",
      "state": "known",
      "value": "Human description",
      "raw_value": "exact words in the supporting quote",
      "claim_id": "CLAIM_ID",
      "evidence_id": "EVIDENCE_ID",
      "note": "Human explanation of this mapping"
    }
  ]
}
```

The illustration shows one entry only: actual specs require 3..20 entries and all categories `purpose`, `alternatives`, `barrier`. Criterion labels must be unique within the dossier. For missing information, use `state: "unknown"`, `value`, `claim_id`, `evidence_id` all `null`, `raw_value: ""`, and explain what is missing in `note`. An all-unknown dossier is not a completed review. Unknown unit/platform/version scope is `null`, never an invented value. A candidate alternative is an attributed human classification, not an automatically verified substitute. Do not treat a README's comparative marketing as a benchmark result.

```sh
python -m horizon.projects --data-dir ./workspace add PROJECT_ID --spec ./dossier.json
python -m horizon.projects --data-dir ./workspace show PROFILE_ID
python -m horizon.projects --data-dir ./workspace compare PROFILE_A PROFILE_B --out ./comparison.json
python -m horizon.projects --data-dir ./workspace compare PROFILE_A PROFILE_B --format markdown --out ./comparison.md
python -m horizon.projects --data-dir ./workspace withdraw PROFILE_ID --note 'Incorrect scope; superseded by a corrected dossier'
```

Adding requires a fully available latest project observation and current editor-approved claims. Selected supporting evidence must belong to that project's local observed source and bound snapshot, so another repository's evidence cannot silently fill its entry. `raw_value` must occur in the selected quote. The full original claim, exact supporting/context quotes, URLs, source observation times and approval basis are captured in the same transaction. These checks cannot prove semantic entailment, honest labels, correct interpretation or real installation requirements.

## Same-scope comparison, not a ranking

Comparison takes 2..10 distinct profile IDs in one read transaction. Rows join on a human criterion label. `category`, `definition`, `unit`, `platform`, `version_scope` must exactly match and be known before `declared_comparable` is emitted. A different label remains a separate row; equivalence is never guessed. Scope equality is a declaration, not evidence that actual workloads match. No numeric score, best-project tag, value ordering or winner is generated.

`version_scope` is a **shared comparison condition**, for example “README observed at each project's default branch; release unverified”, not a demand that unrelated projects have the same version number. `project_version` is a separately displayed human declaration, or null for unknown. It is not derived from default branch or authenticated against releases. If exact pinned versions are needed, do not label this collector as having established them.

Full historical records, unknown cells, stale editorial basis, withdrawn status and review-required flags remain visible. Withdrawn or stale evidence is not promoted to a current conclusion even if declared scopes match. Markdown includes the full criteria/mapping and quoted evidence; dynamic punctuation is encoded to avoid interpreting explicit Markdown/HTML syntax. This is not a universal sanitizer; a renderer can still recognize decoded URLs or create previews. No browser rendering test is claimed. JSON retains literal supplied text and URLs for audit. **Both exports can disclose source text, architecture, notes or copyrighted material: inspect before sharing.** No public export/upload happens automatically.

## Bounds, persistence and acceptance

100 selected projects, 500 collection attempts, 500 immutable profiles, 20 entries/profile, 256 KiB captured basis/profile, 32 MiB profile storage, 4 MiB exclusive-create export. Existing source/snapshot workspace limits apply. Each HTTP response is limited to 2 MiB, README decoded bytes to 512 KiB and text to 500,000 characters. HTTP Content-Length/Transfer-Encoding ambiguity and premature EOF are rejected; close-delimited bodies cannot prove the origin intended more bytes. Socket timeout is 15 seconds and elapsed read deadline 30 seconds checked between reads, not a hard bound on DNS/OS/proxy behavior. Local spec files use existing regular/non-symlink/UTF-8 bounds. No directories or repository trees are enumerated.

New full-backup tables: `project_registry`, `project_runs`, `project_profiles`. Backups retain them; restore resets editorial approvals, leaving known dossier bases needing review. Older Horizon versions reject these unfamiliar tables. Editorial portable JSON still omits the project registry/runs/dossiers; use full backups for these. Backups and output are not anonymized or signed. No UI forms or server routes were added; the existing editor performs claims/evidence/review and this CLI performs the project workflow. No browser/Windows/macOS acceptance or competitive superiority is claimed.

The local tests and synthetic demo are documented after execution in the implementation report. Live public API acceptance, if separately performed, is a limited private verification, not distributed README fixtures or a guarantee of future API availability.

### Executed validation for this increment

The complete synthetic suite ran locally on Linux/Python 3.12: **302 tests passed, zero skips** (257 prior tests, 4 additional radar HTTP-framing regressions, 41 project-dossier regressions). The original synthetic end-to-end demo was separately run and its before/after-correction exports inspected. Project tests include two-request consent/identity checks, malformed README/base64/size/blob hash, unchanged observations, partial failure/recovery, wrong-project evidence rejection, quote/approval binding, rename/reselection races, unknown/withdrawn/different scopes, persistence rollback/failure, quotas, special files, actual CLI outputs, backup resets, and real `HTTPResponse` parsing of early EOF and chunked framing.

A separate private manual run made one public search for `walker512/horizon`, then two ordinary unauthenticated API requests through this collector. It returned an `observed` run with metadata and README summary sources, a 13,960-byte decoded `README.md`, and a matching Git blob SHA. This checks that ingestion path for that repository and moment only, not a human-reviewed competitive comparison, freshness guarantee, project quality recommendation, other repositories, rate-limit behavior or browser UI. Raw live content/database stay private and are not bundled with the synthetic fixtures. No code execution, clone, account token, deployment or publication occurred. No further real network call is implied by offline regression tests.

RC2 corrects per-part request URL provenance for canonical casing and same-ID renames, with failure and skipped-request regressions. The live GitHub observation above was made on RC1; RC2 was verified offline without another network request.
