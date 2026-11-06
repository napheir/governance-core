"""Shared utilities for the PreToolUse guards (scope / edit-write / data-source).

Every guard needs:
  - agent identity: which agent owns the clone this hook is installed in
  - block() helper that prints a uniform banner to stderr + exit 2
  - cross-repo path patterns (the project's other clones)

Identity (P-0129) is derived from .governance/config.json, NOT from the git
branch: the clone directory name is matched against agents[].clone_dir, and a
single-agent config resolves to its only agent. Identity therefore does not
change when a clone checks out another branch, and needs no git call. An
identity that cannot be resolved (config missing / malformed, clone not
registered) raises TopologyError; detect_role() maps it to UNRESOLVED_ROLE,
which guards treat as the most restricted role -- the 0.45.x fallback
"unknown branch -> core" granted full authority to every agent of a consumer
whose roles were absent from a hard-coded upstream table.

Stdlib-only and self-contained: fail-closed hooks must not import
governance_core (knowledge/governance/runtime-import-discipline.md). Tools
that need the agent identity (proposal_lib, regen_constitution, the
pre-commit gate) load THIS file by path, so there is one implementation.

Sync: this file is in sync_infra.ALWAYS_COPY_FILES, so every clone has
its own copy (each guard resolves _REPO_ROOT relative to its own clone).
"""
import json
import os
import sys

# Role token for the agent named by config core_agent_name (governance
# authority: guards bypass their scope layers for it).
CORE_ROLE = "core"

# Role token for a clone whose identity cannot be resolved. No allow-list
# file can carry this name, so it is denied everything a role needs rules for.
UNRESOLVED_ROLE = "<unresolved>"


class TopologyError(Exception):
    """This clone's agent identity cannot be resolved from config.json."""


def hook_repo_root() -> str:
    """Return the root of the repo this module is installed in.

    Installed layout: <repo>/.claude/hooks/_guard_common.py. Package-source
    layout: <repo>/governance_core/hooks/_guard_common.py. Both are two
    levels below the repo root.
    """
    return os.path.normpath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
    )


def _root(repo_root: str) -> str:
    """Absolute, normalized `repo_root`; empty means the repo this module lives in.

    abspath matters for a relative argument: normpath('.') keeps '.', whose
    basename is '' -- identity would always be unresolved for detect_role('.').
    """
    return os.path.normpath(os.path.abspath(repo_root or hook_repo_root()))


def load_topology(repo_root: str) -> dict:
    """Load the agent topology from <repo_root>/.governance/config.json.

    Returns {"agents": [<agent dict>, ...], "core": <core_agent_name>}; each
    agent dict has at least non-empty str "name" and "clone_dir".

    Raises:
        TopologyError: config missing / unreadable / not an object, a
            required field missing or ill-typed, or core_agent_name not
            among agents[].name. Membership is tested explicitly (no
            fallback defaults, Art.4).
    """
    cfg_path = os.path.join(repo_root, ".governance", "config.json")
    try:
        with open(cfg_path, encoding="utf-8") as f:
            cfg = json.load(f)
    except FileNotFoundError:
        raise TopologyError(f"config not found: {cfg_path}") from None
    except (OSError, ValueError) as exc:
        raise TopologyError(f"config unreadable: {cfg_path} ({exc})") from None
    if not isinstance(cfg, dict):
        raise TopologyError(f"config is not a JSON object: {cfg_path}")
    for key in ("agents", "core_agent_name"):
        if key not in cfg:
            raise TopologyError(f"config has no '{key}': {cfg_path}")
    agents = cfg["agents"]
    if not isinstance(agents, list) or not agents:
        raise TopologyError(f"config 'agents' must be a non-empty list: {cfg_path}")
    for agent in agents:
        if (not isinstance(agent, dict)
                or "name" not in agent or "clone_dir" not in agent
                or not isinstance(agent["name"], str)
                or not isinstance(agent["clone_dir"], str)
                or not agent["name"] or not agent["clone_dir"]):
            raise TopologyError(
                f"config agents[] entry needs non-empty 'name' and "
                f"'clone_dir': {agent!r}"
            )
    core = cfg["core_agent_name"]
    if core not in {a["name"] for a in agents}:
        raise TopologyError(
            f"core_agent_name {core!r} is not one of agents[].name"
        )
    return {"agents": agents, "core": core}


def _resolve(root: str) -> tuple:
    """Return (agent name, topology) for the clone at normalized `root`."""
    topo = load_topology(root)
    agents = topo["agents"]
    if len(agents) == 1:
        return agents[0]["name"], topo
    clone = os.path.basename(root).lower()
    for agent in agents:
        if agent["clone_dir"].lower() == clone:
            return agent["name"], topo
    registered = ", ".join(a["clone_dir"] for a in agents)
    raise TopologyError(
        f"clone directory '{os.path.basename(root)}' is not registered in "
        f"config agents[].clone_dir ({registered})"
    )


def resolve_agent(repo_root: str = "") -> str:
    """Return the agent name that owns the clone at `repo_root`.

    Rules, in order: a single-agent config -> its only agent; otherwise the
    agent whose clone_dir equals the clone directory name (case-insensitive).

    Args:
        repo_root: clone root; empty -> the repo this module is installed in.

    Raises:
        TopologyError: identity cannot be resolved (see load_topology).
    """
    return _resolve(_root(repo_root))[0]


def detect_role(repo_root: str = "") -> str:
    """Return the guard role for the clone at `repo_root`.

    CORE_ROLE for the config's core agent, the agent name for any other
    agent, UNRESOLVED_ROLE when identity cannot be resolved (fail-closed:
    the caller treats it as the most restricted role).

    Args:
        repo_root: clone root; empty -> the repo this module is installed in
            (the hook's own clone, never the process cwd).
    """
    try:
        name, topo = _resolve(_root(repo_root))
    except TopologyError:
        return UNRESOLVED_ROLE
    return CORE_ROLE if name == topo["core"] else name


def identity_failure(repo_root: str = "") -> str:
    """Return why identity resolution fails for `repo_root` ("" if it works)."""
    try:
        _resolve(_root(repo_root))
    except TopologyError as exc:
        return str(exc)
    return ""


def sibling_clone_patterns(repo_root: str = "") -> list:
    """Return Bash cross-repo block patterns for this project's other clones.

    For each other non-core clone <c> sitting next to this clone under the
    project directory <p>: '<p>/<c>' (matches absolute paths in Windows and
    POSIX drive forms, and ../../<p>/<c>) and '../<c>' (sibling-relative).
    Lowercased, '/'-separated, matched as substrings of the normalized
    command. Derived from the real clone location, so it holds whether
    config install_root names the project's parent or the clones' parent
    (P-0129 F7).

    The core clone is not listed: business clones legitimately reference
    core (centrally referenced hooks / tools) -- the policy of the original
    literal table, unchanged. Edit/Write into core stays blocked by
    edit-write-guard's path-prefix check. Returns [] when the topology is
    unresolvable; detect_role() reports that failure to the guard.
    """
    root = _root(repo_root)
    try:
        topo = load_topology(root)
    except TopologyError:
        return []
    own = os.path.basename(root).lower()
    project = os.path.basename(os.path.dirname(root)).lower()
    patterns = []
    for agent in topo["agents"]:
        clone = agent["clone_dir"].lower()
        if agent["name"] == topo["core"] or clone == own:
            continue
        patterns.append(f"{project}/{clone}")
        patterns.append(f"../{clone}")
    return patterns


# Cross-repo patterns blocked for non-core agents. shared_state/ is
# intentionally absent: writes there are judged per path by
# shared_state_access() below (P-0135).
CROSS_REPO_PATTERNS = sibling_clone_patterns()


# ---------------------------------------------------------------------------
# shared_state ownership (P-0135; contracts/shared_state_ownership.md §2).
# Every agent's partitions are proposals/<agent>/** plus the config
# `shared_state_partitions` templates; ledger, lock, journal and notices
# (plus config `shared_state_lib_only`) are written only by the libs.
# ---------------------------------------------------------------------------

PROPOSAL_PARTITION = "proposals/{agent}/**"
LIB_ONLY_PATTERNS = ("proposals/_id_ledger.json*", "_journal*", "notices/**")


def _config(repo_root: str) -> dict:
    """The clone's config.json as a dict ({} when unreadable)."""
    try:
        with open(os.path.join(repo_root, ".governance", "config.json"),
                  encoding="utf-8") as f:
            cfg = json.load(f)
    except (OSError, ValueError):
        return {}
    return cfg if isinstance(cfg, dict) else {}


def _str_list(cfg: dict, key: str) -> list:
    """Optional list-of-str config value ([] when absent or ill-typed)."""
    value = cfg[key] if key in cfg else []
    if not isinstance(value, list):
        return []
    return [v.replace("\\", "/").strip("/") for v in value
            if isinstance(v, str) and v.strip()]


def native_path(path: str) -> str:
    """`path` with a Git Bash drive prefix (/c/...) turned into C:/... on Windows."""
    if os.name == "nt" and len(path) >= 3 and path[0] == "/" and path[2] == "/" \
            and path[1].isalpha():
        return f"{path[1]}:/{path[3:]}"
    return path


def shared_state_root(repo_root: str = "") -> str:
    """Absolute shared_state root of the project (config `shared_state_root`).

    Falls back to the historical layout `<clone>/../shared_state` only when the
    config does not name one, so a malformed config never turns the guard off.
    """
    root = _root(repo_root)
    cfg = _config(root)
    value = cfg["shared_state_root"] if "shared_state_root" in cfg else None
    if isinstance(value, str) and value.strip():
        path = native_path(value.strip())
        if not os.path.isabs(path):
            path = os.path.join(root, path)
        return os.path.normpath(path)
    return os.path.normpath(os.path.join(root, "..", "shared_state"))


def _matches(rel: str, pattern: str) -> bool:
    """`pattern` (`dir/**`, or an fnmatch glob) matches shared_state-relative `rel`.

    Case-insensitive on Windows, like the file system there.
    """
    import fnmatch
    if os.name == "nt":
        rel, pattern = rel.lower(), pattern.lower()
    if pattern.endswith("/**"):
        prefix = pattern[:-3]
        return rel == prefix or rel.startswith(prefix + "/")
    return fnmatch.fnmatchcase(rel, pattern)


def partition_patterns(agent: str, repo_root: str = "") -> list:
    """shared_state-relative patterns of `agent`'s partitions."""
    templates = [PROPOSAL_PARTITION] + _str_list(_config(_root(repo_root)),
                                                 "shared_state_partitions")
    return [t.replace("{agent}", agent) for t in templates]


def shared_state_access(target: str, role: str, repo_root: str = "") -> tuple:
    """Classify a write to absolute path `target` by agent `role`.

    Returns (kind, rel): kind is "outside" (not under shared_state), "own"
    (one of `role`'s partitions), "lib-only" (ledger / lock / journal /
    notices / config shared_state_lib_only: libs only), "foreign" (another
    agent's partition; rel names it) or "other" (any other shared_state
    path). rel is the path relative to the shared_state root, '/'-separated.
    """
    root = _root(repo_root)
    base = os.path.normpath(os.path.abspath(shared_state_root(root)))
    tgt = os.path.normpath(os.path.abspath(native_path(target)))
    base_cmp, tgt_cmp = os.path.normcase(base), os.path.normcase(tgt)
    if tgt_cmp != base_cmp and not tgt_cmp.startswith(base_cmp + os.sep):
        return "outside", ""
    rel = tgt[len(base):].lstrip("\\/").replace("\\", "/")
    lib_only = list(LIB_ONLY_PATTERNS) + _str_list(_config(root), "shared_state_lib_only")
    if any(_matches(rel, p) for p in lib_only):
        return "lib-only", rel
    if any(_matches(rel, p) for p in partition_patterns(role, root)):
        return "own", rel
    try:
        names = [a["name"] for a in load_topology(root)["agents"]]
    except TopologyError:
        names = []
    for name in names:
        if name != role and any(_matches(rel, p)
                                for p in partition_patterns(name, root)):
            return "foreign", rel
    return "other", rel


def block(guard_name: str, reason: str, detail: str) -> None:
    """Print a uniform block banner to stderr and sys.exit(2).

    Both guards use the same banner format so user sees a consistent
    diagnostic regardless of which guard fired.
    """
    sys.stderr.write("\n")
    sys.stderr.write("=========================================\n")
    sys.stderr.write(f"[{guard_name}] {reason}\n")
    sys.stderr.write("=========================================\n")
    sys.stderr.write("\n")
    sys.stderr.write(detail + "\n")
    sys.stderr.write("\n")
    sys.exit(2)


def own_repo_pattern(hook_file: str) -> str:
    """Return the cross-repo pattern matching the hook's own repo.

    Used by scope-guard to skip blocking when a Bash command references
    its own clone (which is legitimate; only OTHER clones are off-limits).

    Args:
        hook_file: __file__ of the calling hook script.
    """
    # Hook lives at <repo>/.claude/hooks/<name>.py
    repo_root = os.path.normpath(
        os.path.join(os.path.dirname(os.path.abspath(hook_file)), "..", "..")
    )
    install_root_name = os.path.basename(os.path.dirname(repo_root)).lower()
    return f"{install_root_name}/{os.path.basename(repo_root).lower()}"
