# Evidence-linked intelligence event timeline

This extension turns reviewed source-backed claims into a **human-declared event timeline**, not merely a list of when Horizon saved documents. It connects an event's claimed time, exact editorial basis, source observation timestamps, later corrections and withdrawals. It does not discover events, authenticate announcements or infer chronology from article text.

It advances the open-source intelligence timeline topic in the existing Horizon repository. Automatic event extraction, semantic deduplication, broad-source ingestion and an interactive visual timeline remain unimplemented; the overall approved topic is not silently marked complete.

## Three different clocks

1. **Declared event window:** when a human says the event happened or is expected to happen. This may be an exact offset-bearing instant, a bounded interval, a whole calendar date/range in a named time zone, or unknown.
2. **Source observed/imported time:** timestamp attached to each captured immutable source snapshot. This is not authenticated publisher time, and imported histories can contain supplied timestamps.
3. **Recorded locally / updated locally:** when this event record was created or revised in Horizon.

None automatically substitutes for another. A source downloaded today can describe a future or earlier event. An unknown event time stays unknown, never receives a fabricated midnight. Future timestamps are allowed but are still human assertions, not verified schedules.

## Create and inspect

Use the existing editor to review a claim with its evidence and explicitly approve the wording. List claim IDs:

```sh
python -m horizon.actions --data-dir ./my-workspace claims
```

Create a declared event from `CLAIM_ID`:

```sh
python -m horizon.timeline --data-dir ./my-workspace create --claim CLAIM_ID --title "Declared launch window" --kind release --precision day --start 2026-05-24 --zone America/New_York --note "Source gives this date; the zone is my explicit interpretation, not automatically inferred"
python -m horizon.timeline --data-dir ./my-workspace list
python -m horizon.timeline --data-dir ./my-workspace export --format markdown --out event-timeline.md
```

Copy the returned event ID for history/detail:

```sh
python -m horizon.timeline --data-dir ./my-workspace show EVENT_ID
```

Categories are human labels: `release`, `policy`, `security`, `community`, `other`. The software does not classify events or validate that a claimed time occurs in a quotation. A current editorial approval is necessary to create/revise an event, but **it is not sufficient evidence that the event or time is true**. Read the underlying material yourself.

## Time input

- `--precision instant`: ISO timestamp with seconds and a known offset, such as `2026-05-24T09:00:00-04:00` or `2026-05-24T13:00:00Z`. Up to six fractional second digits are accepted. Omit `--end` for a single instant or provide an inclusive end instant for uncertainty/range. Naive timestamps are rejected. `-00:00` is not silently interpreted as known UTC; use a known offset or unknown precision. Do not also supply `--zone`.
- `--precision day`: strict `YYYY-MM-DD`, with an explicit IANA `--zone`. Omit `--end` for that one calendar date, or give an inclusive final date. Each date interval runs from local midnight through the instant just before the midnight after the final date, converted to UTC. DST days are not assumed to be 24 hours. A skipped/ambiguous midnight boundary is rejected; use a deliberately chosen offset-bearing interval instead.
- `--precision unknown`: omit start, end and zone. The event is retained in an unknown-time group and is not ordered relative to known events.

Supported declared years: 1900..2100. Calendar ranges span at most 3,660 days between first/last dates; instant intervals at most 3,661 days. Reversed/invalid ranges and unknown time zone names are rejected, never silently corrected. Named zones use Python `zoneinfo` and the installed IANA timezone database; if your system lacks that database, named-zone operations will fail rather than guess. This release was tested on Linux with that database present, not on Windows/macOS.

## Ordering and overlap

List/export sorts known windows by their earliest declared UTC boundary, then local record time/ID as deterministic tie-breakers. This **display order is not a claim of definite chronological order**.

Each active known-time event lists other active declared windows that could overlap, using inclusive boundaries. Two instant events at the same moment overlap; touching interval endpoints overlap. Adjacent calendar-day windows do not overlap merely because one ends immediately before the next begins. Unknown-time active IDs are listed separately and may occur anywhere; a label of `disjoint_among_known_active_windows` says nothing about those unknown events.

Withdrawn events remain visible, but are excluded from active overlap checks. Stale editorial-basis events also remain visible with warnings; comparing their declared windows does not revalidate them. No causal ordering, confidence score or probability distribution is inferred.

## Corrections and withdrawals

A source or editorial review change does not silently rewrite a recorded event. Its basis becomes `needs_review` while the captured wording, quotations and time remain inspectable.

After resolving and re-approving the claim in the normal editor, revise the complete event interpretation:

```sh
python -m horizon.timeline --data-dir ./my-workspace revise EVENT_ID --title "Corrected launch window" --kind release --precision instant --start 2026-05-25T13:00:00Z --note "Read the correction and explicitly replaced the previous date interpretation"
```

The revision captures the current editorial basis and retains the previous event fields/basis in history. `revise` also **explicitly restores a withdrawn event to active**; it is not a silent patch of a historical record. The CLI requires the full new title/category/time interpretation and a note. An unreviewed/stale/conflicted/withheld claim cannot be used as the new basis.

Withdraw without deleting history:

```sh
python -m horizon.timeline --data-dir ./my-workspace withdraw EVENT_ID --note "The claimed event is no longer suitable for this timeline"
```

Withdrawal is allowed with stale evidence. It does not prove the event false, approve a correction, or send any external message. No deletion or automatic restoration is performed.

## Data and sharing

The extension adds `intel_events` and `intel_event_history` tables to the existing SQLite workspace. Event changes/history commit atomically. Limits: 500 events; 100 linked quotations / 256 KiB final basis cap, including captured source observation timestamps; 10,000 history entries and 16 MiB combined serialized history details. Quota failures roll back the operation.

JSON timeline exports include source-derived quotations, URLs, human interpretation notes, declared windows, local timestamps, separate basis/status flags and overlap IDs. Markdown escapes supplied markup. `show` includes detailed revision/withdrawal history; overview exports include current captured event records and status, **not all revision-history entries**. Use a full database backup to retain complete history.

Existing portable editorial project JSON does **not** include timeline tables, local watchers, radar observations or action records. Timeline exports are readable artifacts, not import/restore packages. Stop server/CLI processes before a full SQLite filesystem backup. This explicit boundary prevents assuming that the original editorial export is a complete workspace migration.

Exports use UTF-8/LF, exclusive new files and a 32 MiB bound. A failed write can leave a partial file. Review every export for private/copyrighted source material before sharing. No redaction, signature, provenance authentication or fact verification is provided. Local database owners can alter history. This module performs no network requests, LLM calls, publishing, notification delivery or external task execution.

## Validation and alternatives

26 new original synthetic tests, combined with the prior 104: **130 tests passed on Linux/Python 3.12, zero skipped**. Tests include actual SQLite updates and CLI commands, exact offset normalization, 23/25-hour DST dates, skipped calendar dates, unknown/overlapping windows, retained source observation timestamps, stale basis, withdrawal/revision history, rollback and escaped exports. They are not real-event chronology validation or a new browser acceptance run. Existing browser/model/watch/radar/actions code remains unchanged.

[TimelineJS](https://github.com/NUKnightLab/TimelineJS3) already supports rich interactive storytelling timelines. Only its primary documentation was read; no runtime comparison, API interchange compatibility or superiority is claimed here. Horizon's implemented integration is a human-declared uncertain event window linked to its existing editorial evidence state, not a novel timeline algorithm or a replacement for rich visual authoring tools.

## Human-declared release/plan/report/rumor stages

Topic #4 called for distinguishing released material, plans, reporting and rumors, with corrections retained. Events now have a **separate editorial stage assessment**, rather than inferring occurrence from their category or date. The `kind=release` category alone still says nothing about whether an event happened.

```sh
python -m horizon.timeline --data-dir ./workspace assess EVENT_ID --stage planned --note 'The captured announcement describes a plan, not a shipped release.'
python -m horizon.timeline --data-dir ./workspace show EVENT_ID
python -m horizon.timeline --data-dir ./workspace list --topic 'model-release'
python -m horizon.timeline --data-dir ./workspace export --topic 'model-release' --format markdown --out ./topic-timeline.md
```

Stages are `released`, `planned`, `reported`, `rumor`, `unknown`. **Every stage is a human assertion, not automatic confirmation.** `reported` means the editor is classifying reporting; it does not certify the reported event happened. `rumor` is not a proof that a claim is false. A planned date passing never promotes an event. Source authenticity, contradictory sources and semantic evidence adequacy still require human review.

Assessment requires an active event with a current editor-approved evidence basis and a nonempty reason. Existing events default to `not_assessed` / unknown. Each assessment appends an immutable history entry with its reason, time, event fingerprint and prior assessment. Correct an assessment by issuing a new assessment; earlier labels/reasons remain available through `show`. The original event, time and evidence are not silently rewritten.

Changing or withholding the claim, revising its evidence, changing the event (even an identical explicit revision), withdrawing it, or restoring a backup makes the assessment need review. The output then retains `declared_stage` for historical transparency, but sets **`effective_stage: unknown`**. Markdown includes both values and a warning. Reopening a withdrawn event does not revive its old stage. First revise/review the actual event basis, then explicitly assess again. An assessment's `current_editorial_assessment` status only means its captured editorial basis still matches; `automatic_verification` remains false.

The assessment is stored in the existing bounded `intel_event_history`, so full workspace backup retains it without a schema migration. Editorial-only portable JSON still omits timeline/history. The prior history limits and transaction rollback apply. Do not manually modify historical fingerprints or treat them as signed evidence. Stage reasons and quoted evidence may be private; inspect exports before sharing.

`--topic` uses exact, nonempty **captured claim-topic** text, not today's possibly edited claim topic. Historical events therefore stay in their originally captured topic until explicitly revised. An omitted filter returns all events. The returned report discloses the filter; overlap checks are limited to the returned subset, not all workspace events. Unknown-time and historical ordering warnings remain intact. Reads of claims/events/assessments use one SQLite read transaction per `show`/`list` operation.

This is CLI and JSON/Markdown output. Existing service reads expose the additional assessment fields, but no new write API or frontend controls are provided. There is no new browser validation, automatic extraction, topic inference, semantic deduplication, rumor fact-checking or visual timeline. The added 17 original-synthetic tests cover all labels, correction history, source/review/event invalidation, withdrawal/reopening, topic filtering, escaping, rollback, backup restore and actual CLI commands. They do not establish the truth of real-world release reports.
