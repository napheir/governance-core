"""Files merged in from core are not drift (deva-vani report, 2026-11-06).

In a multi-clone project, core upgrades and commits the gc-managed files.
A business clone then receives the new contents through a git merge, but
its installed_files.json (untracked) still holds the previous version's
baselines. _capture_drift compared only against the baseline, so the
clone's next upgrade packaged every merged-in file as a candidate-common
drift candidate: deva-vani's 3 business clones accumulated 72, each one
ready for `candidate.py sweep` to post as a public hub issue. A file whose
content already equals what the upgrade writes is not a local edit.

The stale-baseline state is reproduced exactly: a real install, then every
manifest baseline rewritten to the hash of a previous version, which is
what the business clone's manifest holds after the merge. Runs the real
installer.install() code path; only the auth-code signature check is
stubbed (the gate needs a maintainer-signed code).

Run from repo root:
    python -m pytest tools/test_installer_drift_merged_upstream.py -q
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from governance_core import installer
from governance_core.candidates import collect, envelope

HOOK = ".claude/hooks/auth-guard.py"
CLAUSE = f"{installer.CLAUSES_REL}/art_00_ritual.md"
OLD_BASELINE = hashlib.sha256(b"previous version\n").hexdigest()


@pytest.fixture()
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An installed project with the auth-code signature check stubbed."""
    monkeypatch.setattr(installer.codec, "verify_auth_code",
                        lambda code, key: {"consumer_id": "test-consumer"})
    root = tmp_path / "proj"
    root.mkdir()
    assert _install(root) == 0
    return root


def _install(root: Path) -> int:
    """Run a real install / upgrade into `root`."""
    return installer.install(
        root,
        config_overrides={"project_name": "proj", "ritual_phrase": "OK"},
        auth_code="stub", accept_candidate_uplink=True,
    )


def _stale_manifest(root: Path) -> list[str]:
    """Rewrite every baseline to a previous version's; return the paths."""
    path = root / installer.INSTALLED_FILES_REL
    manifest = json.loads(path.read_text(encoding="utf-8"))
    for entry in manifest["files"]:
        entry["baseline_sha256"] = OLD_BASELINE
        entry["source_version"] = "0.0.1"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return [entry["path"] for entry in manifest["files"]]


def _config(root: Path) -> dict:
    """The project's config.json, as install passes it to _capture_drift."""
    return json.loads((root / installer.CONFIG_REL).read_text(encoding="utf-8"))


def _drift_targets(root: Path) -> set[str]:
    """drift_target of every drift envelope in the outbox."""
    outbox = collect.outbox_dir(root)
    targets = set()
    for cj in outbox.glob(f"*/{envelope.CANDIDATE_JSON}"):
        meta = json.loads(cj.read_text(encoding="utf-8"))
        if "drift_target" in meta:
            targets.add(meta["drift_target"])
    return targets


def test_merged_upstream_files_are_not_drift(project: Path) -> None:
    """Stale baselines, current == incoming: no drift, no envelope."""
    paths = _stale_manifest(project)
    assert HOOK in paths and CLAUSE in paths
    hook = project / HOOK  # merged in by a clone on core.autocrlf=true
    lf = hook.read_bytes().replace(b"\r\n", b"\n")
    hook.write_bytes(lf.replace(b"\n", b"\r\n"))

    assert installer._capture_drift(project, "test-consumer", _config(project),
                                    dry_run=True) == []
    assert _install(project) == 0
    assert _drift_targets(project) == set()


def test_rendered_clause_compared_as_rendered(project: Path) -> None:
    """A generic clause carries the project's ritual phrase, not the
    package placeholder; it still counts as the incoming version."""
    _stale_manifest(project)
    text = (project / CLAUSE).read_text(encoding="utf-8")
    assert "OK" in text and "如君所愿" not in text
    drifted = installer._capture_drift(project, "test-consumer",
                                       _config(project), dry_run=True)
    assert CLAUSE not in drifted


def test_local_edit_among_merged_files_is_captured(project: Path) -> None:
    """Only the file edited locally is drift; the merged-in ones are not."""
    _stale_manifest(project)
    (project / HOOK).write_text("# local edit\n", encoding="utf-8")
    assert _install(project) == 0
    assert _drift_targets(project) == {HOOK}


def test_vendored_auth_maps_to_auth_source() -> None:
    """.claude/hooks/_gc_auth/ is the vendored auth/ package, not hooks/."""
    src = installer._pkg_source_path(".claude/hooks/_gc_auth/store.py")
    assert src == installer.PKG_ROOT / "auth" / "store.py"
    assert src.is_file()


def test_local_edit_with_current_baseline_still_captured(project: Path) -> None:
    """Unchanged behavior: an edit against an up-to-date baseline is drift."""
    (project / HOOK).write_text("# local edit\n", encoding="utf-8")
    assert _install(project) == 0
    assert _drift_targets(project) == {HOOK}
