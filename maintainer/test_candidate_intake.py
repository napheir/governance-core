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


def _payload_body(meta: dict, payload: str, crlf: bool = False) -> str:
    """A full candidate issue body: candidate.json block + one payload block."""
    rel = meta["source_paths"][0]
    body = ("## Candidate\n\n### candidate.json\n```json\n"
            + json.dumps(meta, indent=2) + "\n```\n\n### " + rel + "\n```\n"
            + payload + "\n```\n")
    return body.replace("\n", "\r\n") if crlf else body


def section_duplicates(failed: list[str], set_env) -> None:
    """P-0127: digest-from-body duplicate detection (pure + main branches)."""
    meta = _valid_meta(origin="acme", title="some_generic_thing")
    text_v1, text_v2 = "# thing\nfirst text", "# thing\nrevised text"
    d1 = ci.body_payload_digest(_payload_body(meta, text_v1))
    d2 = ci.body_payload_digest(_payload_body(meta, text_v2))
    empty_reg = {"rejected": []}
    reg = {"rejected": [{
        "skill_name": "some_generic_thing", "payload_sha256": d1,
        "block_by_name": False, "reason": "already promoted", "advice": "none"}]}

    def prior(number: int, digest: str, state: str = "OPEN",
              title: str = "some_generic_thing") -> dict:
        return {"number": number, "state": state, "title": title,
                "digest": digest, "issue_url": f"u/{number}",
                "candidate_id": f"cand-{number}"}

    def classify(number: int, digest: str, registry: dict,
                 priors: list[dict]) -> dict | None:
        return ci.classify_duplicate(
            issue_number=number, title="some_generic_thing", digest=digest,
            rejected_registry=registry, prior_issues=priors)

    _check(d1 != d2 and len(d1) == 64,
           "26. body_payload_digest: content-sensitive sha256", failed)
    _check(ci.body_payload_digest(_payload_body(meta, text_v1, crlf=True)) == d1,
           "27. body_payload_digest: CRLF body == LF digest", failed)
    _check(ci.body_payload_digest(_payload_body(
               _valid_meta(origin="acme", title="some_generic_thing",
                           id="cand-acme-20991231-thing"), text_v1)) == d1,
           "28. body_payload_digest: re-minted id does not change digest", failed)

    v = classify(50, d1, empty_reg, [prior(40, d1, "CLOSED"), prior(45, d1)])
    _check(v is not None and v["verdict"] == "duplicate" and v["of"] == [40, 45],
           "29. same digest as prior issues (open or closed) -> duplicate", failed)
    v = classify(50, d2, empty_reg, [prior(40, d1)])
    _check(v is not None and v["verdict"] == "revision" and v["of"] == [40],
           "30. same title, new digest, prior OPEN -> revision", failed)
    _check(classify(50, d2, empty_reg, [prior(40, d1, "CLOSED")]) is None,
           "31. same title, new digest, prior CLOSED -> no verdict", failed)
    _check(classify(50, d1, empty_reg, [prior(50, d1), prior(60, d1)]) is None,
           "32. self + HIGHER-numbered twins are not prior -> no verdict", failed)
    v = classify(50, d1, reg, [prior(40, d1)])
    _check(v is not None and v["verdict"] == "dup-of-rejected"
           and "already promoted" in v["detail"],
           "33. exact registry digest wins over prior-issue match", failed)
    _check(classify(50, d2, reg, []) is None,
           "34. registry name-only match (new digest) -> no verdict", failed)
    _check(classify(50, d1, empty_reg,
                    [prior(40, d2, title="another_thing")]) is None,
           "35. unrelated prior issue -> no verdict", failed)

    # main() branches -- gh, registry and hub listing stubbed at the boundary
    calls: dict[str, list] = {"labels": [], "comments": []}
    orig = (ci.add_labels, ci.comment, ci._ledger.list_hub_candidate_issues,
            ci._rejected.load_rejected_registry)
    ci.add_labels = lambda repo, issue, *labs: calls["labels"].extend(labs)
    ci.comment = lambda repo, issue, body: calls["comments"].append(body)
    ci._rejected.load_rejected_registry = lambda: empty_reg
    hub: dict[str, list] = {"issues": []}
    ci._ledger.list_hub_candidate_issues = (
        lambda origin, repo="": hub["issues"])

    def run(number: int, payload: str) -> int:
        calls["labels"].clear()
        calls["comments"].clear()
        set_env(GH_REPO="o/r", ISSUE_NUMBER=str(number),
                ISSUE_TITLE="[candidate] skill: some_generic_thing (from acme)",
                ISSUE_BODY=_payload_body(meta, payload, crlf=True))
        return ci.main()

    try:
        hub["issues"] = [prior(40, d1)]
        rc = run(50, text_v1)
        _check(rc == 0 and calls["labels"] == ["candidate", "duplicate"]
               and "#40" in calls["comments"][0],
               "36. main() byte-identical re-file -> candidate+duplicate, "
               "never valid/auto-eligible", failed)

        rc = run(50, text_v2)
        _check(rc == 0 and calls["labels"] == ["candidate", "valid",
                                               "auto-eligible", "revision"]
               and "revision:" in calls["comments"][0],
               "37. main() revised re-file of an open issue -> normal labels "
               "+ revision", failed)

        hub["issues"] = []
        ci._rejected.load_rejected_registry = lambda: reg
        rc = run(50, text_v1)
        _check(rc == 0 and calls["labels"] == ["candidate", "dup-of-rejected"]
               and "already promoted" in calls["comments"][0],
               "38. main() exact registry digest -> candidate+dup-of-rejected",
               failed)

        def boom(origin, repo=""):
            raise RuntimeError("hub listing exploded")
        ci._rejected.load_rejected_registry = lambda: empty_reg
        ci._ledger.list_hub_candidate_issues = boom
        rc = run(50, text_v1)
        _check(rc == 0 and calls["labels"] == ["candidate", "valid",
                                               "auto-eligible"],
               "39. main() dedup failure is fail-open -> labels as before "
               "P-0127", failed)
    finally:
        (ci.add_labels, ci.comment, ci._ledger.list_hub_candidate_issues,
         ci._rejected.load_rejected_registry) = orig


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
    section_duplicates(failed, set_env)
    for k in ("GH_REPO", "ISSUE_NUMBER", "ISSUE_TITLE", "ISSUE_BODY"):
        os.environ.pop(k, None)

    print()
    if failed:
        print(f"[FAIL] {len(failed)} case(s) failed")
        return 1
    print("[PASS] all 39 cases passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
