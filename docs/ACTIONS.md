# From reviewed information to a human action plan

This extension links an actionable plan to the **exact editorial basis** that motivated it. It is a substantive local planning/progress workflow for the news-to-action direction, not an autonomous assistant or a claim that the entire approved theme is complete.

Horizon does not tell you what decision to make, infer your goals, perform a task, send a message or certify that your checklist was actually completed. All titles, reasons, steps, ownership labels, dates and progress notes are human supplied. “Editor-approved” is a human editorial state, not a truth guarantee.

## Workflow

Start with source material and a claim in the normal Horizon editor. Read the passages, resolve stale/conflicting links, and explicitly approve the wording. A summary from GitHub Radar can be a starting source, but it is not automatically a supported/approved action basis.

List claim IDs and editorial states:

```sh
python -m horizon.actions --data-dir ./my-workspace claims
```

Choose an `editor-approved` claim and copy its ID as `CLAIM_ID`:

```sh
python -m horizon.actions --data-dir ./my-workspace create --claim CLAIM_ID --title "Evaluate the new offline option" --why "Check whether it fits our existing workflow before adopting it" --step "Read the release limitations" --step "Try an authorized local synthetic case" --owner "Me" --due 2026-12-01
python -m horizon.actions --data-dir ./my-workspace list
```

Creation returns an `action_id`; use it in place of `ACTION_ID`:

```sh
python -m horizon.actions --data-dir ./my-workspace status ACTION_ID active --note "Starting an evaluation, not a production rollout"
python -m horizon.actions --data-dir ./my-workspace check ACTION_ID 0 --done yes --note "Read the limitations"
python -m horizon.actions --data-dir ./my-workspace check ACTION_ID 1 --done yes --note "Recorded the local test outcome separately"
python -m horizon.actions --data-dir ./my-workspace status ACTION_ID done --note "Human reports the evaluation complete"
python -m horizon.actions --data-dir ./my-workspace show ACTION_ID
python -m horizon.actions --data-dir ./my-workspace export ACTION_ID --format markdown --out action-review.md
```

Indices are zero-based and displayed in exports. `--done no` can reopen a checklist item while an action is not closed. All progress is self-reported. A task described as “email a colleague” is still just text: no email is sent. Dates are plain `YYYY-MM-DD` calendar labels, not time-zone scheduling, automatic overdue alarms or future commitments by the software.

## State and basis are separate

Action states: `planned`, `active`, `blocked`, `done`, `cancelled`. Every transition requires a human note.

- Creating an action requires a currently editor-approved claim. Missing support, conflicting evidence, unreviewed/withheld wording or stale evidence is not eligible.
- The captured basis includes claim wording/topic/signatures/review time/note and exact linked evidence quotations, source versions and metadata. It is a historical editorial basis, not proof of external truth.
- Current basis status is computed against the live claim on every read/transition. Changes to wording, evidence, metadata, source versions or editorial review can yield `needs_review`. A later edit back to old wording does not resurrect the prior approval; the existing persistent invalidation rules remain in force.
- Marking `done` requires every checklist item checked and the captured basis still matching the current editor-approved claim. Refusal is atomic: the action/history are not partially changed.
- A previously completed action remains `done` after the source changes, **but its basis becomes `needs_review`**. Reports warn that historical completion is not revalidated. The tool does not rewrite history, undo a real-world action or automatically perform it again.
- Closed (`done`/`cancelled`) actions cannot have their checklist/plan/basis edited. Explicitly set `planned` with a reopening note first. Cancellation is allowed when the basis is stale; it does not approve the source.

When the source changes, first resolve the claim in the ordinary editor: read new text, revise wording, relink current passages, and make a fresh human editorial decision. Then review the action basis:

```sh
python -m horizon.actions --data-dir ./my-workspace review-basis ACTION_ID --note "Read the revised evidence and confirmed this plan remains appropriate"
```

This command refuses a claim that is still unreviewed/stale/conflicted. When the basis changes it preserves the previous basis/checklist in history and **resets all checklist completion flags**, requiring fresh explicit checks before closing. If the basis is unchanged, progress is preserved. Closed actions must be reopened first. A fresh editorial approval with a different review time/note also requires this action review; the system does not assume that repeated approval is interchangeable with the earlier decision.

## Editing the plan

```sh
python -m horizon.actions --data-dir ./my-workspace edit ACTION_ID --title "Evaluate a narrower use case" --why "Clarified the decision we need" --owner "Me" --due 2026-12-02 --note "Adjusted plan wording"
```

This replaces the supplied plan metadata, recording old and new values. It does not change checklist text, automatically uncheck progress, or certify that old work meets a new scope. If the required work changes, explicitly uncheck the relevant steps or create a new action with the correct checklist. The software cannot judge semantic equivalence of plans. Omitted owner/due options on `edit` clear those fields, as shown by the command defaults.

`list` shows title, rationale, owner, due date, progress, action state and separate basis status without duplicating captured quotations. `show` includes the captured basis and full operation history. Nothing is hidden because it was cancelled, withheld later, or needs review.

## Storage, limits and exports

Two new SQLite tables hold actions and event history; the existing model, browser routes and browser files are unchanged. Changes to an action and its history event commit in one transaction. Limits: 500 actions, 1..20 checklist steps per action, 100 evidence links / 256 KiB per captured basis, 10,000 history events / 16 MiB total serialized event details. A limit failure rolls back that operation rather than silently losing history. Input title/rationale/step/note lengths are bounded. No deletion command or automatic purge is provided.

Action JSON/Markdown exports contain your plan, notes, captured quotations/URLs, current claim status and historical records. They are not anonymized or signed. Review privacy and copyright before sharing. Markdown escapes supplied markup; no tool executes those instructions or sends its URLs to an external service. Files use explicit UTF-8/LF bytes, a 16 MiB export limit and exclusive creation; a disk failure can leave a partial new file. Existing files are never overwritten.

**Important backup boundary:** the browser's existing portable Horizon project JSON does not include action tables, just as it does not include machine-local watchers or radar history. Action exports are readable review records, not an import/restore format. A complete SQLite backup (made while server/CLI are stopped) retains actions and history. Importing a portable editorial project into another workspace will not reconstruct your actions. This limitation is explicit rather than silently labelling the editorial export a full-workspace backup.

Hashes compare captured state; they do not authenticate people, real-world execution or source origin. Anyone controlling the local database can alter records. Do not treat a green basis/completed checkbox as an audit certification or approval for high-impact external actions.

## Validation and remaining scope

23 new public synthetic tests plus the prior 81 tests: **104 passed on Linux/Python 3.12, zero skips**. Tests cover actual database lifecycle, no stale completion, persistent historical warnings, source edit/restore, fresh-approval action review, changed-basis checklist reset, cancellation/reopen, transaction rollback, restart, metadata editing, export escaping and actual CLI. Fixtures are fictional; there was no real task delegation, production agent execution, real-user study or new browser acceptance.

This version still lacks automatic news-to-goal matching, semantic action suggestions, external task-system synchronization, reminders and an interactive action-planning UI. These are remaining coverage gaps, not implemented features. Topics #2–5 remain individually tracked; one integrated repository does not make all their requirements complete. Existing task systems can offer richer collaboration and automation; no competitor runtime or superiority claim is made for this increment.
