"""Test harness for the rejected-candidate registry (P-0076 Phase 2).

Covers:
  - load_rejected_registry: malformed JSON / missing file -> empty shape
  - is_rejected: exact sha match / name match / no match
  - should_block: exact always blocks; name blocks iff block_by_name=true
  - format_advisory: includes skill name, reason, advice, issue url(s)
  - shipped registry: schema is valid, lists the two backfill entries
    landing with P-0076 Phase 2

Run from any clone:
    python tools/test_rejected_registry.py
"""
import io
import json
import sys
import tempfile
from pathlib import Path

from governance_core.candidates import rejected as _rejected


def out(line: str) -> None:
    """Write `line` + newline to stdout (constitution Art.7: no print)."""
    sys.stdout.write(line + "\n")


def _case(label: str, fn) -> bool:
    """Run `fn`; return True iff it returns True without raising."""
    try:
        ok = fn()
    except Exception as exc:  # noqa: BLE001
        out(f"[FAIL] {label}: unexpected {type(exc).__name__}: {exc}")
        return False
    out((f"[OK]   {label}") if ok else f"[FAIL] {label}")
    return bool(ok)


_FIXTURE = {
    "schema": 1,
    "rejected": [
        {
            "rejected_at": "2026-05-26",
            "skill_name": "foo-skill",
            "payload_sha256": "abc123def456",
            "block_by_name": False,
            "origin": "trade-agent",
            "issue_urls": ["https://example/1"],
            "reason": "Business-layer content.",
            "advice": "Keep as local.",
        },
        {
            "rejected_at": "2026-05-26",
            "skill_name": "legacy-skill",
            "payload_sha256": None,
            "block_by_name": True,
            "origin": "trade-agent",
            "issue_urls": ["https://example/2", "https://example/3"],
            "reason": "Pre-0.8.0 rejection: sha not preserved.",
            "advice": "Remove the layer tag.",
        },
    ],
}


def _query_cases() -> list[bool]:
    """is_rejected match / no-match cases against the fixture registry."""
    results: list[bool] = []
    reg = _FIXTURE

    # 1. exact sha match
    r = _rejected.is_rejected("foo-skill", "abc123def456", reg)
    results.append(_case(
        "is_rejected: exact sha match -> match=exact",
        lambda: r is not None and r["match"] == "exact"))
    results.append(_case(
        "is_rejected: exact match entry carries the original reason",
        lambda: r["entry"]["reason"] == "Business-layer content."))

    # 2. same name, different sha -> name match
    r2 = _rejected.is_rejected("foo-skill", "DIFFERENT_SHA", reg)
    results.append(_case(
        "is_rejected: same name + different sha -> match=name",
        lambda: r2 is not None and r2["match"] == "name"))

    # 3. legacy entry (sha=None) matches purely by name
    r3 = _rejected.is_rejected("legacy-skill", "any_sha_works_here", reg)
    results.append(_case(
        "is_rejected: name match against null-sha legacy entry",
        lambda: r3 is not None and r3["match"] == "name"
        and r3["entry"]["block_by_name"] is True))

    # 4. unknown skill -> None
    r4 = _rejected.is_rejected("unrelated", "any", reg)
    results.append(_case(
        "is_rejected: unknown skill -> None",
        lambda: r4 is None))

    # 5. exact preferred over name when multiple entries share a name
    multi_reg = {"schema": 1, "rejected": [
        {"skill_name": "shared", "payload_sha256": "exact",
         "block_by_name": False, "reason": "r1", "advice": "a1"},
        {"skill_name": "shared", "payload_sha256": "other",
         "block_by_name": False, "reason": "r2", "advice": "a2"},
    ]}
    r5 = _rejected.is_rejected("shared", "exact", multi_reg)
    results.append(_case(
        "is_rejected: prefers exact over name when both match",
        lambda: r5 is not None and r5["match"] == "exact"
        and r5["entry"]["reason"] == "r1"))
    return results


def _block_cases() -> list[bool]:
    """should_block logic."""
    results: list[bool] = []

    rej_exact = {"match": "exact", "entry": {"block_by_name": False}}
    results.append(_case(
        "should_block: exact match always blocks (block_by_name irrelevant)",
        lambda: _rejected.should_block(rej_exact)))

    rej_name_blocking = {"match": "name", "entry": {"block_by_name": True}}
    results.append(_case(
        "should_block: name match with block_by_name=True blocks",
        lambda: _rejected.should_block(rej_name_blocking)))

    rej_name_lax = {"match": "name", "entry": {"block_by_name": False}}
    results.append(_case(
        "should_block: name match with block_by_name=False does NOT block",
        lambda: not _rejected.should_block(rej_name_lax)))

    rej_name_missing = {"match": "name", "entry": {}}
    results.append(_case(
        "should_block: name match without block_by_name field -> False",
        lambda: not _rejected.should_block(rej_name_missing)))
    return results


def _advisory_cases() -> list[bool]:
    """format_advisory output structure."""
    results: list[bool] = []
    r = _rejected.is_rejected("foo-skill", "abc123def456", _FIXTURE)
    adv = _rejected.format_advisory("foo-skill", r)
    results.append(_case(
        "format_advisory: header names the skill + kind",
        lambda: "foo-skill" in adv and "previously rejected by hub" in adv))
    results.append(_case(
        "format_advisory: includes the reason",
        lambda: "Business-layer content" in adv))
    results.append(_case(
        "format_advisory: includes the advice",
        lambda: "Keep as local" in adv))
    results.append(_case(
        "format_advisory: includes the issue url",
        lambda: "https://example/1" in adv))

    r2 = _rejected.is_rejected("legacy-skill", "ignored", _FIXTURE)
    adv2 = _rejected.format_advisory("legacy-skill", r2)
    results.append(_case(
        "format_advisory: lists multiple issue urls on separate lines",
        lambda: "https://example/2" in adv2 and "https://example/3" in adv2))
    return results


def _malformed_registry_cases() -> list[bool]:
    """load_rejected_registry fail-safe behavior."""
    results: list[bool] = []
    # tempfile not used; we directly test load on a non-existent path via
    # monkey-patching the registry_path resolver.
    real_path = _rejected.registry_path
    tmp = Path(tempfile.mkdtemp(prefix="gc_rejreg_"))
    try:
        bad = tmp / "broken.json"
        bad.write_text("{ this is not json", encoding="utf-8")
        _rejected.registry_path = lambda: bad
        reg = _rejected.load_rejected_registry()
        results.append(_case(
            "load: malformed JSON -> empty shape, no raise",
            lambda: reg == {"schema": 1, "rejected": []}))

        _rejected.registry_path = lambda: tmp / "absent.json"
        reg2 = _rejected.load_rejected_registry()
        results.append(_case(
            "load: missing file -> empty shape, no raise",
            lambda: reg2 == {"schema": 1, "rejected": []}))
    finally:
        _rejected.registry_path = real_path
    return results


def _shipped_registry_case() -> list[bool]:
    """Smoke test: the shipped registry has schema 1 and lists backfill entries."""
    results: list[bool] = []
    reg = _rejected.load_rejected_registry()
    results.append(_case(
        "shipped registry: schema 1",
        lambda: reg["schema"] == 1))
    results.append(_case(
        "shipped registry: backfill present (>=2 entries)",
        lambda: len(reg["rejected"]) >= 2))
    skills = {e["skill_name"] for e in reg["rejected"]}
    results.append(_case(
        "shipped registry: includes p4-scenario-fixture-construction",
        lambda: "p4-scenario-fixture-construction" in skills))
    results.append(_case(
        "shipped registry: includes cross-agent-gate-spec-mock",
        lambda: "cross-agent-gate-spec-mock" in skills))
    return results


def main() -> int:
    """Run all groups; exit non-zero on any failure."""
    results = (_query_cases() + _block_cases() + _advisory_cases()
               + _malformed_registry_cases() + _shipped_registry_case())
    passed, total = sum(results), len(results)
    out(f"\n{passed}/{total} rejected-registry cases passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
