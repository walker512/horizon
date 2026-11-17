# Community observations beside GitHub discovery

The original early-discovery topic included HN/developer communities, not just stars. This increment observes the **official Hacker News API**, links explicitly matching GitHub repository URLs to the existing Radar's current returned page, and lets an editor import selected discussion metadata as a quoted source. It does not crawl other communities or determine which project is good, novel or likely to gain stars.

## Run the complete path

```sh
# Explicit network consent. Only first 10 IDs in the Show HN feed are inspected.
python -m horizon.community --data-dir ./workspace --feed show --sample-size 10 collect --allow-network
python -m horizon.community --data-dir ./workspace --feed show --sample-size 10 review
# Use an already collected GitHub Radar query ID:
python -m horizon.community --data-dir ./workspace --feed show --sample-size 10 associate GITHUB_QUERY_ID
# Choose a returned HN item yourself:
python -m horizon.community --data-dir ./workspace --feed show --sample-size 10 import HN_ITEM_ID
```

The existing GitHub flow remains `python -m horizon.radar --data-dir ./workspace add/collect/review/import`; see GITHUB_RADAR.md. Both inputs need a successful latest local observation for association. Imported HN records appear in the same editorial source desk. They can be quoted, linked to a claim, reviewed and used in an action or timeline just like other source summaries. Import does **not** approve a claim or follow the linked page.

Global options precede the command. Feed choices are `new`, `top`, `show`; sample size is 1..20. An optional `--keyword` is a case-insensitive substring filter on the **already fetched prefix's titles**, not full-text, semantic or global HN search. It is not sent to HN. Feed, sample size and keyword together identify a local observation stream; changing them does not silently mix histories.

## Coverage and failures

The list response is bounded to 1,000 IDs, and at most the requested first N are inspected, preserving API list order. The report includes returned list size, selected IDs, inspected count, explicit null/deleted/dead/non-story exclusions and title nonmatches. A request/validation failure in any selected item makes the entire new attempt failed, with **no partial candidates**; previous imported source snapshots remain historical. Failed latest observations block new imports and association rather than presenting an old page as fresh. Recovery requires another explicit successful collect, never a retry behind your back.

The feed and items are fetched sequentially. They are **not an atomic remote snapshot**. Missing from a later prefix is not deletion or loss of popularity. First seen means first seen in this local stream, not first published, first discovered on HN, or global project birth. API-provided creation Unix time is kept separate from the local observation timestamp. A score delta compares actual observations of that item, including a reappearance; there is no time-normalized growth forecast. Missing score/comment counts are null, never invented zero.

The upstream interface and item semantics are documented by the [official Hacker News API project](https://github.com/HackerNews/API). Story titles can contain HTML; they are stored as data, not executed by this command. Comment trees, story body HTML, usernames and linked article/repository contents are not fetched or stored. API title/score metadata does not establish the truth of the story.

## Repository association is deliberately narrow

A match requires an explicit `https://github.com/OWNER/REPO` link, optionally with a trailing slash. Matching is case-insensitive against a repository full name in the successful latest GitHub query page. Credentials, explicit ports, query strings, fragments and extra path segments are not normalized into a match. Rename/redirect/shortener resolution and `.git` suffix inference are not performed. Associations show the GitHub repository ID, HN item ID and both observation timestamps. The two local reviews are read separately, not a single cross-module frozen snapshot.

This is URL association only, **not independent corroboration**. A project owner can submit their own announcement, or a post can relay the same source. Imported HN metadata is classified `relay`, availability `summary`, with origin group empty/unknown. The editor must establish a common origin before asserting independence. Raw response SHA-256 values are diagnostic only: raw API bytes are not retained, so hashes cannot be recomputed from the projected fields and do not authenticate provenance.

Imports capture the selected metadata observation, not a continuously synced source. Later collection alone does not rewrite the imported source or its claims. Re-import the selected current item to create a new source snapshot and trigger the existing linked-review invalidation, or explicitly record unavailable context yourself. Historical quotes about a past observation do not become current-event confirmations. Imported summaries and exported reports can contain public URLs, title text and editor-supplied labels; inspect before sharing.

## Network, persistence and limits

Each collect requires boolean consent (`--allow-network` in the CLI). It requests only fixed paths under `https://hacker-news.firebaseio.com/v0/`: one selected feed list and at most 20 numeric item paths. No user URL, browser, cookies, credentials, JavaScript, redirects, linked-content requests, retries, background collection or challenge solving. Normal TLS verification and the host's ordinary proxy configuration apply; do not use proxies to bypass a restriction.

Each response is limited to 1 MiB, with strict JSON projection, duplicate-key rejection and HTTP framing/declared-length checks. A 10-second socket timeout and 20-second checked read deadline apply per response; the item loop checks a 90-second budget between requests. These are not OS/DNS hard time limits, and a final in-flight request can extend the loop deadline. No Content-Length means an origin-intended total cannot be proven. Unexpected/broken responses fail with a fixed non-echoing message.

200 attempts per workspace, including failures. Full backups retain the new `community_runs` table. Older Horizon backup checkers do not know that table and reject it; use this version or later. Editorial portable JSON does not contain collection history, only separately imported editorial source snapshots. Restoring a full backup resets editorial approvals but retains historical feed observations; restore does not perform a fresh network request.

Exit 0 means the operation completed, including an empty bounded result; 3 means a collection attempt was recorded failed; 2 means input/consent/storage error. `review` can return historical observation metadata: inspect its timestamps and status instead of treating a green process exit as fresh remote data. There is no new HTTP writer or browser interface.

## What was actually exercised

The development collector made one ordinary live `new`-feed observation with sample size 1: the list returned 500 IDs, and one story metadata record was inspected. That item had no matching GitHub repository link. Its article was **not** opened, and its headline was not fact-checked. Live observations stay private and are not shipped as reusable truth fixtures. No real cross-source association, real score-growth sequence, or real user adoption is claimed.

The 20 new public tests use original synthetic API payloads and exercise bounded collection, omission/failure handling, strict projection, no-consent refusal, stream separation, score differences, exact repository association, imported quote linking, full backup/restore, actual CLI operations, and real `HTTPResponse` framing over synthetic bytes. Together with the existing suite, 241 tests passed locally on Linux/Python 3.12. No new browser/Windows/macOS run or same-input superiority comparison. Coverage of other developer communities, automatic problem/competitor/onboarding analysis and global early discovery remains missing.
