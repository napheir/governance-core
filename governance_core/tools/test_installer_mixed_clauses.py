"""Mixed clauses survive repeated installs (P-0129 Phase B, F2).

0.45.x recorded the 7 MIXED_CLAUSES in installed_files.json on first install;
the next install skipped the existing copies, so _prune_stale saw "recorded
before, not produced now" and deleted them (deva-vani lost all 7 in every
clone). Mixed clauses are now business-owned from birth: rendered only when
absent, never recorded, never drift-captured, never pruned -- including for a
project whose manifest a pre-0.46 install already polluted.

Runs the real installer.install() code path; only the auth-code signature
check is stubbed (the gate needs a maintainer-signed code).

Run from repo root:
    python -m pytest tools/test_installer_mixed_clauses.py -q
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from governance_core import installer

CLAUSES = installer.CLAUSES_REL
MIXED = sorted(installer.MIXED_CLAUSES)


@pytest.fixture()
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An empty project dir with the auth-code signature check stubbed."""
    monkeypatch.setattr(installer.codec, "verify_auth_code",
                        lambda code, key: {"consumer_id": "test-consumer"})
    root = tmp_path / "proj"
    root.mkdir()
    return root


def _install(root: Path) -> int:
    """Run a real install / upgrade into `root`."""
    return installer.install(
        root,
        config_overrides={"project_name": "proj", "ritual_phrase": "OK"},
        auth_code="stub", accept_candidate_uplink=True,
    )


def _manifest_paths(root: Path) -> set[str]:
    """Paths recorded in installed_files.json."""
    manifest = json.loads(
        (root / installer.INSTALLED_FILES_REL).read_text(encoding="utf-8"))
    return {f["path"] for f in manifest["files"]}


def test_mixed_clauses_survive_second_install(project: Path) -> None:
    assert _install(project) == 0
    assert _install(project) == 0
    for name in MIXED:
        assert (project / CLAUSES / name).is_file(), name


def test_mixed_clauses_never_recorded_in_manifest(project: Path) -> None:
    assert _install(project) == 0
    recorded = _manifest_paths(project)
    for name in MIXED:
        assert f"{CLAUSES}/{name}" not in recorded, name
    # generic clauses stay install-managed
    assert f"{CLAUSES}/art_00_ritual.md" in recorded


def test_project_edits_to_mixed_clause_are_kept(project: Path) -> None:
    assert _install(project) == 0
    clause = project / CLAUSES / "art_01_project_architecture.md"
    clause.write_text("# project-specific architecture\n", encoding="utf-8")
    assert _install(project) == 0
    assert clause.read_text(encoding="utf-8") == "# project-specific architecture\n"


def test_upgrade_from_polluted_manifest_keeps_and_does_not_capture(project: Path) -> None:
    """A pre-0.46 manifest listing the mixed clauses: no prune, no drift."""
    assert _install(project) == 0
    clause = project / CLAUSES / "art_03_contracts.md"
    clause.write_text("# our contracts clause\n", encoding="utf-8")
    manifest_path = project / installer.INSTALLED_FILES_REL
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for name in MIXED:  # simulate what 0.45.x recorded on first install
        manifest["files"].append({
            "path": f"{CLAUSES}/{name}", "baseline_sha256": "0" * 64,
            "source_version": "0.45.1", "category": "clause"})
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    drifted = installer._capture_drift(project, "test-consumer", dry_run=True)
    assert not any(p.startswith(f"{CLAUSES}/") and p.split("/")[-1] in MIXED
                   for p in drifted), drifted
    assert _install(project) == 0
    for name in MIXED:
        assert (project / CLAUSES / name).is_file(), name
    assert clause.read_text(encoding="utf-8") == "# our contracts clause\n"
    assert not any(p.split("/")[-1] in MIXED
                   for p in _manifest_paths(project) if p.startswith(CLAUSES))


def test_deleted_mixed_clause_is_reseeded(project: Path) -> None:
    """A clause lost to the 0.45.x prune is re-seeded as a stub next install."""
    assert _install(project) == 0
    lost = project / CLAUSES / "art_10_artifacts_layout.md"
    lost.unlink()
    assert _install(project) == 0
    assert lost.is_file()
