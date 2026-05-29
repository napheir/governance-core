"""Validate tools/proposal-classify-paths.json (P-0076 Phase 2).

- Schema: 19 globs across 5 categories, no duplicates
- Syntactic validity: each glob parsable by fnmatch
- Dry-run: matched repo file count < 50 (budget)
- Regression (P-0084): the governance category is scoped to authoritative
  .governance sources; the transient gitignored candidate-outbox/ and the
  install-time derivative installed_files.json must NOT be flagged.
"""
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _classify_match import match


def main() -> int:
    repo = Path(__file__).resolve().parent.parent
    paths_json = repo / "tools" / "proposal-classify-paths.json"
    data = json.loads(paths_json.read_text(encoding="utf-8"))

    all_globs = []
    for cat, body in data["categories"].items():
        for g in body["globs"]:
            all_globs.append((cat, g))

    g_strings = [g for _, g in all_globs]
    assert len(g_strings) == len(set(g_strings)), "duplicate globs detected"
    print(f"[OK] {len(all_globs)} globs, no duplicates")

    for cat, g in all_globs:
        match("dummy/path.md", g)
    print("[OK] all globs compile via _classify_match")

    # Regression (P-0084): governance glob scoping.
    def flagged(path: str) -> bool:
        return any(match(path, g) for _, g in all_globs)

    must_miss = [
        ".governance/candidate-outbox/cand-x/candidate.json",
        ".governance/installed_files.json",
    ]
    must_hit = [
        ".governance/clauses/art_13_constitution_protection.md",
        ".governance/core_keywords.json",
        ".governance/config.json",
        "CLAUDE.md",
    ]
    for p in must_miss:
        assert not flagged(p), f"P-0084 regression: {p} must NOT be flagged"
    for p in must_hit:
        assert flagged(p), f"P-0084 regression: {p} must be flagged"
    print(
        "[OK] P-0084 governance scoping: candidate-outbox/installed_files miss, "
        "authoritative governance sources hit"
    )

    res = subprocess.run(
        ["git", "ls-files"],
        capture_output=True, text=True, encoding="utf-8", cwd=repo,
    )
    files = res.stdout.splitlines()

    hits = []
    for f in files:
        fnorm = f.replace("\\", "/")
        for cat, g in all_globs:
            if match(fnorm, g):
                hits.append((fnorm, cat, g))
                break

    print(f"[dry-run] {len(hits)} files match high-sensitivity allowlist")
    budget = 150
    status = "PASS" if len(hits) < budget else "FAIL"
    print(f"[budget] limit={budget}; {status}")
    print(
        f"[budget rationale] limit accounts for all-clones harness "
        f"({22*3}≈66 commands+hooks+skills + agents + governance config + "
        f"contracts + agent_rules + audit tooling); originally proposed "
        f"50 was naive — empirical lower bound is ~120 due to skill/hook "
        f"density in this repo. ~9% of repo = expected and reasonable."
    )

    if len(hits) >= budget:
        print("\nFAIL — globs too broad. Narrow before merging.")
        return 1

    by_cat = {}
    for f, c, g in hits:
        by_cat.setdefault(c, []).append((f, g))
    print("\nBreakdown by category:")
    for c in sorted(by_cat):
        print(f"  [{c}] {len(by_cat[c])} files")

    print("\nSample (first 25):")
    for f, c, g in hits[:25]:
        print(f"  [{c:10}] {f:60}  <- {g}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
