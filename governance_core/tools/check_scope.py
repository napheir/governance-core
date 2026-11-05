# -*- coding: utf-8 -*-
"""
check_scope.py
--------------
Enforce agent file-scope constraints against a fixed baseline commit.

Usage:
    python tools/check_scope.py --agent <agent>
    python tools/check_scope.py --staged-only      # pre-commit gate

Without --agent the agent is this clone's config-derived identity (P-0129,
shared _guard_common.resolve_agent). The config's core agent has no scope
restriction (same as the guards) and always passes.
"""

import argparse
import importlib.util
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RULES_DIR = ROOT / "agent_rules"
BASELINE_FILE = ROOT / ".baseline_commit"


def _load_guard_common():
    """Load the hooks' _guard_common module by path (single identity impl).

    Installed layout: .claude/hooks/ beside tools/; package-source layout:
    governance_core/hooks/. Exits 1 when neither exists.
    """
    here = Path(__file__).resolve().parent
    for candidate in (here.parent / ".claude" / "hooks" / "_guard_common.py",
                      here.parent / "hooks" / "_guard_common.py"):
        if candidate.is_file():
            spec = importlib.util.spec_from_file_location(
                "_gc_guard_common_scope", candidate)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module
    print("[FATAL] cannot locate _guard_common.py (.claude/hooks/ missing?); "
          "run governance-core upgrade")
    sys.exit(1)


def _topology_or_exit():
    """Return (guard_common module, topology dict); exit 1 if unresolvable."""
    guard_common = _load_guard_common()
    try:
        return guard_common, guard_common.load_topology(str(ROOT))
    except guard_common.TopologyError as exc:
        print(f"[FATAL] agent topology unresolved: {exc}")
        sys.exit(1)

def same_as_master(path: str) -> bool:
    """
    Return True if file content at HEAD equals master (i.e., change only comes from merging master).
    """
    try:
        # git diff --quiet master..HEAD -- <path>
        r = subprocess.run(
            ["git", "diff", "--quiet", "master..HEAD", "--", path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        return r.returncode == 0
    except Exception:
        # Conservative: if we can't verify, do NOT skip.
        return False


def run(cmd: str) -> str:
    # Force UTF-8 decoding: on Windows zh-CN locale, subprocess defaults to
    # GBK and crashes on UTF-8 byte output (e.g., CJK filenames staged for
    # deletion). errors="replace" keeps any decode oddity non-fatal.
    return subprocess.check_output(
        cmd, shell=True, cwd=ROOT, encoding="utf-8", errors="replace"
    ).strip()


def load_rules(agent: str):
    allow_file = RULES_DIR / f"{agent}.allow.txt"
    deny_file = RULES_DIR / "shared.deny.txt"

    if not allow_file.exists():
        print(f"[FATAL] no allow list for agent '{agent}': create "
              f"agent_rules/{agent}.allow.txt (one repo-relative path prefix "
              f"per line; core maintains it)")
        sys.exit(1)

    # '#' lines are comments -- same as edit-write-guard's _load_allow_rules.
    allow = [
        line.strip().lstrip("\ufeff").replace("\\", "/")
        for line in allow_file.read_text(encoding="utf-8", errors="replace").splitlines()
        if line.strip() and not line.strip().lstrip("\ufeff").startswith("#")
    ]

    deny = []
    # IMPORTANT: 'core' is governance agent. It must be able to modify shared files
    # (agent_rules/, tools/, .baseline_commit, etc.). Therefore, shared deny rules
    # are NOT applied to core.
    if agent != "core" and deny_file.exists():
        deny = [
            line.strip().lstrip("\ufeff").replace("\\", "/")
            for line in deny_file.read_text(encoding="utf-8", errors="replace").splitlines()
            if line.strip()
        ]

    return allow, deny


def _norm(p: str) -> str:
    p = (p or "").strip()
    p = p.lstrip("\ufeff")          # <--- add this
    p = p.replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    return p


def is_under(path: str, prefixes):
    path_n = _norm(path)

    for pre in prefixes:
        pre_n = _norm(pre)

        # Strip trailing /** glob (e.g. "rules/**" -> "rules")
        if pre_n.endswith("/**"):
            pre_n = pre_n[:-3]

        # treat directory prefix consistently
        if pre_n.endswith("/"):
            if path_n.startswith(pre_n):
                return True
        else:
            # exact file or directory name match
            if path_n == pre_n:
                return True
            # allow "dir" to match "dir/..."
            if path_n.startswith(pre_n + "/"):
                return True

    return False



def get_baseline():
    if not BASELINE_FILE.exists():
        print("[FATAL] .baseline_commit not found. Baseline not initialized.")
        sys.exit(1)
    return BASELINE_FILE.read_text().strip()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--agent", default=None,
                        help="agent name (default: this clone's identity "
                             "from .governance/config.json)")
    parser.add_argument("--staged-only", action="store_true",
                        help="check only staged files (for pre-commit hook)")
    args = parser.parse_args()

    guard_common, topology = _topology_or_exit()
    if args.agent is None:
        try:
            args.agent = guard_common.resolve_agent(str(ROOT))
        except guard_common.TopologyError as exc:
            print(f"[FATAL] agent identity unresolved: {exc}")
            sys.exit(1)
    if args.agent == topology["core"]:
        # Core has governance authority over all scopes (the guards bypass
        # their scope layers for it too); it needs no allow list.
        print(f"[PASS] '{args.agent}' is the core agent: no scope restriction.")
        return


    allow, deny = load_rules(args.agent)

    # Use `-z` (null-terminated) to get raw paths without any quoting.
    # Default `git diff --name-only` wraps paths containing spaces or
    # non-ASCII chars in double-quotes with C-style escapes inside, which
    # then fail prefix matching against UTF-8 allow rules. Combined with
    # core.quotepath=false this eliminates both quoting and octal escapes.
    if args.staged_only:
        try:
            raw = run("git -c core.quotepath=false diff --cached --name-only -z")
        except subprocess.CalledProcessError:
            print("[FATAL] git diff --cached failed.")
            sys.exit(1)
    else:
        baseline = get_baseline()
        try:
            raw = run(f"git -c core.quotepath=false diff --name-only -z {baseline}..HEAD")
        except subprocess.CalledProcessError:
            print("[FATAL] git diff failed. Is baseline commit valid?")
            sys.exit(1)
    files = [p for p in raw.split("\0") if p]

    if not files:
        print("[OK] No file changes detected.")
        return

    violations = []

    for f in files:
        f = f.replace("\\", "/")
        # Shared governance files may change due to merging master into an agent branch.
        # If the file is identical to master, it is NOT an agent-owned modification and should be skipped.
        if args.agent != "core":
            if (
                    f == ".baseline_commit"
                    or f.startswith("agent_rules/")
                    or f == "tools/check_scope.py"
                    or f == "tools/print_startup_pack.ps1"
            ):
                if same_as_master(f):
                    continue

        if is_under(f, deny):
            violations.append((f, "DENY(shared)"))
        elif not is_under(f, allow):
            violations.append((f, "OUT_OF_SCOPE"))

    # During merge commits, filter out files identical to master.
    # These are merge imports (core infrastructure), not agent modifications.
    merge_head = ROOT / ".git" / "MERGE_HEAD"
    if merge_head.exists() and violations and args.agent != "core":
        filtered = []
        for f, reason in violations:
            if not same_as_master(f):
                filtered.append((f, reason))
        skipped = len(violations) - len(filtered)
        if skipped:
            print(f"[INFO] Merge detected: {skipped} scope-external file(s) identical to master (allowed)")
        violations = filtered

    if violations:
        print("\n[FAIL] Scope violations detected:\n")
        for f, reason in violations:
            print(f"  - {f:60s}  [{reason}]")
        print("\nAction:")
        print("  - Move changes into allowed directories")
        print("  - OR submit proposal for shared modules")
        sys.exit(1)

    print("[PASS] All modified files are within allowed scope.")


if __name__ == "__main__":
    main()
