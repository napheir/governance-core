"""Pure-logic unit test for maintainer/candidate_intake.py (P-0088 Phase 1).

Covers the deterministic intake decision WITHOUT any network / gh / git:
  - compute_eligibility: every label branch (T0, surface, kind, net-new,
    secret, dup, invalid)
  - parse_candidate_json: valid / missing / malformed
  - is_feedback_issue: candidate-title vs feedback vs plain
  - load_surface_globs: deny-set loads, no duplicate globs
  - main() orchestration for the two side-effect-light branches (feedback,
    unparseable), with gh wrappers monkeypatched to capture labels/comments.

The intake never promotes, so there is no promote path to test. CI-side
end-to-end (fetch + real validator + scanner) is exercised by the first real
candidate issue, not here.

Run from repo root (the autonomy-layer copy resolves maintainer/ at parent.parent):
    python tools/test_candidate_intake.py
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "maintainer"))

import candidate_intake as ci  # noqa: E402


def _check(cond: bool, label: str, failed: list[str]) -> None:
    if cond:
        print(f"  [OK]   {label}")
    else:
        print(f"  [FAIL] {label}")
        failed.append(label)


def section_compute_eligibility(failed: list[str]) -> None:
    base = dict(secrets_found=False, is_dup=False, net_new=True,
                surface_hit=None, kind="skill", layer="candidate-common")

    labels, elig = ci.compute_eligibility(structural_ok=True, **base)
    _check(labels == ["candidate", "valid", "auto-eligible"]
           and "auto-eligible" in elig,
           "1. T0 skill net-new clean -> auto-eligible", failed)

    labels, _ = ci.compute_eligibility(structural_ok=True, **{**base, "kind": "hook"})
    _check(labels == ["candidate", "valid", "needs-human"] and "auto-eligible" not in labels,
           "2. kind=hook -> needs-human (never auto)", failed)

    labels, _ = ci.compute_eligibility(structural_ok=True, **{**base, "kind": "mechanism"})
    _check("auto-eligible" not in labels,
           "3. kind=mechanism -> never auto-eligible", failed)

    labels, _ = ci.compute_eligibility(
        structural_ok=True, **{**base, "surface_hit": "tools/x-guard.py ~ tools/*-guard.py"})
    _check(labels == ["candidate", "valid", "needs-human"],
           "4. security-surface hit -> needs-human", failed)

    labels, _ = ci.compute_eligibility(structural_ok=True, **{**base, "net_new": False})
    _check("auto-eligible" not in labels,
           "5. not net-new -> needs-human", failed)

    labels, _ = ci.compute_eligibility(structural_ok=True, **{**base, "layer": "business"})
    _check("auto-eligible" not in labels,
           "6. layer=business -> never auto-eligible", failed)

    labels, _ = ci.compute_eligibility(structural_ok=True, **{**base, "secrets_found": True})
    _check(labels == ["candidate", "invalid", "needs-human"],
           "7. secret on re-scan -> invalid", failed)

    labels, _ = ci.compute_eligibility(structural_ok=True, **{**base, "is_dup": True})
    _check("dup-of-rejected" in labels and "auto-eligible" not in labels,
           "8. previously-rejected digest -> dup-of-rejected + needs-human", failed)

    labels, _ = ci.compute_eligibility(structural_ok=False, **base)
    _check(labels == ["candidate", "invalid", "needs-human"],
           "9. not structurally valid -> invalid", failed)

    # Invariant: no branch ever emits an auto-PROMOTE label
    for kw in [dict(structural_ok=True, **base)]:
        labels, _ = ci.compute_eligibility(**kw)
        _check(not any("promote" in lab and "auto-eligible" not in lab for lab in labels),
               "10. no branch emits an auto-promote label", failed)


def section_parsing(failed: list[str]) -> None:
    good = "intro\n### candidate.json\n```json\n{\"id\":\"c1\",\"kind\":\"skill\"}\n```\nrest"
    _check(ci.parse_candidate_json(good) == {"id": "c1", "kind": "skill"},
           "11. parse valid candidate.json block", failed)
    _check(ci.parse_candidate_json("no block here") is None,
           "12. parse missing block -> None", failed)
    bad = "### candidate.json\n```json\n{not json}\n```"
    _check(ci.parse_candidate_json(bad) is None,
           "13. parse malformed json -> None", failed)


def section_feedback_detection(failed: list[str]) -> None:
    _check(ci.is_feedback_issue("[candidate] x", "### candidate.json\n```json\n{}\n```") is False,
           "14. candidate title + envelope -> not feedback", failed)
    _check(ci.is_feedback_issue("feedback: gc is slow", "free text") is True,
           "15. plain feedback issue -> feedback", failed)
    _check(ci.is_feedback_issue("random", "### candidate.json present") is False,
           "16. body has envelope marker -> not feedback", failed)


def section_surface_config(failed: list[str]) -> None:
    globs = ci.load_surface_globs()
    _check(len(globs) == 41, f"17. surface config has 41 globs (got {len(globs)})", failed)
    _check(len(globs) == len(set(globs)), "18. no duplicate globs", failed)
    # target-relative declaration matches a prefix glob (raw form)
    _check(ci.touches_surface(["tools/session-boundary-guard.py"],
                              ["tools/session-boundary-guard.py"]) is not None,
           "19. touches_surface: target-relative path hits prefix glob", failed)
    # payload/-prefixed declaration matches a **/ glob via the stripped form
    _check(ci.touches_surface(["payload/hooks_manifest.json"],
                              ["**/hooks_manifest.json"]) is not None,
           "20. touches_surface: payload/ path hits **/ glob (stripped)", failed)
    # an unrelated path does not hit the real deny-set
    _check(ci.touches_surface(["payload/some_generic_skill.md"], globs) is None,
           "21. touches_surface: generic skill path -> no deny-set hit", failed)


def section_main_feedback_branch(failed: list[str], monkeypatch_env) -> None:
    calls: dict[str, list] = {"labels": [], "comments": []}
    orig_add, orig_comment = ci.add_labels, ci.comment
    ci.add_labels = lambda repo, issue, *labs: calls["labels"].extend(labs)
    ci.comment = lambda repo, issue, body: calls["comments"].append(body)
    try:
        monkeypatch_env(GH_REPO="o/r", ISSUE_NUMBER="99",
                        ISSUE_TITLE="feedback: x", ISSUE_BODY="plain text")
        rc = ci.main()
        _check(rc == 0 and calls["labels"] == ["feedback", "needs-human"],
               "22. main() feedback issue -> feedback+needs-human labels (gh mocked)", failed)

        calls["labels"].clear()
        monkeypatch_env(GH_REPO="o/r", ISSUE_NUMBER="98",
                        ISSUE_TITLE="[candidate] x", ISSUE_BODY="no parseable block")
        rc = ci.main()
        _check(rc == 0 and calls["labels"] == ["candidate", "invalid"],
               "23. main() unparseable candidate -> candidate+invalid (gh mocked)", failed)
    finally:
        ci.add_labels, ci.comment = orig_add, orig_comment


def main() -> int:
    import os
    failed: list[str] = []

    def set_env(**kw: str) -> None:
        for k in ("GH_REPO", "ISSUE_NUMBER", "ISSUE_TITLE", "ISSUE_BODY"):
            os.environ.pop(k, None)
        os.environ.update(kw)

    section_compute_eligibility(failed)
    section_parsing(failed)
    section_feedback_detection(failed)
    section_surface_config(failed)
    section_main_feedback_branch(failed, set_env)
    for k in ("GH_REPO", "ISSUE_NUMBER", "ISSUE_TITLE", "ISSUE_BODY"):
        os.environ.pop(k, None)

    print()
    if failed:
        print(f"[FAIL] {len(failed)} case(s) failed")
        return 1
    print("[PASS] all 23 cases passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
