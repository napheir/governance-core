"""Pure-logic unit test for maintainer/candidate_intake.py (P-0082 #23).

Intake works from the embedded candidate.json ONLY -- no payload on disk, no
hub write. Covered WITHOUT any network / gh (gh is monkeypatched):
  - compute_eligibility: every label branch (invalid, T0, surface, kind,
    net-new, layer)
  - parse_candidate_json: valid / missing / malformed
  - is_feedback_issue: candidate-title vs feedback vs plain
  - load_surface_globs / touches_surface: deny-set load + match forms
  - main() orchestration for feedback, unparseable, a valid net-new skill
    (auto-eligible), and a metadata-invalid candidate (invalid) -- gh mocked.

The intake never promotes, so there is no promote path to test. The payload
checks (full structural / secret scan / dedup) run at promote-time (Phase 2),
not here.

Run from repo root (lives in maintainer/; parent.parent is the repo root):
    python maintainer/test_candidate_intake.py
"""
from __future__ import annotations

import json
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


def _valid_meta(**over) -> dict:
    """A schema-valid candidate.json metadata dict (override fields via kwargs)."""
    meta = {
        "schema": 1, "id": "cand-x-20260602-thing", "kind": "skill",
        "origin": "x", "created": "2026-06-02T00:00:00Z",
        "layer": "candidate-common", "title": "t", "rationale": "r",
        "source_paths": ["payload/some_generic_thing.md"],
    }
    meta.update(over)
    return meta


def _body(meta: dict) -> str:
    return ("intro\n### candidate.json\n```json\n"
            + json.dumps(meta) + "\n```\nrest")


def section_compute_eligibility(failed: list[str]) -> None:
    base = dict(net_new=True, surface_hit=None, kind="skill",
                layer="candidate-common")

    labels, elig = ci.compute_eligibility(metadata_valid=True, **base)
    _check(labels == ["candidate", "valid", "auto-eligible"]
           and "auto-eligible" in elig,
           "1. valid + T0 (net-new skill, no surface) -> auto-eligible", failed)

    labels, _ = ci.compute_eligibility(metadata_valid=False, **base)
    _check(labels == ["candidate", "invalid"],
           "2. invalid metadata -> [candidate, invalid]", failed)

    labels, _ = ci.compute_eligibility(metadata_valid=True, **{**base, "kind": "hook"})
    _check(labels == ["candidate", "valid", "needs-human"] and "auto-eligible" not in labels,
           "3. kind=hook -> needs-human (never auto)", failed)

    labels, _ = ci.compute_eligibility(metadata_valid=True, **{**base, "kind": "mechanism"})
    _check("auto-eligible" not in labels,
           "4. kind=mechanism -> never auto-eligible", failed)

    labels, _ = ci.compute_eligibility(
        metadata_valid=True, **{**base, "surface_hit": "tools/x-guard.py ~ tools/*-guard.py"})
    _check(labels == ["candidate", "valid", "needs-human"],
           "5. security-surface hit -> needs-human", failed)

    labels, _ = ci.compute_eligibility(metadata_valid=True, **{**base, "net_new": False})
    _check("auto-eligible" not in labels,
           "6. not net-new -> needs-human", failed)

    labels, _ = ci.compute_eligibility(metadata_valid=True, **{**base, "layer": "business"})
    _check("auto-eligible" not in labels,
           "7. layer=business -> never auto-eligible", failed)

    # Invariant: no branch ever emits an auto-PROMOTE label
    for mv in (True, False):
        labels, _ = ci.compute_eligibility(metadata_valid=mv, **base)
        _check(not any("promote" in lab and "auto-eligible" not in lab for lab in labels),
               f"8. no auto-promote label (metadata_valid={mv})", failed)


def section_parsing(failed: list[str]) -> None:
    good = "intro\n### candidate.json\n```json\n{\"id\":\"c1\",\"kind\":\"skill\"}\n```\nrest"
    _check(ci.parse_candidate_json(good) == {"id": "c1", "kind": "skill"},
           "9. parse valid candidate.json block", failed)
    _check(ci.parse_candidate_json("no block here") is None,
           "10. parse missing block -> None", failed)
    bad = "### candidate.json\n```json\n{not json}\n```"
    _check(ci.parse_candidate_json(bad) is None,
           "11. parse malformed json -> None", failed)


def section_feedback_detection(failed: list[str]) -> None:
    _check(ci.is_feedback_issue("[candidate] x", "### candidate.json\n```json\n{}\n```") is False,
           "12. candidate title + envelope -> not feedback", failed)
    _check(ci.is_feedback_issue("feedback: gc is slow", "free text") is True,
           "13. plain feedback issue -> feedback", failed)
    _check(ci.is_feedback_issue("random", "### candidate.json present") is False,
           "14. body has envelope marker -> not feedback", failed)


def section_surface_config(failed: list[str]) -> None:
    globs = ci.load_surface_globs()
    _check(len(globs) == 41, f"15. surface config has 41 globs (got {len(globs)})", failed)
    _check(len(globs) == len(set(globs)), "16. no duplicate globs", failed)
    _check(ci.touches_surface(["tools/session-boundary-guard.py"],
                              ["tools/session-boundary-guard.py"]) is not None,
           "17. touches_surface: target-relative path hits prefix glob", failed)
    _check(ci.touches_surface(["payload/hooks_manifest.json"],
                              ["**/hooks_manifest.json"]) is not None,
           "18. touches_surface: payload/ path hits **/ glob (stripped)", failed)
    _check(ci.touches_surface(["payload/some_generic_skill.md"], globs) is None,
           "19. touches_surface: generic skill path -> no deny-set hit", failed)
    _check(ci.validate_metadata_ok(_valid_meta()) is None,
           "20. validate_metadata_ok: valid meta -> None", failed)
    _check(ci.validate_metadata_ok(_valid_meta(kind="banana")) is not None,
           "21. validate_metadata_ok: bad kind -> error string", failed)


def section_main_branches(failed: list[str], set_env) -> None:
    calls: dict[str, list] = {"labels": [], "comments": []}
    orig_add, orig_comment = ci.add_labels, ci.comment
    ci.add_labels = lambda repo, issue, *labs: calls["labels"].extend(labs)
    ci.comment = lambda repo, issue, body: calls["comments"].append(body)
    try:
        set_env(GH_REPO="o/r", ISSUE_NUMBER="99",
                ISSUE_TITLE="feedback: x", ISSUE_BODY="plain text")
        rc = ci.main()
        _check(rc == 0 and calls["labels"] == ["feedback", "needs-human"],
               "22. main() feedback -> feedback+needs-human (gh mocked)", failed)

        calls["labels"].clear()
        set_env(GH_REPO="o/r", ISSUE_NUMBER="98",
                ISSUE_TITLE="[candidate] x", ISSUE_BODY="no parseable block")
        rc = ci.main()
        _check(rc == 0 and calls["labels"] == ["candidate", "invalid"],
               "23. main() unparseable candidate -> candidate+invalid", failed)

        calls["labels"].clear()
        set_env(GH_REPO="o/r", ISSUE_NUMBER="97", ISSUE_TITLE="[candidate] s",
                ISSUE_BODY=_body(_valid_meta()))
        rc = ci.main()
        _check(rc == 0 and calls["labels"] == ["candidate", "valid", "auto-eligible"],
               "24. main() valid net-new skill -> auto-eligible (gh mocked)", failed)

        calls["labels"].clear()
        set_env(GH_REPO="o/r", ISSUE_NUMBER="96", ISSUE_TITLE="[candidate] s",
                ISSUE_BODY=_body(_valid_meta(kind="banana")))
        rc = ci.main()
        _check(rc == 0 and calls["labels"] == ["candidate", "invalid"],
               "25. main() metadata-invalid candidate -> invalid", failed)
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
    section_main_branches(failed, set_env)
    for k in ("GH_REPO", "ISSUE_NUMBER", "ISSUE_TITLE", "ISSUE_BODY"):
        os.environ.pop(k, None)

    print()
    if failed:
        print(f"[FAIL] {len(failed)} case(s) failed")
        return 1
    print("[PASS] all 25 cases passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
