"""Test harness for the candidate-reminder SessionStart hook (P-0072 Phase 2).

Covers:
  - ledger.skill_digest <-> payload_digest consistency (a loose skill file
    hashes the same as the single-file envelope collect would build)
  - ledger.pending_candidate_skills: candidate-common skills minus those
    already in the uplink ledger; business skills excluded
  - the candidate-reminder.py hook: reports pending candidates for a
    consumer, stays silent when none / already uplinked / hub project

The hook reads only config + skills + the ledger (no auth-code
verification), so every case here is portable -- no signing key needed.

Run from any clone:
    python tools/test_candidate_reminder.py
"""
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import governance_core
from governance_core.candidates import envelope, ledger


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


def _pkg_hook() -> Path:
    """Return the package-source candidate-reminder.py path."""
    return Path(governance_core.__file__).resolve().parent \
        / "hooks" / "candidate-reminder.py"


def _learned(root: Path, name: str, layer: str) -> Path:
    """Write a learned skill with the given `layer:` frontmatter."""
    skill = root / ".claude" / "skills" / "learned" / f"{name}.md"
    skill.parent.mkdir(parents=True, exist_ok=True)
    skill.write_text(f"---\nname: {name}\nlayer: {layer}\n---\n\n"
                     f"# {name}\n\nbody.\n", encoding="utf-8")
    return skill


def _make_repo(consumer_id: str) -> tuple[Path, Path]:
    """Build a throwaway repo with the hook + config; return (root, hook)."""
    tmp = Path(tempfile.mkdtemp(prefix="gc_cand_reminder_"))
    hook = tmp / ".claude" / "hooks" / "candidate-reminder.py"
    hook.parent.mkdir(parents=True)
    shutil.copy2(_pkg_hook(), hook)
    cfg = tmp / ".governance" / "config.json"
    cfg.parent.mkdir(parents=True)
    cfg.write_text(json.dumps({"authorization": {"consumer_id": consumer_id}}),
                   encoding="utf-8")
    return tmp, hook


def _run_hook(hook: Path) -> str:
    """Run the SessionStart hook as a subprocess; return its stdout."""
    return subprocess.run(
        [sys.executable, str(hook)], input="{}",
        capture_output=True, text=True, timeout=15).stdout


def _ledger_cases() -> list[bool]:
    """skill_digest / pending_candidate_skills unit cases."""
    results: list[bool] = []
    tmp = Path(tempfile.mkdtemp(prefix="gc_cand_reminder_led_"))
    try:
        skill = _learned(tmp, "useful-skill", "candidate-common")
        env = envelope.build_envelope(
            tmp / "outbox", kind="skill", origin="acme",
            title="useful-skill", rationale="r", payload_files=[skill])
        results.append(_case(
            "skill_digest == payload_digest of its single-file envelope",
            lambda: ledger.skill_digest(skill) == ledger.payload_digest(env)))

        _learned(tmp, "local-only", "business")
        pend = ledger.pending_candidate_skills(tmp)
        results.append(_case(
            "pending lists candidate-common, excludes business",
            lambda: [p.stem for p in pend] == ["useful-skill"]))

        ledger.record_uplink(ledger.ledger_path(tmp),
                             ledger.skill_digest(skill), "cand-x",
                             "https://issue/1")
        results.append(_case(
            "pending excludes a skill already in the ledger",
            lambda: ledger.pending_candidate_skills(tmp) == []))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return results


def _hook_cases() -> list[bool]:
    """candidate-reminder.py SessionStart hook cases."""
    results: list[bool] = []

    # 1. consumer with a pending candidate-common skill -> reports it
    tmp, hook = _make_repo("acme")
    try:
        _learned(tmp, "useful-skill", "candidate-common")
        txt = _run_hook(hook)
        results.append(_case(
            "consumer + pending candidate -> reminder emitted",
            lambda: "[Candidate uplink]" in txt and "useful-skill" in txt))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # 2. consumer, but the skill is already in the ledger -> silent
    tmp, hook = _make_repo("acme")
    try:
        skill = _learned(tmp, "useful-skill", "candidate-common")
        ledger.record_uplink(ledger.ledger_path(tmp),
                             ledger.skill_digest(skill), "cand-x",
                             "https://issue/1")
        txt = _run_hook(hook)
        results.append(_case("consumer + already uplinked -> silent",
                              lambda: txt.strip() == ""))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # 3. hub project -> silent even with a pending candidate
    tmp, hook = _make_repo("governance-core")
    try:
        _learned(tmp, "useful-skill", "candidate-common")
        txt = _run_hook(hook)
        results.append(_case("hub project -> silent",
                              lambda: txt.strip() == ""))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # 4. consumer with only a business skill -> silent
    tmp, hook = _make_repo("acme")
    try:
        _learned(tmp, "local-only", "business")
        txt = _run_hook(hook)
        results.append(_case("consumer + only business skills -> silent",
                              lambda: txt.strip() == ""))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    return results


def main() -> int:
    """Run the ledger + hook groups; exit non-zero on any failure."""
    if not _pkg_hook().exists():
        out(f"[FAIL] package hook missing: {_pkg_hook()}")
        return 1
    results = _ledger_cases() + _hook_cases()
    passed, total = sum(results), len(results)
    out(f"\n{passed}/{total} candidate-reminder cases passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
