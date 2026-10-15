# -*- coding: utf-8 -*-
"""Tests for sender-anchored cross-agent handoff linkage (`handoff_to`).

Covers the five surfaces of the mechanism:
  - proposal_suggest.handoff_targets(): scope owners inferred from a draft's
    description minus the drafting agent, with the per-token co-owner skip
  - audit_proposals open-handoff check: a `handoff_to: X` stays a standing
    WARN until closed (X implemented the proposal itself, or an X-owned
    proposal lists it in `related`)
  - audit_proposals missing-`handoff_to` backstop: a post-cutover in-flight
    draft whose title targets another agent's exclusive scope
  - session-context "Open handoffs to you" surface
  - the writer: proposal_lib `link --handoff-to` / `--clear-handoff`

The first 28 cases are the consumer's reference suite from #139; the cases
under "hub adaptations" and "writer" cover the hub's changes to it.

Temp files only; no live corpus, ledger or git history required. Agent names
are synthetic (alpha / beta / gamma) -- the mechanism is topology-agnostic.

Run from repo root:
    python -m pytest tools/test_handoff_linkage.py -q
"""
import subprocess
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
import proposal_suggest as ps  # noqa: E402
import audit_proposals as ap  # noqa: E402
import proposal_lib as pl  # noqa: E402

# alpha and beta each own one exclusive directory; every agent co-owns contracts/.
AMAP = {
    "alpha": ["alpha_dir", "contracts"],
    "beta": ["beta_dir", "contracts"],
    "gamma": ["gamma_dir", "contracts"],
}


def _write(d: Path, nnnn: str, agent: str, *, status: str = "draft",
           handoff_to: str = "", related: str = "", created: str = "2030-01-02",
           title: str = "x") -> Path:
    """Write a schema-shaped proposal; `related` is the raw frontmatter value."""
    d.mkdir(parents=True, exist_ok=True)
    extra = ""
    if handoff_to:
        extra += f"\nhandoff_to: {handoff_to}"
    if related:
        extra += f"\nrelated: {related}"
    path = d / f"p-{nnnn}-x.md"
    path.write_text(
        f"---\nid: P-{nnnn}\nagent: {agent}\nstatus: {status}\n"
        f"created: {created}{extra}\nowner: {agent}\n---\n\n"
        f"# Proposal P-{nnnn}: {title}\n\n## Trigger\n\nx\n\n## State Log\n\n"
        f"- {created}: draft created by {agent} agent (P-{nnnn})\n",
        encoding="utf-8",
    )
    return path


def _index(files: list) -> dict:
    return ap._build_proposal_index(
        {"in-flight": files, "archive": [], "legacy": []})


# --- handoff_targets --------------------------------------------------------

def test_targets_other_agents_exclusive_scope():
    assert ps.handoff_targets(
        "tune the threshold in beta_dir/engine.py", "alpha", AMAP) == ["beta"]


def test_targets_empty_for_self_scope():
    assert ps.handoff_targets(
        "refactor alpha_dir/engine.py", "alpha", AMAP) == []


def test_targets_skip_token_the_drafter_co_owns():
    # contracts/ is owned by every agent, including the drafter: not a handoff.
    assert ps.handoff_targets(
        "extend contracts/widget_schema.md", "alpha", AMAP) == []


def test_targets_co_owned_token_does_not_mask_exclusive_one():
    assert ps.handoff_targets(
        "extend contracts/widget_schema.md and beta_dir/reader.py",
        "alpha", AMAP) == ["beta"]


def test_targets_sorted_and_deduped_across_tokens():
    assert ps.handoff_targets(
        "gamma_dir/a.py beta_dir/b.py beta_dir/c.py", "alpha", AMAP
    ) == ["beta", "gamma"]


def test_targets_empty_without_per_agent_allow_files():
    # Single-agent topology: no allow map, so the inference stays silent.
    assert ps.handoff_targets("tune beta_dir/engine.py", "alpha", {}) == []


def test_targets_empty_for_prose_without_path_tokens():
    # The detectability floor: a behaviour recommendation naming no path.
    assert ps.handoff_targets(
        "relax the premium cap for new entries", "alpha", AMAP) == []


# --- open-handoff check -----------------------------------------------------

def test_open_handoff_warns_until_closed(tmp_path):
    origin = _write(tmp_path, "0001", "alpha", status="pending", handoff_to="beta")
    warnings = ap._check_open_handoffs(_index([origin]))
    assert len(warnings) == 1
    assert "P-0001" in warnings[0] and "beta" in warnings[0]


def test_open_handoff_closed_by_target_owned_backlink(tmp_path):
    origin = _write(tmp_path, "0001", "alpha", status="pending", handoff_to="beta")
    impl = _write(tmp_path, "0002", "beta", related="[P-0001]")
    assert ap._check_open_handoffs(_index([origin, impl])) == []


def test_open_handoff_not_closed_by_third_agent_backlink(tmp_path):
    origin = _write(tmp_path, "0001", "alpha", status="pending", handoff_to="beta")
    other = _write(tmp_path, "0002", "gamma", related="[P-0001]")
    assert len(ap._check_open_handoffs(_index([origin, other]))) == 1


def test_open_handoff_not_closed_by_senders_own_backlink(tmp_path):
    origin = _write(tmp_path, "0001", "alpha", status="pending", handoff_to="beta")
    follow_up = _write(tmp_path, "0002", "alpha", related="[P-0001]")
    assert len(ap._check_open_handoffs(_index([origin, follow_up]))) == 1


@pytest.mark.parametrize("status", ["implemented", "superseded", "upstreamed"])
def test_open_handoff_closed_when_target_finished_it_itself(tmp_path, status):
    own = _write(tmp_path, "0001", "beta", status=status, handoff_to="beta")
    assert ap._check_open_handoffs(_index([own])) == []


def test_open_handoff_stays_open_when_sender_owned_proposal_is_implemented(tmp_path):
    # Known residual: fulfilled in place under the sender's own proposal.
    origin = _write(tmp_path, "0001", "alpha", status="implemented",
                    handoff_to="beta")
    assert len(ap._check_open_handoffs(_index([origin]))) == 1


def test_no_handoff_field_no_warning(tmp_path):
    plain = _write(tmp_path, "0001", "alpha", related="[P-0009]")
    assert ap._check_open_handoffs(_index([plain])) == []


def test_backlink_in_another_region_closes(tmp_path):
    origin = _write(tmp_path / "flight", "0001", "alpha", status="pending",
                    handoff_to="beta")
    impl = _write(tmp_path / "archive", "0002", "beta", status="implemented",
                  related="[P-0001]")
    index = ap._build_proposal_index(
        {"in-flight": [origin], "archive": [impl], "legacy": []})
    assert ap._check_open_handoffs(index) == []


# --- missing-handoff_to backstop --------------------------------------------

@pytest.fixture
def allow_dir(tmp_path, monkeypatch):
    """A synthetic `<repo_root>/agent_rules/` (the backstop reads it from --root)."""
    d = tmp_path / "agent_rules"
    d.mkdir()
    for agent, prefixes in AMAP.items():
        (d / f"{agent}.allow.txt").write_text(
            "\n".join(f"{p}/**" for p in prefixes) + "\n", encoding="utf-8")
    monkeypatch.setattr(ap, "HANDOFF_CUTOVER", "2030-01-01")
    return d


def _backstop(tmp_path: Path, files: list) -> list:
    return ap._check_missing_handoff_to(_index(files), files, tmp_path)


def test_backstop_warns_on_cross_scope_title_without_field(tmp_path, allow_dir):
    draft = _write(tmp_path / "p", "0001", "alpha",
                   title="tune the threshold in beta_dir/engine.py")
    warnings = _backstop(tmp_path, [draft])
    assert len(warnings) == 1
    assert "P-0001" in warnings[0] and "beta" in warnings[0]


def test_backstop_silent_when_field_is_set(tmp_path, allow_dir):
    draft = _write(tmp_path / "p", "0001", "alpha", handoff_to="beta",
                   title="tune the threshold in beta_dir/engine.py")
    assert _backstop(tmp_path, [draft]) == []


def test_backstop_silent_for_self_scope_title(tmp_path, allow_dir):
    draft = _write(tmp_path / "p", "0001", "alpha",
                   title="refactor alpha_dir/engine.py")
    assert _backstop(tmp_path, [draft]) == []


def test_backstop_grandfathers_pre_cutover_proposals(tmp_path, allow_dir):
    old = _write(tmp_path / "p", "0001", "alpha", created="2029-12-31",
                 title="tune the threshold in beta_dir/engine.py")
    assert _backstop(tmp_path, [old]) == []


@pytest.mark.parametrize("status",
                         ["implemented", "superseded", "upstreamed", "rejected"])
def test_backstop_skips_terminal_proposals(tmp_path, allow_dir, status):
    done = _write(tmp_path / "p", "0001", "alpha", status=status,
                  title="tune the threshold in beta_dir/engine.py")
    assert _backstop(tmp_path, [done]) == []


# --- session surface --------------------------------------------------------

def _hook_path() -> Path:
    """session-context.py in the package-source or the installed layout."""
    for candidate in (_HERE.parent / "hooks" / "session-context.py",
                      _HERE.parent / ".claude" / "hooks" / "session-context.py"):
        if candidate.is_file():
            return candidate
    pytest.skip("session-context.py not found next to tools/")


def _surface(root: Path, role: str) -> str:
    """Call the hook's _check_open_handoffs in a subprocess.

    The hook rewraps sys.stdout at import time, so it is loaded in a child
    interpreter rather than inside the test process.
    """
    code = (
        "import importlib.util, sys\n"
        "spec = importlib.util.spec_from_file_location('sc', sys.argv[1])\n"
        "mod = importlib.util.module_from_spec(spec)\n"
        "spec.loader.exec_module(mod)\n"
        "sys.stdout.write(mod._check_open_handoffs(sys.argv[2], sys.argv[3]))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code, str(_hook_path()), str(root), role],
        capture_output=True, timeout=60)
    assert result.returncode == 0, result.stderr.decode("utf-8", "replace")
    return result.stdout.decode("utf-8", "replace")


def _layout(tmp_path: Path) -> tuple:
    """(repo root, in-flight dir for alpha, in-flight dir for beta, archive dir)."""
    root = tmp_path / "repo"
    shared = tmp_path / "shared_state" / "proposals"
    return (root, shared / "alpha", shared / "beta",
            root / "proposals" / "_archive" / "2030")


def test_surface_lists_open_handoff_for_the_target_only(tmp_path):
    root, alpha_dir, _beta_dir, _archive = _layout(tmp_path)
    root.mkdir(parents=True)
    _write(alpha_dir, "0001", "alpha", status="pending", handoff_to="beta")
    assert "P-0001 (from alpha)" in _surface(root, "beta")
    assert _surface(root, "alpha") == ""
    assert _surface(root, "gamma") == ""


def test_surface_clears_once_the_target_back_links(tmp_path):
    root, alpha_dir, beta_dir, _archive = _layout(tmp_path)
    root.mkdir(parents=True)
    _write(alpha_dir, "0001", "alpha", status="pending", handoff_to="beta")
    _write(beta_dir, "0002", "beta", related="[P-0001]")
    assert _surface(root, "beta") == ""


def test_surface_sees_a_back_link_in_the_archive(tmp_path):
    root, alpha_dir, _beta_dir, archive = _layout(tmp_path)
    _write(alpha_dir, "0001", "alpha", status="pending", handoff_to="beta")
    _write(archive, "0002", "beta", status="implemented", related="[P-0001]")
    assert _surface(root, "beta") == ""


# --- hub adaptations (P-0128 Phase B) ---------------------------------------

def test_rejected_handoff_is_closed(tmp_path):
    # A declined recommendation owes nothing.
    origin = _write(tmp_path, "0001", "alpha", status="rejected", handoff_to="beta")
    assert ap._check_open_handoffs(_index([origin])) == []


def test_open_handoff_warning_names_check_and_writer(tmp_path):
    origin = _write(tmp_path, "0001", "alpha", status="pending", handoff_to="beta")
    (warning,) = ap._check_open_handoffs(_index([origin]))
    assert warning.startswith("Check 19:") and "link" in warning


def test_backstop_reads_allow_files_under_root_not_module(tmp_path, monkeypatch):
    # --root must redirect the allow map: no agent_rules/ under root -> silent,
    # even though the drafted title names another agent's directory.
    monkeypatch.setattr(ap, "HANDOFF_CUTOVER", "2030-01-01")
    draft = _write(tmp_path / "p", "0001", "alpha",
                   title="tune the threshold in beta_dir/engine.py")
    assert _backstop(tmp_path, [draft]) == []


def test_backstop_skips_undated_created(tmp_path, allow_dir):
    draft = _write(tmp_path / "p", "0001", "alpha", created="someday",
                   title="tune the threshold in beta_dir/engine.py")
    assert _backstop(tmp_path, [draft]) == []


def test_index_tolerates_missing_fields(tmp_path):
    path = tmp_path / "p-0001-x.md"
    path.write_text("---\nid: P-0001\n---\n\nbody\n", encoding="utf-8")
    info = _index([path])["P-0001"]
    assert info["status"] == "draft" and info["related"] == []
    assert info["agent"] == "" and info["handoff_to"] == ""


def test_surface_closes_rejected_handoff(tmp_path):
    root, alpha_dir, _beta_dir, _archive = _layout(tmp_path)
    root.mkdir(parents=True)
    _write(alpha_dir, "0001", "alpha", status="rejected", handoff_to="beta")
    assert _surface(root, "beta") == ""


def test_surface_reads_in_repo_shared_state(tmp_path):
    # Single-repo layout: shared_state/ lives inside the repo root.
    root = tmp_path / "repo"
    _write(root / "shared_state" / "proposals" / "alpha", "0001", "alpha",
           status="pending", handoff_to="beta")
    assert "P-0001 (from alpha)" in _surface(root, "beta")


def test_surface_ignores_body_lines(tmp_path):
    # `handoff_to:` in the body is prose, not frontmatter.
    root, alpha_dir, _beta_dir, _archive = _layout(tmp_path)
    root.mkdir(parents=True)
    path = _write(alpha_dir, "0001", "alpha", status="pending")
    path.write_text(path.read_text(encoding="utf-8") + "\nhandoff_to: beta\n",
                    encoding="utf-8")
    assert _surface(root, "beta") == ""


# --- writer: proposal_lib link --handoff-to / --clear-handoff ----------------

@pytest.fixture
def repo(tmp_path, monkeypatch):
    """Proposals on disk with proposal_lib's discovery/config pointed at them."""
    paths = {"P-0001": _write(tmp_path, "0001", "alpha", status="pending"),
             "P-0002": _write(tmp_path, "0002", "beta")}
    monkeypatch.setattr(pl, "find_by_id", lambda pid: paths[pid] if pid in paths else None)
    monkeypatch.setattr(pl, "_agents", lambda: ["alpha", "beta", "gamma"])
    monkeypatch.setattr(pl, "_read_ledger", lambda: {
        "version": "1.0.0", "next_id": 3, "entries": []})
    monkeypatch.setattr(pl, "_lock_path", lambda: tmp_path / ".lock")
    monkeypatch.setattr(pl, "_lock_timeout", lambda: 5)
    return paths


def test_set_handoff_writes_field_and_state_log(repo):
    path, changed = pl.set_handoff_to("P-0001", "beta")
    fm, body = pl.parse_proposal(path)
    assert changed and fm["handoff_to"] == "beta"
    assert "handoff_to set to beta" in body


def test_set_handoff_output_is_seen_by_check19(repo):
    pl.set_handoff_to("P-0001", "beta")
    assert len(ap._check_open_handoffs(_index(list(repo.values())))) == 1
    pl.link_proposal("P-0002", ["P-0001"])  # beta back-links -> closed
    assert ap._check_open_handoffs(_index(list(repo.values()))) == []


def test_set_handoff_is_idempotent(repo):
    pl.set_handoff_to("P-0001", "beta")
    before = repo["P-0001"].read_text(encoding="utf-8")
    _, changed = pl.set_handoff_to("P-0001", "beta")
    assert not changed and repo["P-0001"].read_text(encoding="utf-8") == before


def test_set_handoff_change_and_clear(repo):
    pl.set_handoff_to("P-0001", "beta")
    pl.set_handoff_to("P-0001", "gamma")
    fm, body = pl.parse_proposal(repo["P-0001"])
    assert fm["handoff_to"] == "gamma" and "changed beta -> gamma" in body
    _, changed = pl.set_handoff_to("P-0001", None)
    fm, body = pl.parse_proposal(repo["P-0001"])
    assert changed and "handoff_to" not in fm and "cleared (was gamma)" in body


@pytest.mark.parametrize("target,needle", [
    ("delta", "not a configured agent"),
    ("alpha", "own agent"),
])
def test_set_handoff_rejects_bad_target(repo, target, needle):
    before = repo["P-0001"].read_text(encoding="utf-8")
    with pytest.raises(ValueError) as exc:
        pl.set_handoff_to("P-0001", target)
    assert needle in str(exc.value)
    assert repo["P-0001"].read_text(encoding="utf-8") == before


def test_cli_bad_handoff_leaves_related_unwritten(repo, capsys):
    before = repo["P-0001"].read_text(encoding="utf-8")
    rc = pl.main(["link", "--id", "P-0001", "--related", "P-0002",
                  "--handoff-to", "delta"])
    assert rc == 1 and repo["P-0001"].read_text(encoding="utf-8") == before


def test_cli_link_requires_some_change(repo):
    assert pl.main(["link", "--id", "P-0001"]) == 2


def test_create_hint_names_writer_and_is_ascii_marked(tmp_path, monkeypatch, capsys):
    d = tmp_path / "agent_rules"
    d.mkdir()
    for agent, prefixes in AMAP.items():
        (d / f"{agent}.allow.txt").write_text(
            "\n".join(f"{p}/**" for p in prefixes) + "\n", encoding="utf-8")
    monkeypatch.setattr(pl, "REPO_ROOT", tmp_path)
    pl._emit_handoff_suggestion("tune beta_dir/engine.py", "alpha", "P-0001")
    out = capsys.readouterr().out
    assert "[HANDOFF]" in out
    assert "link --id P-0001 --handoff-to beta" in out


def test_create_hint_silent_without_allow_files(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(pl, "REPO_ROOT", tmp_path)
    pl._emit_handoff_suggestion("tune beta_dir/engine.py", "alpha", "P-0001")
    assert capsys.readouterr().out == ""
