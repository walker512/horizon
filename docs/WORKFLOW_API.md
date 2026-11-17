# Integrated loopback workflow API

This is a service integration of Horizon's existing capabilities, **not a new frontend**. It makes the same source/claim review, discovery, local-file tracking, actions and event models available through one loopback HTTP process. All existing editorial routes and page files remain available. A dedicated workflow UI has not been implemented or browser-tested for this increment.

Start normally:

```sh
python -m horizon --data-dir ./my-workspace --port 8769
```

Only `127.0.0.1` is bound. Do not expose this single-user service through a public proxy. It has no multi-user authentication. Existing exact Host and Origin checks, JSON request requirements and CSP remain in place. A same-machine client with access can operate the workspace; these controls are not an adversarial local-user security boundary.

## Bounded reads

```sh
curl 'http://127.0.0.1:8769/api/workflow'
curl 'http://127.0.0.1:8769/api/workflow?resource=claims&offset=0&limit=25'
```

Resource is `overview` (counts), `claims`, `actions`, `events`, `queries` or `watches`. Offset must be 0..10000; limit 1..50 (default 25). Unexpected or duplicate query parameters are rejected. Each list gives `total`, `offset`, `limit` and `items`. Separate pages are not a transactional snapshot; concurrent edits can change membership. Data gathering is bounded by each underlying workspace limit.

Action/event list results expose current status and basis warnings. Event lists omit full captured quotations; request `event-show` for those. Watches never return registered filesystem paths. No GET collects GitHub data, scans local files, executes a task or changes editorial decisions. Module startup creates missing extension tables; ordinary list reads do not create action/event records.

## Explicit POST operations

Use `Content-Type: application/json`. Route is `/api/workflow/OPERATION`. Each operation accepts **exactly** its listed fields; supply empty strings where an optional value is not desired. Extra or missing fields are rejected. Duplicate JSON object keys are rejected at every nesting level before any workflow operation, including conflicting repeated consent fields. This shared bounded parser also applies to existing JSON write routes and GitHub response parsing.

- `action-create`: `claim_id`, `title`, `why`, `steps` (array), `owner`, `due`. Returns `action_id`.
- `action-check`: `action_id`, `index` (zero-based integer), `done` (boolean), `note`.
- `action-status`: `action_id`, `status`, `note`.
- `action-review`: `action_id`, `note`. Rebase to the current reviewed claim, with the same changed-basis checklist reset as the CLI.
- `action-edit`: `action_id`, `title`, `why`, `owner`, `due`, `note`.
- `action-show`: `action_id`. Returns `action` including captured basis and history; no external effects.
- `event-create`: `claim_id`, `title`, `kind`, `precision`, `start`, `end`, `zone`, `note`. Returns `event_id`.
- `event-revise`: `event_id`, `title`, `kind`, `precision`, `start`, `end`, `zone`, `note`. Like the CLI, revision explicitly restores a withdrawn event to active and records the previous interpretation.
- `event-withdraw`: `event_id`, `note`.
- `event-show`: `event_id`. Returns `event` with captured basis/history.
- `radar-add`: `label`, `query`, `per_page` (integer 1..50). Returns `query_id`; this only stores a query locally.
- `radar-review`: `query_id`. Returns a local `review`, no network.
- `radar-collect`: `query_id`, **`allow_network: true`**. Sends the saved query to the fixed public GitHub API and returns `review`.
- `radar-import`: `query_id`, `repo_id` (integer). Imports a selected latest successful API metadata summary locally, not its README/code and not an approved claim.
- `watch-scan`: **`allow_local_reads: true`**. Reads only files explicitly registered earlier through the local tracking CLI. Returns `results`.
- `watch-changes`: `source_id`. Reads already stored versions and returns `changes`; no new file read or network.

The consent flags must be the JSON boolean `true`, not `1`, a string, null or an omitted value. They are intentionally separate: consent to contact GitHub does not imply consent to scan files, and neither executes external tasks. A future client must explain the relevant boundary before sending them. The server does not itself show a confirmation dialog or authenticate an individual human click. Do not send secrets in search queries.

Example creation from an already reviewed claim (replace the ID):

```sh
curl -H 'Content-Type: application/json' \
  -d '{"claim_id":"CLAIM_ID","title":"Evaluate the option","why":"Decide whether it fits","steps":["Read limitations","Run an authorized synthetic check"],"owner":"Me","due":""}' \
  http://127.0.0.1:8769/api/workflow/action-create
```

Underlying state constraints are unchanged. A stale basis cannot be completed or silently refreshed; a re-reviewed changed basis resets checklist flags; historical done/withdrawn records remain visible. Dates/events are declarations, not fact verification. See ACTIONS.md and TIMELINE.md for exact semantics. This API has no arbitrary file registration/read path, shell command execution, message-sending endpoint or URL-fetch endpoint. Local path registration remains a deliberate CLI operation.

## A full correction flow

The real HTTP regression performs this chain against a new synthetic workspace:

1. Add source text, create a claim, link an exact passage and explicitly record editorial approval through the original routes.
2. Create a human action and an unknown-time event through workflow routes.
3. Record checklist progress.
4. Add a corrected source version through the original source route.
5. Observe `needs_review` for both action and event; attempted action completion is rejected.
6. Remove old evidence, revise the claim, link the corrected passage and explicitly approve it.
7. Revise the event interpretation, review the action basis and confirm checklist flags reset.
8. Record new checks and human completion; withdraw the old event interpretation with a note.

No step is automatic factual validation or execution of the described real-world task. These operations are individually transactional, not one transaction spanning every HTTP request; an interrupted client must inspect current state before retrying. Create operations can create another record if blindly retried after an ambiguous response; there is no idempotency-key protocol. Clients should retain returned IDs and check list/detail state. Existing source snapshot idempotency remains as documented.

## Responses, privacy and storage

A rejected workflow read/write returns HTTP 400 with a generic non-echoing error. Bad Host/Origin remains 403, non-JSON write content type 415. Other original editorial endpoints retain their existing behavior. All responses use the existing `no-store` policy.

**HTTP 200 does not imply monitoring success or quality.** `radar-collect` can return `review.status: "failed"`; `watch-scan` can return individual `result: "unavailable"`; actions/events can need review. Clients must inspect structured states. Failed GitHub observations do not return old candidates as fresh; unavailable local files are not interpreted as publisher deletion. There are no automatic retries, scheduling or notifications.

Detail responses and exported records can contain private text, notes, URLs, queries and quotations. Review before sharing. Portable editorial project JSON still excludes extension registries/history, while a full SQLite backup retains them. Starting the workflow service adds extension tables but does not rewrite existing editorial data. As before, stop all processes before a filesystem database backup.

## Verified scope and remaining work

13 new tests, **143 total passed on Linux/Python 3.12, zero skips**, including actual loopback HTTP for the chain above and Host/Origin/content-type/consent/pagination boundaries. Direct dispatch tests use an injected fictional GitHub response; loopback tests spy on fetch/scan boundaries and send raw conflicting duplicate-key JSON to prove those requests never invoke either boundary. They do not contact a real external service. Earlier Radar CLI live-request evidence remains historical, not a new browser/API-network run for this service increment.

Static browser assets are unchanged. No workflow frontend or browser interaction test is claimed; no denied browser/CI route was retried, and no security settings were relaxed. This service layer enables integration, but does not close the interactive UI, reminder/delivery, broad discovery, public-policy acquisition or semantic interpretation gaps in original topics #2–5. It is not a new repository or an independent superiority claim.
