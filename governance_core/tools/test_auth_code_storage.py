"""Authorization code storage, migration and install-time revocation (P-0132).

The code used to live in `.governance/config.json` (`authorization.auth_code`),
a git-tracked file -- which published the hub's own code in its public
repository. It now lives in the gitignored `.governance/auth_code`; config.json
keeps the non-secret consumer_id. An upgrade migrates a code still in
config.json and keeps that copy until `--remove-config-auth-code` (clones of a
multi-clone project still on an older version read it there). install also
checks the revocation feed once and refuses a revoked code.

The storage cases run the real `installer.install()` with only the signature
check stubbed; the revocation cases sign real codes and feeds with a
throwaway key.

Run from repo root:
    python -m pytest tools/test_auth_code_storage.py -q
"""
from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path

import pytest

from governance_core import auth, installer
from governance_core.auth import codec, revocation, store

AGENTS = [{"name": "core", "branch": "master", "clone_dir": "agent-core"}]


def _clone(tmp_path: Path) -> Path:
    clone = tmp_path / "proj" / "agent-core"
    clone.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", "-b", "master", str(clone)], check=True)
    return clone


def _install(clone: Path, code: str | None = "stub", **kwargs) -> int:
    """Run a real install (or, with preserve_config, an upgrade)."""
    return installer.install(clone, config_overrides={
        "project_name": "proj", "core_agent_name": "core", "agents": AGENTS,
        "shared_state_root": str(clone.parent / "shared_state"),
    }, auth_code=code, accept_candidate_uplink=True, **kwargs)


def _config(clone: Path) -> dict:
    return json.loads((clone / ".governance" / "config.json").read_text(
        encoding="utf-8"))


@pytest.fixture
def stub_verify(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub only the signature check (codes here are not signed)."""
    monkeypatch.setattr(installer.codec, "verify_auth_code",
                        lambda code, key: {"consumer_id": "test-consumer"})


def test_fresh_install_keeps_code_only_in_gitignored_file(tmp_path: Path,
                                                          stub_verify) -> None:
    clone = _clone(tmp_path)
    assert _install(clone) == 0
    assert store.read_code(clone) == "stub"
    authorization = _config(clone)["authorization"]
    assert "auth_code" not in authorization
    assert authorization["consumer_id"] == "test-consumer"
    ignored = subprocess.run(["git", "-C", str(clone), "check-ignore", "-q",
                              store.AUTH_CODE_REL])
    assert ignored.returncode == 0, "code file is not gitignored"


def _pre_049_clone(tmp_path: Path) -> Path:
    """A clone as installed before 0.49: the code only in config.json."""
    clone = _clone(tmp_path)
    assert _install(clone) == 0
    store.code_path(clone).unlink()
    cfg = _config(clone)
    cfg["authorization"] = {"auth_code": "stub-legacy",
                            "consumer_id": "test-consumer",
                            "verified_at": "2026-05-18T00:00:00Z"}
    (clone / ".governance" / "config.json").write_text(json.dumps(cfg),
                                                       encoding="utf-8")
    return clone


def test_upgrade_migrates_config_code_and_keeps_the_copy(
        tmp_path: Path, stub_verify, caplog: pytest.LogCaptureFixture) -> None:
    clone = _pre_049_clone(tmp_path)
    assert _install(clone, code=None, preserve_config=True) == 0
    assert store.read_code(clone) == "stub-legacy"
    authorization = _config(clone)["authorization"]
    assert authorization["auth_code"] == "stub-legacy"  # older clones read it
    assert authorization["verified_at"] == "2026-05-18T00:00:00Z"  # unchanged code
    caplog.set_level(logging.WARNING)
    installer.doctor(clone)
    assert "still stored in" in caplog.text


def test_remove_config_auth_code_drops_the_copy(tmp_path: Path,
                                                stub_verify) -> None:
    clone = _pre_049_clone(tmp_path)
    assert _install(clone, code=None, preserve_config=True) == 0
    assert _install(clone, code=None, preserve_config=True,
                    remove_config_auth_code=True) == 0
    assert "auth_code" not in _config(clone)["authorization"]
    assert store.read_code(clone) == "stub-legacy"


def test_new_code_replaces_the_file_but_not_the_config_copy(
        tmp_path: Path, stub_verify) -> None:
    """install --auth-code NEW writes the file; config.json is never given a code."""
    clone = _pre_049_clone(tmp_path)
    assert _install(clone, code="stub-new", preserve_config=True) == 0
    assert store.read_code(clone) == "stub-new"
    assert _config(clone)["authorization"]["auth_code"] == "stub-legacy"


def test_store_round_trip_and_empty_file(tmp_path: Path) -> None:
    assert store.read_code(tmp_path) is None
    store.write_code(tmp_path, "  GC1.a.b \n")
    assert store.code_path(tmp_path).read_bytes() == b"GC1.a.b\n"
    assert store.read_code(tmp_path) == "GC1.a.b"
    store.code_path(tmp_path).write_text("\n", encoding="utf-8")
    with pytest.raises(store.AuthStoreError):
        store.read_code(tmp_path)


# --- install-time revocation check (P-0132 Phase B) -----------------------

def _signed_setup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                  revoke_code: bool) -> tuple[Path, str]:
    """A test key the installer trusts, a signed feed, and a code naming it."""
    seed = auth.generate_seed()
    monkeypatch.setattr(installer.codec, "load_bundled_public_key",
                        lambda: auth.public_key_from_seed(seed))
    feed_dir = tmp_path / "feed"
    feed_dir.mkdir()
    feed_path = feed_dir / "revocation.json"
    payload = codec.canonical_payload(
        "acme", "2026-11-05", "2099-01-01", schema=2,
        revocation_feed_url=feed_path.as_uri(), max_offline_days=30)
    code = codec.make_auth_code(payload, seed)
    feed = revocation.new_feed()
    if revoke_code:
        feed = revocation.add_revocation(feed, "acme", "leaked",
                                         code_sha256=codec.code_fingerprint(code))
    revocation.write_feed(feed_path, feed_dir / "revocation.json.sig", feed, seed)
    return _clone(tmp_path), code


def test_per_code_install_refuses_a_revoked_code(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    clone, code = _signed_setup(tmp_path, monkeypatch, revoke_code=True)
    assert _install(clone, code=code) == 7
    assert store.read_code(clone) is None


def test_per_code_install_accepts_a_clean_code(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    clone, code = _signed_setup(tmp_path, monkeypatch, revoke_code=False)
    assert _install(clone, code=code) == 0
    assert store.read_code(clone) == code


def test_per_code_install_proceeds_when_feed_unreachable(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    clone, code = _signed_setup(tmp_path, monkeypatch, revoke_code=True)
    (tmp_path / "feed" / "revocation.json").unlink()
    assert _install(clone, code=code) == 0
