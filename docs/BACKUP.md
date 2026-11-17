# Complete workspace backup and safe recovery

Horizon now has two different export purposes:

- The browser's portable project JSON and briefs are **editorial sharing formats**, not the complete workspace. They do not contain watcher configuration, radar history, actions or timeline tables.
- This local CLI makes a **consistent full SQLite workspace copy**, including those workflows. It can restore a trusted copy into a new directory, with safety resets described below.

This is an operational improvement for the integrated #2–5 workflows, not another repository or a claim that all original discovery/monitoring/planning requirements are finished.

## Create and inspect

```sh
python -m horizon.backup create --data-dir ./my-workspace --out ./workspace-backup.sqlite3
python -m horizon.backup check ./workspace-backup.sqlite3
```

Creation uses SQLite's online backup API, not a raw copy of the main file. It includes committed journal/WAL contents and can work while the app is open. Concurrent transactions are copied consistently; an uncommitted change is not promised to appear, and the result is not guaranteed to be the very latest value after the command returns. Heavy continuous writes can prevent a timely copy; the operation fails without publishing a partial destination.

The destination must not exist, including as a symlink. The parent directory must already exist. The complete database is validated in a same-directory temporary file, flushed, and published with a hard link that cannot overwrite an existing path. No hard-link fallback that replaces files is attempted. If your filesystem does not support this operation, it fails and leaves the existing destination alone. This workflow was tested on Linux; Windows/macOS and every filesystem type have not been tested.

The CLI prints table counts and a SHA-256 of the created file, not record contents or source paths. Keep that hash separately if useful for detecting later byte changes; it is not a signature or proof of provenance. Backup files start with owner-only temporary-file permissions on the tested platform. You remain responsible for storage access, encryption, retention and copies.

## Restore into a new workspace

Use only a trusted backup that you created or otherwise reviewed. This is **not an untrusted database upload service or a comprehensive SQLite sanitizer**.

```sh
python -m horizon.backup restore ./workspace-backup.sqlite3 --data-dir ./restored-workspace --acknowledge-reset
python -m horizon --data-dir ./restored-workspace
```

The target directory must not already exist, even if empty. The explicit `--acknowledge-reset` flag acknowledges that:

1. All claim editorial decisions become `unreviewed`; review signatures and approval timestamps are cleared. Existing source versions, quotations and supplied audit history remain.
2. Active registrations of machine-local source files are removed. No restored path is read. Explicitly register the correct files for the new machine/workspace yourself.
3. Radar query definitions and past observations remain, but nothing is collected automatically. A later collection still requires the normal explicit network consent.
4. Action and timeline records/history remain, including a human-recorded `done` or `withdrawn` state. Their basis reads as needing review because the restored claim is unreviewed. A historical completion is not automatically revalidated or executed again.
5. A restore audit entry records the resets. Original backup bytes and the original live workspace are not changed.

Re-review the evidence in the restored editor before using it for new decisions or completion. These resets intentionally follow the same principle as portable-project import: supplied history is not a new trusted approval. The tool does not infer which old decisions remain correct.

The restored `workspace.sqlite3` is published only after the copy, resets and structural checks succeed. If publication fails, temporary files are removed and an empty just-created target directory is removed if safe. It never recursively deletes an unexpected file/directory. Concurrent hostile directory replacement is outside the trusted-local-filesystem boundary; do not operate in directories controlled by someone else. Power-loss durability of the containing filesystem is not certified.

## What `check` proves, and what it does not

The file must be a regular, non-symlink leaf SQLite database, at most 512 MiB. Required editorial tables and exact supported column order must be present. Known optional extension tables are allowed. Unknown tables, explicit custom indexes, views, virtual tables and triggers are rejected rather than silently ignored. SQLite quick structural integrity and foreign-key checks must pass. Schema support is deliberately version-bound; a future/modified schema can be rejected and may need an updated tool.

The check **does not** perform a complete semantic audit of every stored JSON blob, quotation, editorial judgment, source timestamp or historical statement. It does not authenticate people, validate news, establish that reported tasks actually ran, or prove the database was never altered. Output explicitly sets `semantic_validation: false` and `authenticity_verified: false`. A trusted backup can still contain inaccurate human input.

SQLite checks have progress-based deadlines; copying has a separate progress deadline and size check. These are failure controls, not a hard real-time guarantee against pathological operating systems/filesystems or hostile SQLite internals. Parent directories must be trusted. No extension loading is enabled, no network is contacted, no local source files are scanned, and no action description is executed.

The new CLI does not add an HTTP endpoint that downloads/restores the whole database. Only an explicit local command can invoke it. Exit 0 means the requested structural copy/check/restore completed; exit 2 means rejection or an operational failure. Errors do not echo database values or filesystem paths. Insufficient space, locked sources, unsupported schemas and unavailable destinations are not reported as successful backups.

## Privacy and storage

**The complete backup is not a sharing/anonymization format.** It contains source text, URLs, notes, claims, queries, observations, action history, event history and original registered local paths. A restore removes active watcher rows, but deletion is not forensic erasure: prior strings may remain in SQLite free pages. Neither backup nor restore redacts secrets, clears copyright restrictions or encrypts data. Review appropriate access before transferring or uploading any copy.

For a manually copied backup, stop all writers and account for SQLite journal/WAL files; the online CLI avoids the common mistake of copying only a live main file. Preserve an original backup until you have opened and reviewed the restored workspace. Each restored workspace is separate; it does not merge or overwrite another project.

## Verification

18 new public original synthetic tests, **161 total passed on Linux/Python 3.12, zero skips**. These include a fully populated watcher/radar/action/timeline workspace, live committed WAL changes while a writer connection remains open, concurrent transaction consistency, restored stale-basis behavior, unchanged originals, explicit acknowledgment, new-path refusal, structural/FK/schema rejection, FIFO/symlink refusal, simulated copy/publication failures and actual CLI commands.

No actual private workspace or credentials are included in fixtures. No network, new browser run, or Windows/macOS acceptance is claimed. The integrated workflow still has separately documented UI, scheduling, coverage and semantic-analysis gaps; reliable backup does not mark those themes complete.

Project-dossier extension: full backups also include `project_registry`, `project_runs` and `project_profiles`. The existing restore approval reset makes known profile bases need review; no project is fetched on restore. Editorial-only portable exports do not carry these extension tables. See PROJECT_DOSSIERS.md for observation and privacy boundaries.
