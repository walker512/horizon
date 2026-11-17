# Comparison: scope before claims

## Checked primary sources

- [TrendRadar](https://github.com/sansan0/TrendRadar), commit `86584f5544c66d4e22132f9b87c44a7ea3a32fea`, GPL-3.0. It offers multi-source aggregation, RSS, filtering, AI-assisted analysis and many delivery channels. Its parser preserves GUIDs and supports more feed formats than this prototype.
- [AIHOT](https://github.com/KKKKhazix/AIHOT), commit `04a3d427371b8e0373dea6a19e58f5e15bdb4e43`, MIT. It provides a configurable industry news pipeline and site. This evaluation read its repository and license; its full application was **not executed**.
- [FactCircuit](https://github.com/superwesleyhys-ux/factcircuit), commit `df0d8ce577c63a0e86ba06f3846fd316b785e1af`, MIT. It already preserves immutable source versions, exact evidence spans, source lineage, staged checks and correction/reanalysis. These are not novel Horizon features.

Checked 2026-11-17. Upstream repositories may change after these revisions. No upstream code is copied into Horizon.

## Executed comparisons

### FactCircuit offline quickstart and trace

The pinned upstream `python -m factcircuit quickstart` and `trace examples/local_trace.json` commands ran successfully, without model calls or live retrieval. Its fictional quickstart followed four material versions in three rounds to a correction, producing `contradicted` with located original material. Semantic annotations were hand-authored upstream; this is not an accuracy result.

The exact four supplied source texts and URLs from that run were then ingested into Horizon, in the same rounds. A manually linked initial headline was editorially approved. When the same source's correction arrived, Horizon preserved four snapshots and changed the prior approval to `needs-review`.

This is **not an accuracy comparison**: Horizon records editorial decisions while the upstream fixture contains semantic judgments. It demonstrates a working state transition and confirms that the central provenance/correction problem is already handled by a direct competitor. No Horizon superiority was observed.

### TrendRadar isolated feed parser

The pinned upstream parser, using feedparser 6.0.12, and Horizon's local importer processed the same synthetic RSS text. Both produced the expected title and article URL. TrendRadar also retained the supplied GUID; Horizon does not yet use feed GUID identity. This is a narrow parser check, not an execution of TrendRadar's whole application or a performance comparison.

## What remains unproven

- Whether a human editor completes the full source-update-to-corrected-brief task with less effort than an existing workflow.
- Whether provenance decisions and source changes are clearer in practice.
- Real-reader demand, adoption, GitHub growth, or superior accuracy.
- Full competitor desktop workflows, live-feed coverage and performance at scale.

Do not present this prototype as a better fact-checker, a replacement for TrendRadar, or an automatic fact verifier. Independent review and downloaded-package browser acceptance must precede any publication decision.

## Same-corpus editorial disposition replay

We reran FactCircuit's official offline quickstart and Horizon against the exact same four source URL/text versions from the upstream synthetic fixture. Both preserved all four versions. Horizon's four manually selected evidence links and FactCircuit's relation-basis spans matched the supplied source text.

FactCircuit's bundled, handwritten decomposer/verifier retained two explicit citation edges, a separate contradiction edge, an original-source finding, availability/cutoff fields and a final contradicted result. Horizon retains exact quotations, snapshots, manually declared common-origin grouping and editorial history, but does not provide equivalent typed lineage edges or evidence cutoff semantics. Its formatted local brief and editor interface serve a different workflow, not a proven better verifier.

The replay used 11 scripted Horizon mutation transactions and 3 exports, versus 1 official FactCircuit quickstart command. These numbers are **not comparable human operation counts**: they exclude input/adapter authoring and reuse upstream's prewritten semantic annotations. No human timing, usability study, accuracy advantage, or reduced-work claim follows.

The exercise found a concrete Horizon presentation gap: explicit withholding was obscured by the stale-evidence status. The revised display/export shows the editorial withholding decision separately while preserving stale warnings and blocking stale approval. A later material change marks the withholding as historical. This is a product fix, not evidence of superiority.
