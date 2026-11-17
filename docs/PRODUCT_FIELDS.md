# Structured AI product observations

This is a human-reviewed evidence notebook for **input/output token prices, context windows, maximum output, license identifiers, request limits and token limits**. It adds typed values and explicit comparable scope to existing Horizon claims, instead of asking readers to infer which model/tier/unit a prose change refers to. It does not fetch these fields automatically, certify vendor claims, recommend a provider, calculate a task bill or interpret licenses.

## Why the schema is explicit

Original sources consulted while designing this increment:

- [Claude model overview](https://platform.claude.com/docs/en/models/overview) separates context window from maximum output and includes price qualifiers. Those are separate fields, not interchangeable capacities.
- [Claude pricing](https://platform.claude.com/docs/en/about-claude/pricing) distinguishes token categories, cache/batch conditions, serving platforms and regional modifiers. The observation must name its channel, region and conditions rather than treat all displayed prices as equivalent.
- [OpenAI rate-limit documentation](https://developers.openai.com/api/docs/guides/rate-limits) distinguishes model/account scope and request/token time windows. A public example does not establish an individual account's actual allowance.
- [Meta's Llama 3.3 license](https://huggingface.co/meta-llama/Llama-3.3-70B-Instruct/blob/main/LICENSE) has conditions beyond a short license name. A label comparison must not become a commercial-use or open-source compliance conclusion.

These are primary-source design references, not a bundled current-price dataset or a complete interpretation of the documents. They can change. No current provider numbers or copied license text are shipped in the example. Reading sources during development is not an automated adapter or real-user validation.

## Run a complete original-synthetic example

From the checkout:

```sh
python examples/structured_fields_demo.py --data-dir ./new-field-demo
python -m horizon.fields --data-dir ./new-field-demo list
```

The example refuses an existing directory. It creates a quoted synthetic price, approves its claim, records a typed observation, revises the source, and creates a second observation. `comparison.json` contains both source versions, exact quotes, recorded/import times, an exact decimal difference and an explicit stale historical basis warning. Nothing is fetched, no real price is asserted, and no external action is executed.

## Record your own reviewed field

1. Add an authorized source excerpt to Horizon, with URL, original-vs-relay classification and availability. Preserve context and units; do not copy private contracts into a publicly shared workspace.
2. Create a claim and link the relevant exact quote as **supports**. Review its wording and approve it explicitly. Approval is editorial, not automatic truth verification.
3. Save a JSON spec like this, replacing synthetic values and scope from the actual source:

```json
{
  "scope": {
    "provider": "Synthetic",
    "model": "model-v1",
    "channel": "direct",
    "region": "global",
    "tier": "standard",
    "conditions": "Uncached text input; synchronous base service"
  },
  "field": "price_input",
  "unit": "USD/million_tokens",
  "value": "2.50",
  "qualifier": "exact",
  "effective_date": "",
  "raw_value": "2.50",
  "note": "Human mapping of the selected quote; effective date not stated."
}
```

```sh
python -m horizon.fields --data-dir ./workspace add --claim-id CLAIM_ID --evidence-id EVIDENCE_ID --spec ./field.json
python -m horizon.fields --data-dir ./workspace show OBSERVATION_ID
python -m horizon.fields --data-dir ./workspace compare LEFT_ID RIGHT_ID --out ./comparison.json
python -m horizon.fields --data-dir ./workspace withdraw OBSERVATION_ID --note 'Wrong scope; see replacement observation'
```

Use `null` for an **unknown scope dimension**, not the word "unknown". Every scope key is mandatory. Comparison will not calculate a delta when any scope dimension is null. Otherwise scope strings are compared exactly, with no inferred equivalence or normalization; misleading user labels are not detected.

### Fields and units

| Field | Unit | Value |
|---|---|---|
| `price_input`, `price_output` | `USD/million_tokens` or `EUR/million_tokens` | Decimal **string**, up to 9 integer and 6 fractional digits |
| `context_window`, `max_output` | `tokens` | Integer 0..1,000,000,000,000 |
| `request_limit` | `requests/minute` or `requests/day` | Integer in the same bound |
| `token_limit` | `tokens/minute` or `tokens/day` | Integer in the same bound |
| `license` | `identifier` | Bounded human-entered label, not a legal permission |

No currency conversion, token-denominator conversion, unlimited sentinel or other billing categories are provided. Convert quantities only after human review, explaining the normalization in `note`. `raw_value` must appear literally in the selected supporting quote; this substring check **does not prove the numeric conversion, model match, qualifier, scope or date is semantically correct**.

`qualifier` is `exact`, `from`, `up_to`, or `unknown`. Unknown requires `value: null` and an empty raw value. A missing account-specific allowance should be unknown, never an invented zero. Non-exact observations produce no numeric delta; a license label only supports exact/unknown. `effective_date` is an explicit human declaration or empty for unknown. The program does not equate it to the recorded time, order observations by it, or determine if it is already in force.

## History and comparison guarantees

Observations are immutable; corrections require a new observation and optional withdrawal of the old one. Withdrawal is retained and suppresses comparison, not a deletion. Captured evidence retains source URL/title/kind, exact quote, snapshot ID and local snapshot creation/import time. The last timestamp is **not certified publisher time**. Current basis is checked against the claim's present editorial review and evidence; a later change/withholding/review reset shows `needs_review` without rewriting the old record.

Comparison reads both records in one SQLite read transaction. Both full historical records are returned. Different field/unit/scope, unknown scope, unknown or qualified values, and withdrawn records produce no numeric difference. Exact declared numbers use decimal arithmetic (`right - left`), not binary floats. Old stale observations may still yield a **historical arithmetic difference** but set `review_required: true`; that is not approval of current correctness. `mapping_requires_human_review` is always true, independently of the editorial-basis flag. No percent forecast, ranking, chronology or affected-user inference is generated. A license-label change carries no compatibility/compliance conclusion.

The CLI returns 0 for a completed command even when a comparison is incomparable, historical or withdrawn. Consumers must inspect the structured status. Exit 2 indicates controlled input/storage/output failure. Existing output files are never overwritten.

## Persistence, limits and privacy

500 observations; 256 KiB captured basis each; 32 MiB total basis/spec storage; comparison JSON limited to 4 MiB. Standard regular non-symlink UTF-8 spec-file limits apply, and duplicate JSON keys are rejected. Mutations and their audit entry are transactional. Full-workspace backups include the new table; restoring a backup resets approvals so restored observations need review. **Older Horizon versions do not know the new table and reject those full backups.** Editorial-only portable JSON omits observations; use full backup for them.

Output contains supplied model/account scope, notes, exact quoted excerpts and source URLs. It is neither anonymous nor safe to publish without inspection. There is no network, deployment, account lookup, credential scan or private contract discovery in this module. New frontend forms and a graphical comparison have not been implemented or tested.

## Scope and validation

204 public tests pass locally, including 21 new synthetic tests of scope/unit mismatch, unknown/from bounds, exact decimals, quotes, historical invalidation, withdrawal, rollback, full-backup restoration and actual CLI operations. The included synthetic end-to-end demo was run separately. No new Windows/macOS/browser test or real-account limit measurement was performed.

This partially fills original topic #3's structured evidence and historical comparison requirements. Automated extraction, multi-vendor catalogue maintenance, confirmed effective-date detection, user-specific impact analysis and scheduled notifications remain missing. Existing monitoring/catalogue products may already cover related functions; no head-to-head superiority is claimed.
