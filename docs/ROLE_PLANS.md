# From evidence to a role-specific review plan

Horizon can now prepare a concrete developer/researcher review checklist from an approved claim instead of requiring the editor to start with a blank action form. The planner is **deterministic and transparent**, not an AI model call. It does not understand sources, identify missing facts automatically, infer your profession or execute the suggested work.

## Try the whole workflow

```sh
# Original synthetic fixture, new directory required; draft only:
python examples/role_plan_demo.py --data-dir ./developer-demo
# A separate example explicitly adopts a researcher draft into local Actions:
python examples/role_plan_demo.py --data-dir ./researcher-demo --role researcher --adopt
python -m horizon.actions --data-dir ./researcher-demo list
```

Neither command executes a task or sends a message. The first creates no action. The second creates one `planned` action with all steps unchecked, a synthetic owner, and the captured evidence basis. Existing progress, completion, changed-source blocking, reopening and re-review remain the normal Actions workflow.

## Use your own reviewed claim

1. Capture an authorized source, link exact passages to a claim and make an explicit editorial review. Approval is not an automatic factual verdict.
2. Find its ID and inspect its current quoted evidence:

```sh
python -m horizon.actions --data-dir ./workspace claims
python -m horizon.plans --data-dir ./workspace evidence CLAIM_ID
```

3. Save a spec with exactly these keys. Empty lists are deliberate missing-reference markers, not assertions that no such material exists anywhere:

```json
{
  "role": "developer",
  "claim_id": "CLAIM_ID",
  "slots": {
    "official_docs": [],
    "pricing": [],
    "code_example": [],
    "compatibility": []
  },
  "interpretations": [
    "This announcement might warrant a migration experiment; that is my unverified interpretation."
  ]
}
```

Replace a slot's empty list with one or more evidence IDs from the selected claim if you have chosen relevant quotations. A researcher spec instead uses `dataset`, `code`, `experiment_design`, and `limitations`. Every role slot is mandatory; each accepts up to five distinct evidence IDs. The same quotation may be explicitly used in several slots, but that does not make it several independent sources. Up to five unverified interpretations of 300 characters each are supported.

4. Prepare, read, and only then explicitly adopt:

```sh
python -m horizon.plans --data-dir ./workspace draft --spec ./role-spec.json --out ./role-draft.json
# Inspect the JSON's captured_basis, role_slots, unverified_interpretations and proposal.
python -m horizon.plans --data-dir ./workspace adopt --draft ./role-draft.json --owner 'Your chosen owner' --due 2027-01-01
```

The due date is optional and is not a scheduled reminder. Draft generation never creates an action. Adoption writes only a local planned checklist; all steps begin unchecked. Adoption is **not idempotent**: invoking it again can create a second plan, so inspect Actions after an uncertain result instead of blindly retrying. The command reports the created action ID.

## What the columns mean

- `captured_basis` contains the existing editorial claim, its review state and the exact evidence quotes/source references. These are **quoted claims and editorial decisions**, not machine-certified facts.
- `role_slots` are human classifications. A selected reference is labelled `referenced_not_semantically_verified`, even if it really is the wrong document. References may be supporting, refuting or contextual; their original relations remain visible. No slot automatically becomes “verified.”
- Empty slots are `missing_reference`. They generate a concrete suggestion to find/link a relevant authorized source before deciding. They do not claim the source does not exist.
- `unverified_interpretations` is a separate list of human-entered reasoning. The planner never upgrades those sentences to approved facts or invents supporting citations.
- `proposal.steps` are static role prompts: developers review docs, billing conditions, code and compatibility; researchers review data, code, experiment design and limitations. A final prompt asks for unresolved questions and an explicit proceed/defer/stop decision. These suggestions are not executed, personalized guarantees or evidence that the work was completed.

Editing the raw proposed checklist or labels in a saved draft makes adoption fail. Change the explicit spec and regenerate a new draft if needed. After adoption, use the existing Actions controls; checklist-text changes require a new plan under the existing Actions contract. A recomputable draft is **not a cryptographic signature or trusted instruction channel**. An attacker who can edit both a spec and matching draft can create a consistent new proposal; review untrusted files, and do not treat this consistency check as authorization for external work.

## Staleness and atomic adoption

Adoption recomputes the draft from its declared inputs and the current evidence/template. Exact typed JSON comparison rejects altered content, labels, template versions and boolean/float substitutions. Changed/withheld/edited evidence requires regenerating and reviewing the plan.

There is also a second captured-basis check **inside Actions' write transaction**. A source/review change between draft revalidation and insertion therefore rejects the adoption instead of recording a plan under a different basis. Action insertion and its history are still atomic. Already adopted actions retain their history when evidence later changes: current completion is blocked until re-review, and historical done remains done with a warning. No historical work is silently erased or recertified.

All steps are local. There is no network, credential lookup, LLM call, deployment, code execution, email, external task synchronization, reminder or automated inference in this increment. It adds no HTTP operation or frontend form.

## Bounds, privacy and portability

Drafts are bounded to 500,000 ASCII-serialized characters/bytes so a successfully written draft fits the regular-file reader's input bound. The underlying 256 KiB evidence-basis, Actions rationale/checklist/storage limits also apply. Oversized drafts/rationales are rejected before an output is created. Draft output must be a new file, never an overwrite. Duplicate JSON keys, special files and symlink spec/draft leaves are rejected by existing shared readers/parsers. Directories/filesystem parents remain trusted, not a hostile-file sandbox.

Drafts and adopted action rationale contain source excerpts, evidence IDs, owner choices and human interpretations. They are not anonymized. Keep unneeded private speculation out of shared exports. Full workspace backup preserves adopted actions; it does not automatically include separately saved draft files. Restoring a workspace resets approvals, so an old draft cannot be adopted without renewed evidence review and regeneration. Editorial-only portable JSON does not include Actions, as before.

## Verification and remaining gaps

257 public tests pass locally on Linux/Python 3.12, zero skips, including 16 new tests of both roles, no implicit action creation, typed draft tampering, late-change race rejection, stale evidence, unknown links, bounds, backup reset and actual CLI evidence/draft/adopt operations. Both public demo modes were run separately. No fresh browser/cross-platform or real-user effectiveness study was performed.

This partially fills original topic #5's role-specific actionable checklist and quote-versus-interpretation separation. Automatic role-aware reasoning, semantic source extraction, generated personalized recommendations, external task delivery and reminders remain missing. It is not presented as a superior AI planner or a complete replacement for those workflows.
