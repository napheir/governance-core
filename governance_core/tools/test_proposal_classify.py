"""Tests for proposal_lib.py classify subcommand (P-0076 Phase 3)."""
import json
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CLI = [sys.executable, str(REPO / "tools" / "proposal_lib.py"), "classify"]


def run(*args) -> tuple[int, str, str]:
    import os
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    r = subprocess.run(
        CLI + list(args),
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        cwd=REPO, env=env,
    )
    out = (r.stdout or "").strip()
    err = (r.stderr or "").strip()
    return r.returncode, out, err


def parse_json(out: str) -> dict:
    return json.loads(out)


def test_harness_path_hit():
    rc, out, _ = run("--path", ".claude/commands/learn.md", "--quick", "--json")
    assert rc == 0
    d = parse_json(out)
    assert d["verdict"] == "PROPOSAL_REQUIRED"
    assert "harness" in d["reason"]


def test_governance_path_hit():
    rc, out, _ = run("--path", "CLAUDE.md", "--quick", "--json")
    d = parse_json(out)
    assert d["verdict"] == "PROPOSAL_REQUIRED"
    assert "governance" in d["reason"]


def test_routing_path_hit():
    rc, out, _ = run("--path", "knowledge/INDEX.routing.json", "--quick", "--json")
    d = parse_json(out)
    assert d["verdict"] == "PROPOSAL_REQUIRED"
    assert "routing" in d["reason"]


def test_non_harness_path_miss():
    rc, out, _ = run("--path", "analysis/foo.py", "--quick", "--json")
    d = parse_json(out)
    assert d["verdict"] == "NO_PROPOSAL"


def test_keyword_hit():
    rc, out, _ = run("--path", "analysis/foo.py",
                     "--description", "扩 router triggers",
                     "--quick", "--json")
    d = parse_json(out)
    assert d["verdict"] == "PROPOSAL_REQUIRED"
    assert "keyword" in d["reason"]


def test_no_path_arg_fails():
    rc, _, err = run("--quick", "--json")
    assert rc == 1
    assert "--path required" in err


def test_log_entry_written():
    log = REPO / ".claude" / "cache" / "classify_log.jsonl"
    n_before = len(log.read_text(encoding="utf-8").splitlines()) if log.is_file() else 0
    run("--path", ".claude/agents/test_marker.md", "--quick", "--json")
    n_after = len(log.read_text(encoding="utf-8").splitlines())
    assert n_after == n_before + 1
    last = json.loads(log.read_text(encoding="utf-8").splitlines()[-1])
    assert last["paths"] == [".claude/agents/test_marker.md"]
    assert last["verdict"] == "PROPOSAL_REQUIRED"
    assert last["mode"] == "quick"


def test_non_quick_deferred():
    rc, out, _ = run("--path", "analysis/foo.py", "--description", "x", "--json")
    d = parse_json(out)
    assert d["verdict"] == "NEEDS_CLARIFICATION"
    assert d["mode"] == "llm-deferred"


def test_wall_time_under_300ms():
    t0 = time.perf_counter()
    for _ in range(3):
        run("--path", ".claude/commands/learn.md", "--quick", "--json")
    elapsed = (time.perf_counter() - t0) / 3
    assert elapsed < 0.3, f"avg {elapsed:.3f}s exceeds 300ms budget"


def main() -> int:
    tests = [
        test_harness_path_hit, test_governance_path_hit, test_routing_path_hit,
        test_non_harness_path_miss, test_keyword_hit, test_no_path_arg_fails,
        test_log_entry_written, test_non_quick_deferred,
        test_wall_time_under_300ms,
    ]
    passed = 0
    failed = []
    for t in tests:
        try:
            t()
            print(f"[PASS] {t.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"[FAIL] {t.__name__}: {e}")
            failed.append(t.__name__)
        except Exception as e:
            print(f"[ERROR] {t.__name__}: {e}")
            failed.append(t.__name__)
    print(f"\n{passed}/{len(tests)} passed")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
