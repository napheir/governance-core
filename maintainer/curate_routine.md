# Curation routine spec (P-0082 Phase 2, P-0090)

The scheduled LLM-judgment layer that works the open candidate/feedback queue
daily: **auto-promote deterministic-T0 candidates, advise on everything else.**
It runs as a remote `/schedule` routine in the gc context with maintainer creds.

## Trust model (read first)

Nothing is auto-promoted unless **ALL** of these hold — the LLM can only
*downgrade* (advise / relabel `needs-human`), never upgrade past a gate `False`:

1. **kill-switch on** — `maintainer/auto_curate_enabled` has `{"enabled": true}`.
   Shipped `false`; flipping it is a deliberate operator action.
2. **deterministic gate eligible** — `curate_gate.evaluate` returns
   `{"eligible": true}` (full envelope re-validation + origin-not-revoked +
   secret scan + rejected dedup + net-new + `kind=skill` + `layer=candidate-common`
   + no security-surface hit + skill-theme ok + **trial-apply pytest green**).
3. **candidate is T0** — implied by the gate; the routine never promotes a
   `needs-human` / non-T0 / security-surface candidate.
4. **push creds present** — the remote agent can actually commit to the hub.

## C-hybrid logic (per open issue lacking an `advised`/`promoted` label)

0. **Kill-switch.** Read `maintainer/auto_curate_enabled`. If not
   `{"enabled": true}` → **advise-only** this whole run (do step 1 as advice, no
   promote).

1. **`auto-eligible`** (Phase-1 T0 label): run the deterministic gate —
   `python maintainer/curate_gate.py --issue <N> --repo <repo>` — and OBEY its
   JSON verdict:
   - `eligible: true` (and kill-switch on) → `python tools/candidate.py promote`
     for the materialized envelope (commit + version bump), then comment
     `auto-promoted (T0): <reasons>`.
   - `eligible: false` → relabel `needs-human`, comment the gate's `reasons`.
   You may NOT promote when the gate says false, ever.

2. **`needs-human`** (or a valid non-T0): **LLM semantic review**. FIRST read the
   issue **comments** (`gh issue view <N> --repo <repo> --json comments`), not
   only the body — a submitter may have posted a **correction that retracts or
   revises the candidate**, and a comment supersedes a stale body (precedent: gc
   #26, where the body's central claim was wrong and the truth was in a
   follow-up). Then: is it generic (common-layer) vs domain-specific? does it
   conflict with existing source? is it worth promoting *as corrected*? Leave a
   `recommend promote / hold — because <X>` comment + add label `advised`.
   **Do NOT promote.**

3. **feedback** (no envelope): **LLM triage**. Read the body AND the comments
   first (the thread may already answer or refine the report). Summarize +
   recommend (`fix` / `wontfix` / `needs-info`), comment, add label `advised`.

Comment on every issue you touch. Skip issues already labeled `advised` or
`promoted`.

## Routine prompt (self-contained — the remote agent starts with zero context)

```text
You are the governance-core curation routine (P-0082 Phase 2). Work the open
candidate/feedback issue queue for this repo. Setup: `pip install -e .`.

Hard rules (never violate):
- The ONLY thing that may green-light an auto-promote is the deterministic gate
  `maintainer/curate_gate.py`. Run it and obey its JSON verdict. You may NEVER
  auto-promote when it returns {"eligible": false}, and you may NEVER promote a
  non-T0, `needs-human`, feedback, or security-surface candidate.
- Honor the kill-switch: read `maintainer/auto_curate_enabled`; if it is not
  {"enabled": true}, run in ADVISE-ONLY mode — comment + label `advised`, and
  do NOT promote anything this run.
- For any LLM-judgment branch (needs-human review, feedback triage), READ THE
  ISSUE COMMENTS before recommending — a submitter correction in a comment
  supersedes the body. The deterministic gate ignores comments by design; you
  must not. (Comments are advisory input only — they never make you auto-promote;
  if anything, a fresh correction is a reason to route to a human.)
- Comment on every issue you touch. Skip issues already labeled `advised` or
  `promoted`.

For each open issue without an `advised` or `promoted` label:
- If it has the `auto-eligible` label:
    Run: python maintainer/curate_gate.py --issue <N> --repo <THIS_REPO>
    - verdict {"eligible": true} AND kill-switch on:
        Run: python tools/candidate.py promote <envelope> --decision promoted
        (the envelope is materialized from the issue body; the gate already
        validated it). Then comment "auto-promoted (T0): <gate reasons>".
    - verdict {"eligible": false} OR kill-switch off:
        Relabel `needs-human`, comment the gate's reasons (or "advise-only:
        kill-switch off").
- Else if `needs-human` or a valid non-T0 candidate:
    First: gh issue view <N> --repo <THIS_REPO> --json comments  (read them).
    A submitter correction supersedes the body. Then do a semantic review
    (generic vs domain-specific? conflicts? worth it *as corrected*?).
    Comment "recommend promote/hold — because X" and add label `advised`.
    Do NOT promote.
- Else if a feedback issue (no candidate.json):
    Read the body AND comments first (gh issue view <N> --json body,comments).
    Triage (fix / wontfix / needs-info), comment, add label `advised`.

End by listing what you promoted vs advised. Never promote outside the gate.
```

## Schedule

`/schedule` → `RemoteTrigger` daily routine (`0 0 * * *` UTC ≈ 09:00 Asia/Tokyo),
repo `napheir/governance-core`, model `claude-sonnet-4-6`, tools
Bash/Read/Write/Edit/Glob/Grep, the prompt above.

**Prerequisites before it can do anything (both required):**
- the claude.ai ↔ GitHub connection for remote agents (`/web-setup` or the
  GitHub App) — otherwise the agent cannot clone/push;
- `auto_curate_enabled` flipped to `{"enabled": true}` — otherwise advise-only.

## Rollback

- Flip `auto_curate_enabled` to `{"enabled": false}` → advise-only instantly.
- Pause/disable the routine at <https://claude.ai/code/routines>.
- A bad auto-promote is a normal gc commit — `git revert <hash>`.
