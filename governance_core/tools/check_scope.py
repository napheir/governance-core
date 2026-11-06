# -*- coding: utf-8 -*-
"""
check_scope.py
--------------
Enforce agent file-scope constraints.

Usage:
    python tools/check_scope.py --agent <agent>    # branch audit of HEAD
    python tools/check_scope.py --audit-branch --agent <agent> --repo <clone> [--json]
    python tools/check_scope.py --staged-only      # pre-commit gate
    python tools/check_scope.py --merge-commit     # pre-merge-commit gate

The branch audit (P-0135; contracts/shared_state_ownership.md §1) checks a
branch's net change since its merge-base with the core ref, merge
resolutions included, against the agent's allow rules as committed on the
core ref. Run from core with --repo, it fetches the clone's checked-out
commit into refs/gc-audit/<agent> and judges it with core's own refs and
rules. Exit 0 = in scope, 1 = violations, 2 = the audit could not run. It
replaces the retired baseline mode (`.baseline_commit`, which nothing ever
wrote).

Without --agent the agent is this clone's config-derived identity (P-0129,
shared _guard_common.resolve_agent). The config's core agent has no scope
restriction (same as the guards) and always passes.

Core history is config-derived (P-0131): `upstream_branch` and
`core_branches`. During a merge commit a scope-external file passes only as
core content -- identical to the core ref, or staged as MERGE_HEAD has it
with no merged-in commit outside core history touching it. Files another
agent's commits bring in are rejected as IMPORTED_OUT_OF_SCOPE.

--merge-commit runs for an automatic (conflict-free) merge commit, which
never runs pre-commit. git writes MERGE_HEAD only after that hook, so a
merge import cannot be attributed there: scope-external files not identical
to the core ref defer the commit (exit 1). git keeps the merge staged;
`git commit` concludes it through the pre-commit gate.
"""

import argparse
import json
import importlib.util
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RULES_DIR = ROOT / "agent_rules"


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

def _git_ok(*args: str) -> bool:
    """Return True when `git <args>` exits 0 in ROOT (any error -> False)."""
    try:
        r = subprocess.run(["git", *args], cwd=ROOT, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, check=False)
    except OSError:
        return False
    return r.returncode == 0


def load_core_refs() -> list:
    """Return the core-history refs that resolve in this clone (P-0131).

    From .governance/config.json: `upstream_branch` first (optional; e.g.
    origin/master, which /sync-repos fetches -- a business clone's local
    core branch is usually stale), then each `core_branches` entry (required,
    non-empty list of str, as in config.py). Refs that do not resolve to a
    commit here are skipped. Exits 1 when `core_branches` is missing or
    ill-typed (no default, Art.4).
    """
    cfg_path = ROOT / ".governance" / "config.json"
    try:
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"[FATAL] cannot read {cfg_path}: {exc}")
        sys.exit(1)
    branches = cfg["core_branches"] if "core_branches" in cfg else None
    if (not isinstance(branches, list) or not branches
            or not all(isinstance(b, str) and b for b in branches)):
        print(f"[FATAL] {cfg_path}: 'core_branches' must be a non-empty list "
              f"of branch names")
        sys.exit(1)
    candidates = list(branches)
    if "upstream_branch" in cfg and isinstance(cfg["upstream_branch"], str) \
            and cfg["upstream_branch"]:
        candidates.insert(0, cfg["upstream_branch"])
    refs = []
    for ref in candidates:
        if ref not in refs and _git_ok("rev-parse", "-q", "--verify",
                                       f"{ref}^{{commit}}"):
            refs.append(ref)
    return refs


def same_as_core(path: str, staged: bool, core_ref) -> bool:
    """Return True if `path` equals its version on `core_ref` (core content).

    `core_ref` is the authoritative core ref (first of load_core_refs());
    None -- no core ref resolves -- is never "the same".
    staged=True (the pre-commit gate) compares the STAGED content: comparing
    HEAD there passed any staged edit to a file whose committed version still
    matched core -- e.g. a business agent rewriting its own
    agent_rules/<agent>.allow.txt in the commit under check (P-0129).
    staged=False compares the committed HEAD (used by the retired baseline
    mode; every current caller passes staged=True).
    Any git error counts as "not the same".
    """
    if core_ref is None:
        return False
    cmd = (["git", "diff", "--cached", "--quiet", core_ref, "--", path]
           if staged else
           ["git", "diff", "--quiet", core_ref, "HEAD", "--", path])
    try:
        r = subprocess.run(cmd, cwd=ROOT, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, check=False)
        return r.returncode == 0
    except Exception:
        # Conservative: if we can't verify, do NOT skip.
        return False


def in_merge() -> bool:
    """Return True while a merge is being concluded (MERGE_HEAD exists).

    Uses rev-parse rather than ROOT/.git/MERGE_HEAD so worktrees (where .git
    is a file) are handled.
    """
    r = subprocess.run(
        ["git", "rev-parse", "-q", "--verify", "MERGE_HEAD"],
        cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        check=False,
    )
    return r.returncode == 0


def same_as_merge_head(path: str) -> bool:
    """Return True if the staged content of `path` equals MERGE_HEAD's.

    During a merge commit (pre-commit runs only when the merge did not
    auto-commit, e.g. after conflict resolution) HEAD is still the pre-merge
    commit, so a HEAD comparison flags every file the merge brings in. The
    staged version equal to the merged-in commit means the change came from
    the merge, not from this agent (P-0129 F9) -- but not that it came from
    core: see foreign_import_commits().
    """
    r = subprocess.run(
        ["git", "diff", "--cached", "--quiet", "MERGE_HEAD", "--", path],
        cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        check=False,
    )
    return r.returncode == 0


def foreign_import_commits(core_refs: list) -> dict:
    """Map each file the merge imports from outside core history to its commits.

    Runs `git log --cc --name-only MERGE_HEAD ^HEAD ^<core ref>...`: the
    commits this merge brings in that are not in core history, with the
    files each changed -- for merge commits (`--cc`) only the files that
    differ from every parent, i.e. conflict resolutions and edits slipped
    into the merge. A file staged as MERGE_HEAD has it is a legitimate import
    only if no such commit touched it (P-0131): before, any merged-in branch
    -- another business agent's included -- passed whole.

    Returns {path: ["<short hash> <subject>", ...]}. With no resolvable core
    ref every incoming commit counts (fail-closed). A git failure exits 1.
    """
    sep = "\x1e"
    cmd = ["git", "-c", "core.quotepath=false", "log", "--cc", "--name-only",
           f"--format={sep}%h %s", "MERGE_HEAD", "^HEAD",
           *[f"^{ref}" for ref in core_refs]]
    try:
        out = subprocess.check_output(cmd, cwd=ROOT, encoding="utf-8",
                                      errors="replace",
                                      stderr=subprocess.DEVNULL)
    except (OSError, subprocess.CalledProcessError):
        print("[FATAL] git log of the merged-in commits failed.")
        sys.exit(1)
    touched: dict = {}
    commit = None
    # split("\n"), not splitlines(): splitlines() also breaks on \x1e.
    for line in out.split("\n"):
        if line.startswith(sep):
            commit = line[len(sep):]
        elif line.strip() and commit is not None:
            touched.setdefault(line.strip().replace("\\", "/"), []).append(commit)
    return touched


def run(cmd: str) -> str:
    # Force UTF-8 decoding: on Windows zh-CN locale, subprocess defaults to
    # GBK and crashes on UTF-8 byte output (e.g., CJK filenames staged for
    # deletion). errors="replace" keeps any decode oddity non-fatal.
    return subprocess.check_output(
        cmd, shell=True, cwd=ROOT, encoding="utf-8", errors="replace"
    ).strip()


def _allow_lines(text: str) -> list:
    """Allow-rule prefixes from an allow file's text ('#' lines are comments,
    same as edit-write-guard's _load_allow_rules)."""
    return [
        line.strip().lstrip("\ufeff").replace("\\", "/")
        for line in text.splitlines()
        if line.strip() and not line.strip().lstrip("\ufeff").startswith("#")
    ]


def _deny_lines(text: str) -> list:
    """Deny-rule prefixes from shared.deny.txt's text."""
    return [line.strip().lstrip("\ufeff").replace("\\", "/")
            for line in text.splitlines() if line.strip()]


def load_rules(agent: str):
    allow_file = RULES_DIR / f"{agent}.allow.txt"
    deny_file = RULES_DIR / "shared.deny.txt"

    if not allow_file.exists():
        print(f"[FATAL] no allow list for agent '{agent}': create "
              f"agent_rules/{agent}.allow.txt (one repo-relative path prefix "
              f"per line; core maintains it)")
        sys.exit(1)

    allow = _allow_lines(allow_file.read_text(encoding="utf-8", errors="replace"))

    deny = []
    # Only non-core agents reach here: main() passes the core agent before
    # loading rules, so it is never subject to the shared deny list.
    if deny_file.exists():
        deny = _deny_lines(deny_file.read_text(encoding="utf-8", errors="replace"))

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

        # Strip trailing /** glob (e.g. "services/**" -> "services")
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



# ---------------------------------------------------------------------------
# Branch scope audit (P-0135; contracts/shared_state_ownership.md §1). Audits
# a business branch's net change since its merge-base with the core ref,
# merge resolutions included. Rules, the core ref and core history are read
# from THIS repo: run from core, nothing the audited agent controls (its
# allow file, its refs, its working tree) steers the result.
# ---------------------------------------------------------------------------

AUDIT_REF_PREFIX = "refs/gc-audit/"


class AuditError(Exception):
    """The branch audit could not run (exit 2)."""


def _git(*args: str, cwd: Path = ROOT, check: bool = True):
    """Return stdout of `git <args>` in `cwd`; None on failure when check=False."""
    try:
        res = subprocess.run(["git", "-c", "core.quotepath=false", *args],
                             cwd=cwd, capture_output=True, encoding="utf-8",
                             errors="replace", check=False)
    except OSError as exc:
        raise AuditError(f"git not runnable: {exc}") from exc
    if res.returncode != 0:
        if check:
            raise AuditError(f"git {' '.join(args)} failed: {res.stderr.strip()}")
        return None
    return res.stdout


def fetch_clone_head(repo: Path, agent: str) -> str:
    """Fetch the checked-out commit of clone `repo` into refs/gc-audit/<agent>.

    The auditing repo then holds its own copy of the branch; the clone's own
    refs (e.g. a rewritten origin/master) play no part in the audit.
    """
    ref = AUDIT_REF_PREFIX + agent
    _git("fetch", "--no-tags", "-q", str(repo), f"+HEAD:{ref}")
    return ref


def core_rules(core_ref: str, agent: str) -> tuple:
    """(allow, deny) for `agent` as committed on `core_ref` (never a work tree)."""
    allow_text = _git("show", f"{core_ref}:agent_rules/{agent}.allow.txt",
                      check=False)
    if allow_text is None:
        raise AuditError(f"no agent_rules/{agent}.allow.txt on {core_ref}")
    deny_text = _git("show", f"{core_ref}:agent_rules/shared.deny.txt",
                     check=False)
    return _allow_lines(allow_text), _deny_lines(deny_text or "")


def _core_blobs(core_ref: str, paths: list) -> dict:
    """{path: {blob ids of every version of that path in core history}}."""
    blobs: dict = {p: set() for p in paths}
    for i in range(0, len(paths), 200):
        chunk = paths[i:i + 200]
        out = _git("log", "--root", "-m", "--no-renames", "--raw", "--no-abbrev",
                   "--format=", core_ref, "--", *chunk)
        for line in out.split("\n"):
            if not line.startswith(":") or "\t" not in line:
                continue
            meta, path = line.split("\t", 1)
            fields = meta.split()
            if len(fields) >= 4 and fields[3].strip("0") and path in blobs:
                blobs[path].add(fields[3])
    return blobs


def _path_owners(core_ref: str, path: str, agents: list) -> list:
    """Agents whose core-ref allow rules cover `path`."""
    owners = []
    for name in agents:
        text = _git("show", f"{core_ref}:agent_rules/{name}.allow.txt", check=False)
        if text is not None and is_under(path, _allow_lines(text)):
            owners.append(name)
    return owners


def audit_branch(agent: str, ref: str, core_ref: str, other_agents: list) -> dict:
    """Audit `ref` for `agent` against `core_ref`; return the report dict.

    A path changed since merge-base(core_ref, ref) passes when it matches the
    agent's allow rules (minus deny), when its tip blob is a version core
    committed, or when it is deleted and absent at the core tip.
    """
    base = _git("merge-base", core_ref, ref, check=False)
    if not base:
        raise AuditError(f"no merge-base between {core_ref} and {ref}")
    base = base.strip()
    allow, deny = core_rules(core_ref, agent)
    raw = _git("diff", "--no-renames", "--name-status", "-z", base, ref)
    tokens = [t for t in raw.split("\0") if t]
    changes = list(zip(tokens[0::2], tokens[1::2]))
    suspect = [(st, p) for st, p in changes
               if is_under(p, deny) or not is_under(p, allow)]
    history = _core_blobs(core_ref, [p for st, p in suspect if st != "D"])
    violations = []
    for status, path in suspect:
        if not is_under(path, deny):
            if status == "D":
                if _git("cat-file", "-e", f"{core_ref}:{path}", check=False) is None:
                    continue  # core deleted it too
            else:
                blob = _git("rev-parse", f"{ref}:{path}").strip()
                if blob in history[path]:
                    continue  # a version core committed
        log = _git("log", "--format=%h %s", f"{base}..{ref}", "--", path)
        violations.append({
            "path": path, "status": status,
            "commits": [c for c in log.split("\n") if c.strip()],
            "owners": _path_owners(core_ref, path, other_agents),
        })
    return {"schema": 1, "agent": agent, "ref": ref, "base": base,
            "core_ref": core_ref, "violations": violations}


def _print_audit(report: dict) -> None:
    """Human-readable branch-audit report."""
    if not report["violations"]:
        print(f"[PASS] {report['agent']} @ {report['ref']}: every change since "
              f"{report['base'][:12]} is in scope or core content "
              f"(rules from {report['core_ref']}).")
        return
    print(f"\n[FAIL] {report['agent']} @ {report['ref']}: "
          f"{len(report['violations'])} out-of-scope change(s) since "
          f"{report['base'][:12]} (rules from {report['core_ref']}):\n")
    for v in report["violations"]:
        owners = f"  owner: {', '.join(v['owners'])}" if v["owners"] else ""
        print(f"  - [{v['status']}] {v['path']}{owners}")
        for c in v["commits"][:5]:
            print(f"      {c}")
        if len(v["commits"]) > 5:
            print(f"      (+{len(v['commits']) - 5} more)")
    print("\nThese changes are outside the agent's allow rules on the core "
          "branch and are not core content. Revert them on the branch, or "
          "route them through a proposal.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--agent", default=None,
                        help="agent name (default: this clone's identity "
                             "from .governance/config.json)")
    parser.add_argument("--staged-only", action="store_true",
                        help="check only staged files (for pre-commit hook)")
    parser.add_argument("--merge-commit", action="store_true",
                        help="automatic merge commit (pre-merge-commit hook); "
                             "implies --staged-only")
    parser.add_argument("--audit-branch", action="store_true",
                        help="audit a branch's changes since its merge-base "
                             "with the core ref (the default without "
                             "--staged-only / --merge-commit)")
    parser.add_argument("--repo", default=None,
                        help="audit the checked-out commit of this clone "
                             "(fetched into refs/gc-audit/<agent> here)")
    parser.add_argument("--ref", default=None,
                        help="audit this ref of the current repo (default HEAD)")
    parser.add_argument("--json", action="store_true",
                        help="print the branch-audit report as JSON")
    parser.add_argument("--notify", action="store_true",
                        help="write a scope-violation notice to the audited "
                             "agent and each owner (shared_state/notices/)")
    args = parser.parse_args()
    if args.merge_commit:
        args.staged_only = True

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

    if not args.staged_only:
        sys.exit(_run_branch_audit(args, topology))

    allow, deny = load_rules(args.agent)

    # Use `-z` (null-terminated) to get raw paths without any quoting.
    # Default `git diff --name-only` wraps paths containing spaces or
    # non-ASCII chars in double-quotes with C-style escapes inside, which
    # then fail prefix matching against UTF-8 allow rules. Combined with
    # core.quotepath=false this eliminates both quoting and octal escapes.
    try:
        raw = run("git -c core.quotepath=false diff --cached --name-only -z")
    except subprocess.CalledProcessError:
        print("[FATAL] git diff --cached failed.")
        sys.exit(1)
    files = [p for p in raw.split("\0") if p]

    if not files:
        print("[OK] No file changes detected.")
        return

    # Core history (config upstream_branch / core_branches); the first ref
    # that resolves is the authoritative core content (P-0131).
    core_refs = load_core_refs()
    core_ref = core_refs[0] if core_refs else None

    violations = []

    for f in files:
        f = f.replace("\\", "/")
        # Shared governance files reach agent branches through core merges.
        # Identical to core, they are not an agent-owned modification.
        if (
                f.startswith("agent_rules/")
                or f == "tools/check_scope.py"
                or f == "tools/print_startup_pack.ps1"
        ):
            if same_as_core(f, args.staged_only, core_ref):
                continue

        if is_under(f, deny):
            violations.append((f, "DENY(shared)"))
        elif not is_under(f, allow):
            violations.append((f, "OUT_OF_SCOPE"))

    # During merge commits a scope-external file passes when it is core
    # content (identical to the core ref), or when it is staged exactly as
    # the merged-in commit has it AND no merged-in commit outside core
    # history touched it. A file another agent's commits brought in, or one
    # changed while resolving the merge, stays a violation (P-0131).
    imported_foreign = False
    if violations and in_merge():
        foreign = foreign_import_commits(core_refs)
        filtered = []
        for f, reason in violations:
            if same_as_core(f, args.staged_only, core_ref):
                continue
            if f in foreign:
                commits = foreign[f]
                more = f" +{len(commits) - 1} more" if len(commits) > 1 else ""
                filtered.append((f, f"IMPORTED_OUT_OF_SCOPE: {commits[0]}{more}"))
                imported_foreign = True
            elif not same_as_merge_head(f):
                filtered.append((f, reason))
        skipped = len(violations) - len(filtered)
        if skipped:
            print(f"[INFO] Merge detected: {skipped} scope-external file(s) "
                  f"imported from core history (allowed)")
        violations = filtered

    # Automatic merge commit: MERGE_HEAD does not exist yet, so only files
    # identical to the core ref can be recognized as imports here. Defer the
    # rest to the pre-commit gate instead of judging them.
    if violations and args.merge_commit:
        pending = [(f, r) for f, r in violations
                   if not same_as_core(f, True, core_ref)]
        if pending:
            print(f"\n[DEFER] Automatic merge commit stopped: {len(pending)} "
                  f"scope-external file(s) not identical to "
                  f"{core_ref or 'any core ref'}:\n")
            for f, reason in pending:
                print(f"  - {f:60s}  [{reason}]")
            print("\nThe merge is staged and not committed. Conclude it with")
            print("  git commit --no-edit")
            print("(the pre-commit gate allows files identical to the merged-in")
            print("commit), or abandon it with: git merge --abort")
            sys.exit(1)
        violations = []

    if violations:
        print("\n[FAIL] Scope violations detected:\n")
        for f, reason in violations:
            print(f"  - {f:60s}  [{reason}]")
        print("\nAction:")
        print("  - Move changes into allowed directories")
        print("  - OR submit proposal for shared modules")
        if imported_foreign:
            print("  - IMPORTED_OUT_OF_SCOPE: the merge brings in commits that are "
                  "not in core history")
            print(f"    ({', '.join(core_refs) or 'no core ref resolves'}). "
                  "Cross-agent changes reach this branch through core.")
            print("    If those commits are already on the core branch, fetch it "
                  "(git fetch) and retry.")
        sys.exit(1)

    print("[PASS] All modified files are within allowed scope.")


def notify_violations(report: dict, project_root: Path = ROOT) -> list:
    """Write a scope-violation alert to the audited agent and to every owner
    of a violating path (contracts/shared_state_ownership.md §5). Returns
    the (agent, notice id) pairs written."""
    from governance_core import ownership
    shared = ownership.shared_root(project_root)
    me = ownership.topology(project_root)["self"]
    by_agent: dict = {}
    for v in report["violations"]:
        for agent in [report["agent"], *v["owners"]]:
            by_agent.setdefault(agent, []).append(v)
    written = []
    for agent, items in by_agent.items():
        commits = sorted({c for v in items for c in v["commits"]})
        detail = (f"branch audit of {report['agent']} @ {report['ref']} "
                  f"(rules from {report['core_ref']}): "
                  f"{len(items)} out-of-scope change(s)")
        nid = ownership.write_notice(
            shared, agent, kind="scope-violation", severity="alert", frm=me,
            paths=[v["path"] for v in items], commits=commits, detail=detail)
        written.append((agent, nid))
    return written


def _run_branch_audit(args, topology: dict) -> int:
    """Run the branch audit for main(); return the exit code (0/1/2)."""
    core_refs = load_core_refs()
    if not core_refs:
        print("[FATAL] no core ref resolves here (config upstream_branch / "
              "core_branches); fetch the core branch first")
        return 2
    others = [a["name"] for a in topology["agents"]
              if a["name"] not in (topology["core"], args.agent)]
    try:
        if args.repo:
            ref = fetch_clone_head(Path(args.repo).resolve(), args.agent)
        else:
            ref = args.ref or "HEAD"
        report = audit_branch(args.agent, ref, core_refs[0], others)
    except AuditError as exc:
        print(f"[FATAL] branch audit could not run: {exc}")
        return 2
    if args.json:
        print(json.dumps(report, ensure_ascii=False))
    else:
        _print_audit(report)
    if args.notify and report["violations"]:
        try:
            for agent, nid in notify_violations(report):
                if not args.json:
                    print(f"[NOTICE] {agent}: {nid}")
        except Exception as exc:  # noqa: BLE001 - the audit result stands
            print(f"[WARN] notices not written: {exc}", file=sys.stderr)
    return 1 if report["violations"] else 0


if __name__ == "__main__":
    main()
