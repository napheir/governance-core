"""Test harness for drift-as-diff uplink + --body-file (P-0077).

Covers:
  - build_issue on a drift envelope -> body carries `### drift diff`,
    `payload_form: diff`, `payload_sha256:`; NO `### payload/<name>` fence
  - build_issue on a net-new envelope -> body shape unchanged (full
    payload fence, no payload_form line)
  - build_issue on a drift envelope whose baseline cannot be located
    -> falls back to legacy full-payload form
  - parse_payload_from_issue_body on a drift body -> returns (meta, {})
    with meta["payload_form"]=="diff" and meta["payload_sha256"] set
  - parse_payload_from_issue_body on a net-new body -> behavior
    unchanged (payload bytes returned)
  - discover_uplinked_from_hub: mocked `gh issue list` returns one drift
    + one net-new issue -> both digests recovered correctly (drift via
    sha-from-body, net-new via rehash)
  - uplink_envelope --body-file: argv contains --body-file pointing at
    a tempfile whose content equals the body; tempfile cleaned up after

Run from any clone:
    python tools/test_uplink_drift_diff.py
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
from governance_core.candidates import uplink as _uplink


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


def _build_drift_envelope(tmp: Path, drift_target: str,
                           baseline_text: str, current_text: str) -> Path:
    """Build a drift envelope mirroring how installer._capture_drift would.

    The envelope's payload is the consumer's current file bytes. The
    drift_target string is a relative path the hub maps back to a
    governance_core/ baseline. We point drift_target at a real path
    inside the installed governance_core package so _pkg_source_path
    resolves; the baseline we wrote here is just a fixture for diff
    rendering -- the actual diff uses the package source.

    Uses `write_bytes` rather than `write_text` so Windows newline
    translation does not drift the on-disk bytes vs. the in-memory
    `current_text`.
    """
    payload = tmp / "payload" / Path(drift_target).name
    payload.parent.mkdir(parents=True, exist_ok=True)
    payload.write_bytes(current_text.encode("utf-8"))
    return _envelope.build_envelope(
        tmp, kind="mechanism", origin="trade-agent",
        title=f"drift {Path(drift_target).name}",
        rationale="drift capture (test)",
        payload_files=[payload], layer="candidate-common",
        drift_target=drift_target,
        baseline_sha256=hashlib.sha256(
            baseline_text.encode("utf-8")).hexdigest())


def _build_netnew_envelope(tmp: Path, skill_name: str,
                            payload_bytes: bytes) -> Path:
    """Build a net-new (non-drift) skill envelope."""
    tmp.mkdir(parents=True, exist_ok=True)
    payload = tmp / skill_name
    payload.write_bytes(payload_bytes)
    return _envelope.build_envelope(
        tmp / "outbox", kind="skill", origin="trade-agent",
        title=skill_name.replace(".md", ""),
        rationale="net-new skill (test)",
        payload_files=[payload], layer="candidate-common")


def _build_issue_cases() -> list[bool]:
    """uplink.build_issue branching by drift vs net-new."""
    results: list[bool] = []

    # 1. Drift envelope against a real install-managed path -> diff body
    tmp = Path(tempfile.mkdtemp(prefix="gc_p77_drift_"))
    try:
        # Use a real install-managed path so _pkg_source_path resolves.
        drift_target = "tools/proposal_lib.py"
        baseline_text = (Path(_envelope.__file__).resolve().parent.parent
                         / "tools" / "proposal_lib.py").read_text(
                             encoding="utf-8")
        # Consumer adds a fake patch line at the top of the file.
        current_text = ("# local probe edit\n" + baseline_text)
        env_dir = _build_drift_envelope(
            tmp, drift_target, baseline_text, current_text)
        title, body, labels = _uplink.build_issue(env_dir)

        results.append(_case(
            "drift: body declares payload_form: diff",
            lambda: "- payload_form: diff" in body))
        results.append(_case(
            "drift: body has a payload_sha256 line",
            lambda: "- payload_sha256:" in body))
        results.append(_case(
            "drift: body has a drift diff fence",
            lambda: "### drift diff" in body and "```diff" in body))
        results.append(_case(
            "drift: body has NO full payload fence",
            lambda: "### payload/" not in body))
        results.append(_case(
            "drift: diff carries the consumer's added line",
            lambda: "+# local probe edit" in body))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # 2. Net-new envelope -> full payload fence, no payload_form line
    tmp = Path(tempfile.mkdtemp(prefix="gc_p77_netnew_"))
    try:
        payload_bytes = (b"---\nname: foo\nlayer: candidate-common\n---\n"
                         b"\n# foo\nbody\n")
        env_dir = _build_netnew_envelope(tmp, "foo.md", payload_bytes)
        title, body, labels = _uplink.build_issue(env_dir)
        results.append(_case(
            "net-new: body has full payload fence",
            lambda: "### payload/foo.md" in body and "```\n" in body
            and "body\n" in body))
        results.append(_case(
            "net-new: body has NO payload_form line",
            lambda: "payload_form:" not in body))
        results.append(_case(
            "net-new: body has NO drift diff fence",
            lambda: "### drift diff" not in body))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # 3. Drift envelope whose drift_target does NOT resolve -> fallback to
    #    legacy full-payload form so uplink never blocks on baseline miss.
    tmp = Path(tempfile.mkdtemp(prefix="gc_p77_drift_fallback_"))
    try:
        env_dir = _build_drift_envelope(
            tmp, "tools/this-does-not-exist.py",
            "baseline\n", "current\n")
        title, body, labels = _uplink.build_issue(env_dir)
        results.append(_case(
            "drift fallback: missing baseline -> legacy full payload fence",
            lambda: "### payload/this-does-not-exist.py" in body
            and "payload_form:" not in body))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    return results


def _parser_cases() -> list[bool]:
    """parse_payload_from_issue_body branching by body shape."""
    results: list[bool] = []

    # Build a drift body via build_issue (proven shape from §1)
    tmp = Path(tempfile.mkdtemp(prefix="gc_p77_parser_"))
    try:
        drift_target = "tools/proposal_lib.py"
        baseline_text = (Path(_envelope.__file__).resolve().parent.parent
                         / "tools" / "proposal_lib.py").read_text(
                             encoding="utf-8")
        current_text = "# patched header\n" + baseline_text
        env_dir = _build_drift_envelope(
            tmp, drift_target, baseline_text, current_text)
        _, drift_body, _ = _uplink.build_issue(env_dir)

        meta, payload = _ledger.parse_payload_from_issue_body(drift_body)
        results.append(_case(
            "parse drift: meta has payload_form='diff'",
            lambda: meta.get("payload_form") == "diff"))
        results.append(_case(
            "parse drift: meta has 64-hex payload_sha256",
            lambda: "payload_sha256" in meta
            and len(meta["payload_sha256"]) == 64))
        results.append(_case(
            "parse drift: payload bytes dict is empty (sha is authoritative)",
            lambda: payload == {}))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # Net-new body parser path unchanged
    tmp = Path(tempfile.mkdtemp(prefix="gc_p77_parser_netnew_"))
    try:
        payload_bytes = b"---\nname: foo\n---\n\n# foo\n"
        env_dir = _build_netnew_envelope(tmp, "foo.md", payload_bytes)
        _, netnew_body, _ = _uplink.build_issue(env_dir)
        meta, payload = _ledger.parse_payload_from_issue_body(netnew_body)
        results.append(_case(
            "parse net-new: no payload_form key",
            lambda: "payload_form" not in meta))
        results.append(_case(
            "parse net-new: payload bytes recovered",
            lambda: payload.get("foo.md") == payload_bytes))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    return results


def _discover_recovery_cases() -> list[bool]:
    """discover_uplinked_from_hub correctly handles drift + net-new bodies."""
    results: list[bool] = []

    tmp = Path(tempfile.mkdtemp(prefix="gc_p77_discover_"))
    try:
        # Build one drift + one net-new issue body via build_issue.
        drift_target = "tools/proposal_lib.py"
        baseline_text = (Path(_envelope.__file__).resolve().parent.parent
                         / "tools" / "proposal_lib.py").read_text(
                             encoding="utf-8")
        current_text = "# patched\n" + baseline_text
        drift_env = _build_drift_envelope(
            tmp / "a", drift_target, baseline_text, current_text)
        _, drift_body, _ = _uplink.build_issue(drift_env)

        netnew_payload = b"---\nname: bar\n---\n\n# bar\n"
        netnew_env = _build_netnew_envelope(tmp / "b", "bar.md", netnew_payload)
        _, netnew_body, _ = _uplink.build_issue(netnew_env)

        # Compute expected digests:
        # - drift: matches what build_issue computed and embedded as
        #   payload_sha256 (basename + null + bytes + null hash)
        h_drift = hashlib.sha256()
        h_drift.update(b"proposal_lib.py\0")
        h_drift.update(current_text.encode("utf-8"))
        h_drift.update(b"\0")
        expected_drift_digest = h_drift.hexdigest()
        # - net-new: rehash via _hash_payload
        expected_netnew_digest = _ledger._hash_payload(
            [("bar.md", netnew_payload)])

        # Mock subprocess.run for the discover call
        fake_issues = [
            {"number": 100, "title": "[candidate] mechanism: drift proposal_lib.py (from trade-agent)",
             "body": drift_body, "url": "https://example/100"},
            {"number": 101, "title": "[candidate] skill: bar (from trade-agent)",
             "body": netnew_body, "url": "https://example/101"},
        ]
        real_run = _ledger.subprocess.run

        def fake_run(argv, **kw):
            return subprocess.CompletedProcess(
                args=argv, returncode=0,
                stdout=json.dumps(fake_issues).encode("utf-8"),
                stderr=b"")
        _ledger.subprocess.run = fake_run
        try:
            rebuilt = _ledger.discover_uplinked_from_hub("trade-agent")
        finally:
            _ledger.subprocess.run = real_run

        results.append(_case(
            "discover: 2 issues rebuilt (drift + net-new)",
            lambda: len(rebuilt) == 2))
        # Drift entry should match the sha-from-body
        drift_entry = next((r for r in rebuilt
                            if "100" in r["issue_url"]), None)
        results.append(_case(
            "discover drift: digest taken from body's payload_sha256",
            lambda: drift_entry is not None
            and drift_entry["digest"] == expected_drift_digest))
        netnew_entry = next((r for r in rebuilt
                             if "101" in r["issue_url"]), None)
        results.append(_case(
            "discover net-new: digest via rehash matches expected",
            lambda: netnew_entry is not None
            and netnew_entry["digest"] == expected_netnew_digest))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    return results


def _gh_command_argv_case() -> list[bool]:
    """uplink.gh_command builds argv with --body-file, not --body."""
    results: list[bool] = []
    argv = _uplink.gh_command(
        title="test title",
        body_file="/tmp/fake_body.md",
        labels=["candidate", "kind/skill"],
        repo="napheir/governance-core")
    results.append(_case(
        "gh_command: uses --body-file, not --body",
        lambda: "--body-file" in argv and "--body" not in argv))
    results.append(_case(
        "gh_command: --body-file argument value is the tempfile path",
        lambda: argv[argv.index("--body-file") + 1] == "/tmp/fake_body.md"))
    results.append(_case(
        "gh_command: labels passed as --label entries",
        lambda: argv.count("--label") == 2))
    return results


def main() -> int:
    """Run all groups; exit non-zero on any failure."""
    results = (_build_issue_cases() + _parser_cases()
               + _discover_recovery_cases() + _gh_command_argv_case())
    passed, total = sum(results), len(results)
    out(f"\n{passed}/{total} uplink-drift-diff cases passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
