"""Test harness for the candidate-uplink trigger (P-0072).

Covers:
  - uplink ledger: payload digest stability, record / is_uplinked,
    idempotent record, an edited payload yielding a fresh digest
  - candidate.py `sweep`: the /wrap-up trigger -- selects pending
    candidates, skips ones already in the ledger, no-ops on an empty
    project, and skips entirely for the hub project

The sweep cases need a real-key-signed code (uplink verifies origin
against the bundled public key), so they are skipped with a notice when
~/.governance-core/signing_key.json is absent.

Run from any clone:
    python tools/test_candidate_sweep.py
"""
import argparse
import contextlib
import io
import json
import shutil
import sys
import tempfile
from pathlib import Path

from governance_core.auth import codec
from governance_core.candidates import envelope, ledger
from governance_core.tools import candidate

KEY_PATH = Path.home() / ".governance-core" / "signing_key.json"


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


def _envelope_at(parent: Path, body: str) -> Path:
    """Build a one-file candidate envelope under `parent`; return its dir."""
    parent.mkdir(parents=True, exist_ok=True)
    src = parent / "src-skill.md"
    src.write_text(body, encoding="utf-8")
    return envelope.build_envelope(
        parent / "outbox", kind="skill", origin="acme",
        title="sample skill", rationale="a candidate-common skill",
        payload_files=[src])


def _ledger_cases() -> list[bool]:
    """Uplink-ledger unit cases (no signing key needed)."""
    results: list[bool] = []
    tmp = Path(tempfile.mkdtemp(prefix="gc_sweep_ledger_"))
    try:
        env_a = _envelope_at(tmp / "a", "# skill\n\nbody one\n")
        env_b = _envelope_at(tmp / "b", "# skill\n\nbody one\n")
        env_c = _envelope_at(tmp / "c", "# skill\n\nbody TWO (edited)\n")
        dig_a = ledger.payload_digest(env_a)
        dig_b = ledger.payload_digest(env_b)
        dig_c = ledger.payload_digest(env_c)

        results.append(_case(
            "identical payload -> identical digest",
            lambda: dig_a == dig_b))
        results.append(_case(
            "edited payload -> different digest",
            lambda: dig_a != dig_c))

        lp = tmp / "_uplinked.json"
        results.append(_case(
            "load_ledger absent -> empty",
            lambda: ledger.load_ledger(lp)["uplinked"] == []))
        results.append(_case(
            "is_uplinked False before record",
            lambda: not ledger.is_uplinked(ledger.load_ledger(lp), dig_a)))
        ledger.record_uplink(lp, dig_a, "cand-x", "https://issue/1")
        results.append(_case(
            "is_uplinked True after record",
            lambda: ledger.is_uplinked(ledger.load_ledger(lp), dig_a)))
        ledger.record_uplink(lp, dig_a, "cand-x", "https://issue/1")
        results.append(_case(
            "record_uplink idempotent on digest",
            lambda: len(ledger.load_ledger(lp)["uplinked"]) == 1))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return results


def _consumer_project(tmp: Path, consumer_id: str, auth_code: str) -> None:
    """Write a minimal authorized .governance/config.json under `tmp`."""
    cfg = tmp / ".governance" / "config.json"
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text(json.dumps({
        "authorization": {"consumer_id": consumer_id, "auth_code": auth_code},
        "candidate_uplink": {"consent": True}}), encoding="utf-8")


def _learned_skill(tmp: Path, name: str, layer: str) -> None:
    """Write a learned skill with the given `layer:` frontmatter."""
    skill = tmp / ".claude" / "skills" / "learned" / f"{name}.md"
    skill.parent.mkdir(parents=True, exist_ok=True)
    skill.write_text(f"---\nname: {name}\nlayer: {layer}\n---\n\n"
                     f"# {name}\n\nInnocuous candidate body.\n",
                     encoding="utf-8")


def _sweep(tmp: Path) -> tuple[int, str]:
    """Call candidate.cmd_sweep(--dry-run) on `tmp`; return (rc, stdout)."""
    ns = argparse.Namespace(project_root=str(tmp),
                            repo="napheir/governance-core", dry_run=True)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = candidate.cmd_sweep(ns)
    return rc, buf.getvalue()


def _sweep_cases() -> list[bool]:
    """candidate.py sweep cases (need the real signing key)."""
    if not KEY_PATH.exists():
        out(f"[SKIP] sweep cases -- no signing key at {KEY_PATH}")
        return []

    seed = codec.b64url_decode(
        json.loads(KEY_PATH.read_text(encoding="utf-8"))["seed_b64"])

    def _code(consumer_id: str) -> str:
        payload = codec.canonical_payload(
            consumer_id, "2026-05-19", "2027-05-19", schema=2,
            revocation_feed_url="https://example.invalid/revocation.json",
            max_offline_days=30)
        return codec.make_auth_code(payload, seed)

    results: list[bool] = []

    # 1. hub project -> [N/A -- hub], skipped
    tmp = Path(tempfile.mkdtemp(prefix="gc_sweep_hub_"))
    try:
        _consumer_project(tmp, "governance-core", "GC1.placeholder")
        rc, txt = _sweep(tmp)
        results.append(_case("hub project -> N/A skip",
                              lambda: rc == 0 and "N/A -- hub project" in txt))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # 2. empty consumer project -> no pending
    tmp = Path(tempfile.mkdtemp(prefix="gc_sweep_empty_"))
    try:
        _consumer_project(tmp, "acme", _code("acme"))
        rc, txt = _sweep(tmp)
        results.append(_case("no candidate-common skills -> no pending",
                              lambda: rc == 0 and "no pending" in txt))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # 3. consumer project with a candidate-common skill -> pending selected
    tmp = Path(tempfile.mkdtemp(prefix="gc_sweep_pending_"))
    try:
        _consumer_project(tmp, "acme", _code("acme"))
        _learned_skill(tmp, "useful-skill", "candidate-common")
        _learned_skill(tmp, "local-only", "business")  # must be ignored
        rc, txt = _sweep(tmp)
        results.append(_case(
            "candidate-common skill -> selected as pending (business ignored)",
            lambda: rc == 0 and "would uplink" in txt
            and "1 pending" in txt))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # 4. same, but the candidate's digest is already in the ledger -> skipped
    tmp = Path(tempfile.mkdtemp(prefix="gc_sweep_dedup_"))
    try:
        from governance_core.candidates import collect as _collect
        _consumer_project(tmp, "acme", _code("acme"))
        _learned_skill(tmp, "useful-skill", "candidate-common")
        built = _collect.collect_netnew_skills(tmp, "acme")
        ledger.record_uplink(ledger.ledger_path(tmp),
                             ledger.payload_digest(built[0]),
                             "cand-pre", "https://issue/pre")
        rc, txt = _sweep(tmp)
        results.append(_case(
            "candidate already in ledger -> no pending (deduped)",
            lambda: rc == 0 and "no pending" in txt))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    return results


def _dedup_cases() -> list[bool]:
    """P-0099 #90: within-run digest dedup (RC1) + collect idempotency (RC2).

    Key-free: RC1 tests the pure `_dedup_pending_by_digest` helper, RC2 tests
    `collect_netnew_skills` on a temp project (no signing key, no network).
    """
    results: list[bool] = []
    pa, pb, pc = Path("a"), Path("b"), Path("c")

    # RC1: two same-digest pending envelopes -> one kept, one skipped
    kept, skipped = candidate._dedup_pending_by_digest(
        [(pa, "dig1"), (pb, "dig1"), (pc, "dig2")])
    results.append(_case(
        "RC1: same-digest pending -> first kept, dup skipped (order kept)",
        lambda: kept == [(pa, "dig1"), (pc, "dig2")]
        and skipped == [(pb, "dig1")]))
    results.append(_case(
        "RC1: all-unique pending -> nothing skipped",
        lambda: candidate._dedup_pending_by_digest(
            [(pa, "d1"), (pb, "d2")]) == ([(pa, "d1"), (pb, "d2")], [])))

    from governance_core.candidates import collect as _collect

    # RC2: collect is idempotent for an unchanged candidate-common skill
    tmp = Path(tempfile.mkdtemp(prefix="gc_collect_idem_"))
    try:
        _learned_skill(tmp, "useful-skill", "candidate-common")
        first = _collect.collect_netnew_skills(tmp, "acme")
        second = _collect.collect_netnew_skills(tmp, "acme")
        env_dirs = list(
            (tmp / ".governance" / "candidate-outbox").glob("cand-*"))
        results.append(_case("RC2: first collect builds one envelope",
                             lambda: len(first) == 1))
        results.append(_case(
            "RC2: second collect (unchanged skill) builds none",
            lambda: second == []))
        results.append(_case(
            "RC2: outbox holds exactly one envelope dir",
            lambda: len(env_dirs) == 1))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # RC2: an edited skill (new digest) IS still staged as an update
    tmp = Path(tempfile.mkdtemp(prefix="gc_collect_change_"))
    try:
        _learned_skill(tmp, "useful-skill", "candidate-common")
        _collect.collect_netnew_skills(tmp, "acme")
        skill = tmp / ".claude" / "skills" / "learned" / "useful-skill.md"
        skill.write_text(skill.read_text(encoding="utf-8") + "\nedited\n",
                         encoding="utf-8")
        changed = _collect.collect_netnew_skills(tmp, "acme")
        results.append(_case(
            "RC2: edited skill (new digest) -> staged as update",
            lambda: len(changed) == 1))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    return results


def main() -> int:
    """Run the ledger + dedup + sweep groups; exit non-zero on any failure."""
    results = _ledger_cases() + _dedup_cases() + _sweep_cases()
    passed, total = sum(results), len(results)
    out(f"\n{passed}/{total} candidate-sweep cases passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
