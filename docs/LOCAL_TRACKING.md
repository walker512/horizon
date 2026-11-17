# Local policy and source-file tracking

This extension adds a real, repeatable **local-file acquisition workflow** to Horizon's evidence desk. It is part of the approved AI product/policy change tracking direction, but does **not** finish that broader topic: public-web fetching, subscriptions, source authentication, semantic policy classification and notification delivery remain absent. It is not a new repository or a claim that all news-related topics are covered.

## Working flow

1. Obtain a source text file that you are authorized to process. You can export it manually or produce it using your own acquisition pipeline. This tool will not fetch its URL.
2. Register the file with an explicit title and source URL (metadata only):

```sh
python -m horizon.watch --data-dir ./policy-workspace register --file ./policy.txt --url https://example.org/product/policy --title "Product policy" --availability full
python -m horizon.watch --data-dir ./policy-workspace list
```

Registration prints its `source_id`. Replace `SOURCE_ID` below with that exact value. Files must already exist. By default availability is `summary`; choose `full` only when appropriate. These labels are your declarations, not verification of publisher authenticity or completeness. `--kind` defaults to `report`; `primary`, `relay`, `summary` are also available. A primary label is not authentication.

3. Open the normal Horizon workspace to connect source passages to claims and make your own editorial decisions:

```sh
python -m horizon --data-dir ./policy-workspace
```

4. After your acquisition process updates the same local text file, scan:

```sh
python -m horizon.watch --data-dir ./policy-workspace scan
python -m horizon.watch --data-dir ./policy-workspace changes SOURCE_ID --out change-review.json
```

`scan` runs **once**, not continuously. You may invoke it from a scheduler you control, but this package neither installs a scheduled job nor sends notifications. Changes are ordinary immutable Horizon snapshots and invalidate prior affected approvals. Refresh the already-open browser to see changes made by this separate CLI; the browser is not live-updated. To approve new wording, read the source and relink current evidence through the existing editor. No semantic conclusion is made automatically.

5. Stop tracking without deleting source history:

```sh
python -m horizon.watch --data-dir ./policy-workspace untrack SOURCE_ID
```

To change the local path or declared availability, untrack and register again. Re-registering an existing URL retains its existing source metadata (title/kind/origin); use the existing Horizon source editor to change metadata. Registering new text for that URL still invalidates affected approvals. At most 50 files may be tracked per workspace.

## Scan and version semantics

- Identical content, availability and error to the latest version is `unchanged`; no duplicate snapshot is created. Newlines and other textual differences are not silently normalized.
- Different valid text yields `changed`, a new immutable version and persistent approval invalidation for linked claims.
- Missing, symlink, special, invalid UTF-8, blank, NUL-containing or oversized files yield `unavailable`, recorded as a failed acquisition snapshot with no supposed source content. This **does not mean a publisher deleted a policy**. Repeated identical failures are idempotent snapshots; each attempted scan is still logged.
- A valid file after a failure yields `recovered`; even restoration of identical historical text is a new latest snapshot. Historical approvals do not revive automatically. Previously linked evidence remains tied to its exact older version.
- All source updates, watcher check metadata, review invalidations and the scan audit log commit in **one database transaction**. A database quota/validation failure rolls back the entire scan. An unavailable file itself is a valid failed-acquisition record, not a transaction failure.
- Empty tracking list returns an empty result and does not mean anything was monitored. A successful scan has exit 0 even when content changed; exit 3 means at least one tracked file was unavailable. Invalid registration/operational failure gives exit 2.

Tracked input is UTF-8, at most 2 MiB / 500,000 characters, regular leaf files only, with the existing Horizon workspace caps of 500 sources, 2,500 snapshots and 6 million snapshot text characters. Parent directories and filesystems must be trusted; this does not protect against hostile filesystem mutation, remote filesystem hangs or publisher spoofing. Nonblocking/no-follow flags are used where available. The application never searches arbitrary directories or infers which files you wanted tracked.

## Change review

The JSON review includes current source metadata, latest availability/hash, observation timestamps, a compact snapshot timeline, nearest previous **available** comparison version, an exact line diff when bounded, and linked claim decisions/current statuses. No local registered path is included.

A current failed acquisition is `unavailable_not_deletion` with no diff. After recovery, comparison skips failed snapshots and uses the last available version; their intervening failures remain in the timeline. A first available snapshot has no comparison. Same historical text is explicit, not inferred to be a fresh human approval.

Diff generation supports at most 100,000 characters / 1,000 lines in each compared version. Larger changed documents are explicitly `changed_diff_omitted_size_limit`, never called unchanged. Full immutable texts remain in the workspace for inspection. Diff lines preserve their original newline endings. This is text change detection, **not** interpretation of legal/policy meaning, announcement dates, retroactivity or affected product versions. Timestamps are local observation/import metadata, not authenticated publication dates. Imported history may have user-supplied timestamps.

`changes --out` creates a new file exclusively; it never overwrites an existing export. Output is bounded to 4 MiB with explicit LF JSON bytes. A filesystem write failure may leave a partial file; remove/review that file before selecting a fresh destination. The export is a point-in-time review, not a signed artifact or independently verified publisher statement.

## Local storage, sharing and compatibility

The extension adds one `local_watches` table to the existing SQLite workspace. Existing sources, snapshots, claims and evidence are not migrated or rewritten. Registered **absolute file paths** are stored in that local database, so protect database backups. `list`, change reports and portable project exports do not disclose those paths; source text could independently contain them, and is not sanitized.

The browser's portable project JSON deliberately excludes machine-local registrations. It exports the usual source versions, evidence and audit history. Importing it into another workspace does **not** recreate watchers or read someone else's paths; explicitly register files again there. A full database backup includes watcher configuration and paths. Stop the server and CLI before making a filesystem copy of the database.

Public project exports and diffs can include private/copyrighted policy text, source URLs and claim notes. Review before sharing. This is not anonymization. URLs are never fetched; there are no external messages, model calls, telemetry or new remote credentials. This extension does not change the browser routes or UI files.

## Validation and coverage boundary

22 new public synthetic tests exercise registration, unchanged scans, actual file changes, missing/recovered files, idempotency, stale approval invalidation, no resurrection, comparison limits, portable import without watchers, privacy of paths, FIFO/symlink rejection, transaction rollback and actual CLI use. Together with the existing 31 tests, **53 tests passed on Linux/Python 3.12, zero skipped**, including the existing real loopback HTTP tests. Synthetic fixtures are not real policy monitoring or user validation.

Historical browser acceptance applies only to the unchanged published browser code. This extension's new CLI was tested; no new browser flow, hosted CI, Windows/macOS, public-site acquisition or scheduled delivery was tested. These remain explicit gaps, not reasons to label broader topics complete.

Existing tools such as [changedetection.io](https://github.com/dgtlmoon/changedetection.io) provide actual webpage monitoring and notification integrations far beyond this local-file mode. Horizon does not claim novelty or superiority over them. No head-to-head runtime comparison was run for this extension. Its implemented connection is local revisions → stale linked evidence → persistent review invalidation in the existing Horizon workspace.
