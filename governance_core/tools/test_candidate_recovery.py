"""Test harness for sweep ledger self-heal (P-0076 Phase 1).

Covers:
  - parse_payload_from_issue_body: extracts (meta, payload bytes) from
    a candidate issue body; payload bytes round-trip exactly (with the
    trailing-newline retention fix landed in this phase)
  - discover_uplinked_from_hub: rehashes hub issues into ledger entries
    using a mocked `gh issue list` subprocess (offline)
  - graceful degradation: missing `gh`, malformed body, malformed gh
    output -> recovery returns empty, no raise
  - integration: empty ledger + outbox envelope whose payload sha matches
    a hub-recovered digest -> sweep would skip uplink (the dedup path
    is the same one P-0072 already covers)

Run from any clone:
    python tools/test_candidate_recovery.py
"""
import hashlib
import io
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from governance_core.candidates import envelope as _envelope
from governance_core.candidates import ledger as _ledger


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


def _build_issue_body(skill_name: str, payload_bytes: bytes,
                      candidate_id: str, origin: str) -> str:
    """Produce a candidate issue body matching the uplink.build_issue format."""
    rel = f"payload/{skill_name}"
    meta = {
        "schema": _envelope.ENVELOPE_SCHEMA,
        "id": candidate_id,
        "kind": "skill",
        "origin": origin,
        "created": "2026-05-26T00:00:00Z",
        "layer": "candidate-common",
        "title": skill_name.replace(".md", ""),
        "rationale": "test payload",
        "source_paths": [rel],
    }
    parts = [
        f"## Candidate: {meta['title']}",
        "",
        f"- id: `{meta['id']}`",
        f"- kind: `{meta['kind']}`",
        f"- origin: `{meta['origin']}`",
        f"- layer: `{meta['layer']}`",
        f"- created: {meta['created']}",
        "",
        "### Rationale",
        "",
        meta["rationale"],
        "",
        "### candidate.json",
        "```json",
        json.dumps(meta, indent=2),
        "```",
        "",
        f"### {rel}",
        "```",
        payload_bytes.decode("utf-8"),
        "```",
    ]
    return "\n".join(parts) + "\n"


def _parser_cases() -> list[bool]:
    """parse_payload_from_issue_body cases."""
    results: list[bool] = []
    payload_bytes = b"---\nname: foo\n---\n\n# foo\nbody line\n"
    body = _build_issue_body("foo.md", payload_bytes,
                             "cand-trade-agent-20260526-foo", "trade-agent")

    meta, payload = _ledger.parse_payload_from_issue_body(body)
    results.append(_case(
        "parse: candidate.json id recovered",
        lambda: meta["id"] == "cand-trade-agent-20260526-foo"))
    results.append(_case(
        "parse: payload bytes round-trip byte-for-byte",
        lambda: payload["foo.md"] == payload_bytes))
    results.append(_case(
        "parse: digest of rebuilt payload equals hash of original",
        lambda: _ledger._hash_payload([("foo.md", payload_bytes)])
        == _ledger._hash_payload(list(payload.items()))))

    # malformed body (no candidate.json fence) -> ValueError
    bad = "## Random text\n\nno candidate fence here\n"
    raised = False
    try:
        _ledger.parse_payload_from_issue_body(bad)
    except ValueError:
        raised = True
    results.append(_case(
        "parse: missing candidate.json fence -> ValueError",
        lambda: raised))

    # body declares source_paths but the payload fence is missing
    meta2 = {
        "schema": _envelope.ENVELOPE_SCHEMA,
        "id": "cand-x-20260526-bar",
        "kind": "skill", "origin": "x",
        "created": "2026-05-26T00:00:00Z", "layer": "candidate-common",
        "title": "bar", "rationale": "test", "source_paths": ["payload/bar.md"],
    }
    bad2 = ("### candidate.json\n```json\n" + json.dumps(meta2, indent=2)
            + "\n```\n")
    raised2 = False
    try:
        _ledger.parse_payload_from_issue_body(bad2)
    except ValueError:
        raised2 = True
    results.append(_case(
        "parse: declared source_paths missing payload fence -> ValueError",
        lambda: raised2))
    return results


def _make_gh_mock(stdout_bytes: bytes, returncode: int = 0,
                  raise_filenotfound: bool = False,
                  raise_calledprocess: bool = False):
    """Build a subprocess.run shim returning canned `gh issue list` output."""
    def _shim(argv, **kw):
        if raise_filenotfound:
            raise FileNotFoundError("gh not found")
        if raise_calledprocess:
            raise subprocess.CalledProcessError(
                1, argv, output=b"", stderr=b"gh: api error")
        return subprocess.CompletedProcess(
            args=argv, returncode=returncode, stdout=stdout_bytes, stderr=b"")
    return _shim


def _discover_cases() -> list[bool]:
    """discover_uplinked_from_hub cases using a mocked subprocess.run."""
    results: list[bool] = []
    real_run = _ledger.subprocess.run

    # 1. hub returns 2 issues with valid bodies -> 2 rebuilt entries
    payload_a = b"# skill A\nbody\n"
    payload_b = b"# skill B\ndifferent body\n"
    body_a = _build_issue_body("skill-a.md", payload_a,
                               "cand-trade-agent-20260526-skill-a",
                               "trade-agent")
    body_b = _build_issue_body("skill-b.md", payload_b,
                               "cand-trade-agent-20260526-skill-b",
                               "trade-agent")
    fake_issues = [
        {"number": 10, "title": "[candidate] skill: skill-a (from trade-agent)",
         "body": body_a, "url": "https://example/10"},
        {"number": 11, "title": "[candidate] skill: skill-b (from trade-agent)",
         "body": body_b, "url": "https://example/11"},
    ]
    _ledger.subprocess.run = _make_gh_mock(
        json.dumps(fake_issues).encode("utf-8"))
    try:
        rebuilt = _ledger.discover_uplinked_from_hub("trade-agent")
        results.append(_case(
            "discover: 2 valid issues -> 2 entries",
            lambda: len(rebuilt) == 2))
        results.append(_case(
            "discover: entry[0] digest matches hash of skill A",
            lambda: rebuilt[0]["digest"]
            == _ledger._hash_payload([("skill-a.md", payload_a)])))
        results.append(_case(
            "discover: entry[1] candidate_id parsed from body",
            lambda: rebuilt[1]["candidate_id"]
            == "cand-trade-agent-20260526-skill-b"))
        results.append(_case(
            "discover: entry[1] issue_url carried through",
            lambda: rebuilt[1]["issue_url"] == "https://example/11"))
    finally:
        _ledger.subprocess.run = real_run

    # 2. hub returns 1 valid + 1 malformed body -> only valid one recovered
    fake_mixed = [
        {"number": 12, "title": "[candidate] skill: skill-a (from trade-agent)",
         "body": body_a, "url": "https://example/12"},
        {"number": 13, "title": "[candidate] junk", "body": "no fences here",
         "url": "https://example/13"},
    ]
    _ledger.subprocess.run = _make_gh_mock(
        json.dumps(fake_mixed).encode("utf-8"))
    try:
        rebuilt = _ledger.discover_uplinked_from_hub("trade-agent")
        results.append(_case(
            "discover: malformed issue skipped, valid one kept",
            lambda: len(rebuilt) == 1
            and rebuilt[0]["candidate_id"]
            == "cand-trade-agent-20260526-skill-a"))
    finally:
        _ledger.subprocess.run = real_run

    # 3. gh not installed -> empty list, no raise
    _ledger.subprocess.run = _make_gh_mock(b"", raise_filenotfound=True)
    try:
        rebuilt = _ledger.discover_uplinked_from_hub("trade-agent")
        results.append(_case(
            "discover: gh missing -> empty list",
            lambda: rebuilt == []))
    finally:
        _ledger.subprocess.run = real_run

    # 4. gh returns non-zero exit -> empty list, no raise
    _ledger.subprocess.run = _make_gh_mock(b"", raise_calledprocess=True)
    try:
        rebuilt = _ledger.discover_uplinked_from_hub("trade-agent")
        results.append(_case(
            "discover: gh failure -> empty list",
            lambda: rebuilt == []))
    finally:
        _ledger.subprocess.run = real_run

    # 5. gh returns non-JSON stdout -> empty list, no raise
    _ledger.subprocess.run = _make_gh_mock(b"this is not json")
    try:
        rebuilt = _ledger.discover_uplinked_from_hub("trade-agent")
        results.append(_case(
            "discover: gh non-JSON output -> empty list",
            lambda: rebuilt == []))
    finally:
        _ledger.subprocess.run = real_run
    return results


def _digest_round_trip_case() -> list[bool]:
    """uplink build_issue payload -> parser -> digest equals payload_digest.

    This is the central correctness invariant of Phase 1: the issue body
    must carry payload bytes verbatim so hub-side rehash reproduces the
    digest the consumer-side `payload_digest` would have written into the
    ledger. The fix in this phase is removing the `.rstrip()` in
    `uplink.build_issue`.
    """
    from governance_core.candidates import uplink as _uplink

    results: list[bool] = []
    tmp = Path(tempfile.mkdtemp(prefix="gc_recovery_roundtrip_"))
    try:
        # A real skill file with a trailing newline -- this is the case
        # that broke before the rstrip fix. Use `write_bytes` so Windows
        # newline translation doesn't drift the on-disk bytes vs. what
        # uplink reads back via `read_text`.
        skill = tmp / "demo.md"
        skill.write_bytes(b"---\nlayer: candidate-common\n---\n\nbody\n")
        env_dir = _envelope.build_envelope(
            tmp / "outbox", kind="skill", origin="trade-agent",
            title="demo", rationale="rt test", payload_files=[skill],
            layer="candidate-common")
        on_disk_digest = _ledger.payload_digest(env_dir)
        title, body, _ = _uplink.build_issue(env_dir)
        _, payload = _ledger.parse_payload_from_issue_body(body)
        rebuilt_digest = _ledger._hash_payload(list(payload.items()))
        results.append(_case(
            "round-trip: digest from issue body equals on-disk digest "
            "(rstrip fix)",
            lambda: rebuilt_digest == on_disk_digest))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return results


def main() -> int:
    """Run all groups; exit non-zero on any failure."""
    results = (_parser_cases() + _discover_cases()
               + _digest_round_trip_case())
    passed, total = sum(results), len(results)
    out(f"\n{passed}/{total} candidate-recovery cases passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
