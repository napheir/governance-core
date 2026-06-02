"""Tests for EOL-normalized manifest hashing in installer.py (P-0094, gc #27).

Verifies the CRLF-false-drift fix. A consumer on core.autocrlf=true checks out
install-managed files as CRLF while the package materializes LF; the old
raw-byte hashing reported essentially every text file as drift. `_content_sha256`
normalizes CRLF/CR -> LF at BOTH the manifest baseline (_write_installed_manifest)
and the drift-check (_capture_drift), so an EOL-only difference is not drift while
a genuine content edit still is.

Run from repo root:
    python -m pytest tools/test_installer_drift_eol.py -q
"""
from pathlib import Path

from governance_core import installer


# --- _content_sha256 unit behavior --------------------------------------------

def test_content_sha256_eol_insensitive(tmp_path: Path) -> None:
    """CRLF and LF of identical content hash equal."""
    lf = tmp_path / "lf.txt"
    crlf = tmp_path / "crlf.txt"
    lf.write_bytes(b"line one\nline two\n")
    crlf.write_bytes(b"line one\r\nline two\r\n")
    assert installer._content_sha256(lf) == installer._content_sha256(crlf)


def test_content_sha256_lone_cr_normalized(tmp_path: Path) -> None:
    """Defensive: a lone-CR (old-Mac) file normalizes to LF too."""
    lf = tmp_path / "lf.txt"
    cr = tmp_path / "cr.txt"
    lf.write_bytes(b"a\nb\n")
    cr.write_bytes(b"a\rb\r")
    assert installer._content_sha256(lf) == installer._content_sha256(cr)


def test_content_sha256_content_change_detected(tmp_path: Path) -> None:
    """A genuine (non-EOL) content edit changes the hash."""
    a = tmp_path / "a.txt"
    b = tmp_path / "b.txt"
    a.write_bytes(b"hello\nworld\n")
    b.write_bytes(b"hello\nWORLD\n")
    assert installer._content_sha256(a) != installer._content_sha256(b)


# --- end-to-end: manifest baseline + _capture_drift ---------------------------

def _seed_managed(project_root: Path, rel: str, data: bytes) -> Path:
    p = project_root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    return p


def test_capture_drift_crlf_no_op(tmp_path: Path) -> None:
    """A managed file re-checked-out as CRLF is NOT reported as drift."""
    managed = _seed_managed(tmp_path, ".claude/hooks/x.py", b"print('hi')\n")
    installer._write_installed_manifest(tmp_path, [(managed, "hook")])
    # simulate git autocrlf re-checkout: identical content, CRLF endings
    managed.write_bytes(b"print('hi')\r\n")
    drifted = installer._capture_drift(tmp_path, "test-consumer", dry_run=True)
    assert drifted == []


def test_capture_drift_genuine_edit_caught(tmp_path: Path) -> None:
    """A real (non-EOL) content edit IS reported as drift."""
    managed = _seed_managed(tmp_path, ".claude/hooks/x.py", b"print('hi')\n")
    installer._write_installed_manifest(tmp_path, [(managed, "hook")])
    managed.write_bytes(b"print('bye')\n")
    drifted = installer._capture_drift(tmp_path, "test-consumer", dry_run=True)
    assert drifted == [".claude/hooks/x.py"]


def test_baseline_and_drift_check_symmetric(tmp_path: Path) -> None:
    """Both sites use the same helper: a CRLF baseline matches an LF current
    (an asymmetry would reintroduce the false-drift mismatch)."""
    managed = _seed_managed(tmp_path, ".claude/hooks/x.py", b"a\r\nb\r\n")
    installer._write_installed_manifest(tmp_path, [(managed, "hook")])
    managed.write_bytes(b"a\nb\n")
    drifted = installer._capture_drift(tmp_path, "test-consumer", dry_run=True)
    assert drifted == []
