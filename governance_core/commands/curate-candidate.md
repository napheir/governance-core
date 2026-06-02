---
theme: universal
owner: core
---

# /curate-candidate - Hub-side candidate curation

Curate incoming candidates (skills / hooks / mechanisms / drift) into the
package source, or reject them with advice. The **hub-side counterpart** to
`/submit-candidate` (P-0065). This skill orchestrates the existing tools and
governance flow; it does **not** reimplement them.

> **Hub gate** — this skill is for the convergence hub (the project whose
> `.governance/config.json` `authorization.consumer_id` is `governance-core`).
> A consumer offers capabilities with `/submit-candidate`; the hub curates them
> here.

## When to use

- `candidate-reminder` (SessionStart) or a maintainer notes open `candidate`
  issues / staged envelopes.
- The owner asks to review or promote a contributed capability.

## Authoritative sources (this skill points; it does not restate)

| Concern | Source of truth |
|---|---|
| pipeline overview + CLI | `docs/core-manual.md` §11 + `tools/candidate.py` |
| reject-with-advisory | `maintainer/reject_candidate.py` |
| generic vs domain-specific | `.claude/skills/lesson-classification.md` |
| hook import rules | `knowledge/governance/runtime-import-discipline.md` |
| capability change governance | `/proposal` skill (classify → … → archive) |
| package/autonomy separation | Constitution Art.11 |

## Workflow

### 1. Review

```bash
python tools/candidate.py review
```
Lists local `candidates/` envelopes + open GitHub `candidate` issues, with each
candidate's prior decision (if any).

### 2. Classify each candidate

- **Layer** — generic common-layer vs consumer-domain-specific. Use the
  `lesson-classification` axis. Domain-coupled payloads are rejected (the
  generic *kernel* may be invited back as a rewrite).
- **Net-new vs already-in-source** — compare against `governance_core/`.
- **Completeness** — are *all* referenced payloads attached? An incomplete
  bundle (a hook whose config/helper/tests were never uploaded) is **not
  promotable**: comment requesting the rest and keep the issue OPEN.
- **Topology** — multi-clone-only pieces (e.g. `sync_infra` distribution wiring)
  are N/A for a single-agent hub; exclude them.

### 3. Verify BEFORE applying

- Fetch the issue body **and its comments** (`gh issue view <N> --json
  body,comments`); extract `candidate.json` + payload(s) from the body. **Read
  the comments before acting** — a submitter may have posted a correction that
  retracts or revises the candidate, and a comment supersedes a stale body
  (precedent: gc #26 — the body's central claim was wrong; the truth was in a
  follow-up. Promote the *corrected* kernel, not the retracted body). The
  deterministic auto-promote gate reads body-only by design; the comment is
  LLM-judgment input only.
- **Drift candidates** carry `baseline_sha256`. Compare it to the *current*
  package source (`sha256sum governance_core/<target>`):
  - **equal** → the payload applies cleanly.
  - **drifted** → do NOT trust stale line numbers. Apply a diff with
    `git apply -p1 --recount` (re-locates hunks by context). For a full-file
    payload, get the true delta with
    `git diff --no-index --ignore-cr-at-eol <current> <payload>` — most
    "drift" is just CRLF-vs-LF noise and the real change is pure-add.
- **De-trade-ify** — if the mechanism is generic but examples leak a consumer's
  domain (paths, tickers, internal proposal ids), genericize the examples before
  shipping. The mechanism stays verbatim; only illustrations change.

### 4. Apply to the package source

Edit `governance_core/` **only** — never the root autonomy-layer copy (Art.11.2).
`candidate.py promote` auto-places `skill`/`hook` kinds; a `mechanism` is placed
by hand.

### 5. Wire it in (capability-specific)

- **New hook** → add it to `governance_core/hooks/hooks_manifest.json`
  (installer regenerates `settings.local.json`; doctor flags an unregistered
  hook). Honor `runtime-import-discipline.md`: a fail-closed per-call gate must
  be self-contained; any other `governance_core` importer must guard the import
  and fail open.
- **New non-`.py` data file** (`.json`, or `.md` outside an already-globbed dir)
  → add it to `pyproject.toml` `[tool.setuptools.package-data]`, **or it silently
  drops from the wheel**. The editable install masks this — only the wheel-content
  check (step 6) catches it.

### 6. Validate (dogfood discipline)

- Bump the version (the change ships to consumers via `upgrade`).
- Run the test suite (`tools/test_*.py`); add a test for net-new code.
- `governance-core upgrade --project-root .` then `governance-core doctor`
  (exit 0).
- **Wheel isolation**: `python -m build --wheel`, then assert the wheel's
  top-level is only `governance_core*` (+ dist-info), the new files are present,
  and `maintainer/` did not leak (Art.11.4).

### 7. Record the curation decision

```bash
# promote (place mechanism payloads by hand first, then record):
python tools/candidate.py promote <envelope-dir> --decision promoted --note "..."
# reject with consumer-visible advice + close the issue:
python maintainer/reject_candidate.py --issue N --reason "..." --advice "..." --also-close
```
Decisions are written to `maintainer/consumer_registry.json` /
`governance_core/candidates/rejected_registry.json` (committed ledgers).

### 8. Formalize + close

- A promotion that **adds capability** goes through `/proposal` (classify →
  create → approve → implement → archive) — the curation record + audit trail.
- Close the issue with a curation-outcome comment: what landed (commit +
  version), or why rejected, or (incomplete bundle) what is still needed. Thank
  the contributor.

## Anti-patterns

- ❌ Applying a drift payload without the baseline-sha / `--recount` check (stale
  line numbers corrupt the file).
- ❌ Promoting a domain-coupled payload verbatim instead of genericizing.
- ❌ Editing the autonomy-layer copy instead of `governance_core/` (Art.11.2).
- ❌ Shipping a new data file without a package-data glob (drops from the wheel).
- ❌ Closing an incomplete-bundle issue as promoted — request the rest, keep open.
- ❌ Recording `promoted` without going through `/proposal` for a capability add.

## Cross-reference

- `/submit-candidate` (consumer side) · `/proposal` · `/upgrade`
- `docs/core-manual.md` §11 (pipeline) · §13 (maintainer reject workflow)
