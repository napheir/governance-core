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
import json
from pathlib import Path

from governance_core import installer
from governance_core.candidates import collect, envelope


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


# --- intentional-drift declaration (P-0117, #119) -----------------------------

def _write_intentional(project_root: Path, targets: list) -> None:
    gov = project_root / ".governance"
    gov.mkdir(parents=True, exist_ok=True)
    (gov / "intentional_drift.json").write_text(
        json.dumps({"schema": 1, "drift_targets": targets}), encoding="utf-8")


def test_load_intentional_drift_missing(tmp_path: Path) -> None:
    """No file -> empty set (fail-safe; identical to today's behavior)."""
    assert installer._load_intentional_drift(tmp_path) == set()


def test_load_intentional_drift_valid_normalizes_sep(tmp_path: Path) -> None:
    """Valid file -> declared paths, normalized to forward slashes."""
    _write_intentional(tmp_path, ["tools/x.py", "a\\b.py"])
    assert installer._load_intentional_drift(tmp_path) == {"tools/x.py", "a/b.py"}


def test_load_intentional_drift_malformed(tmp_path: Path) -> None:
    """Malformed JSON -> empty set (never breaks upgrade)."""
    gov = tmp_path / ".governance"
    gov.mkdir(parents=True, exist_ok=True)
    (gov / "intentional_drift.json").write_text("{not json", encoding="utf-8")
    assert installer._load_intentional_drift(tmp_path) == set()


def test_load_intentional_drift_wrong_schema(tmp_path: Path) -> None:
    """Unexpected schema -> empty set."""
    gov = tmp_path / ".governance"
    gov.mkdir(parents=True, exist_ok=True)
    (gov / "intentional_drift.json").write_text(
        json.dumps({"schema": 2, "drift_targets": ["x"]}), encoding="utf-8")
    assert installer._load_intentional_drift(tmp_path) == set()


def _drift_envelope_layers(project_root: Path) -> dict:
    """Map each built drift envelope's drift_target -> its stamped layer."""
    outbox = collect.outbox_dir(project_root)
    layers = {}
    for cj in outbox.glob(f"*/{envelope.CANDIDATE_JSON}"):
        meta = json.loads(cj.read_text(encoding="utf-8"))
        if "drift_target" in meta:
            layers[meta["drift_target"]] = meta["layer"]
    return layers


def test_capture_drift_stamps_business_for_declared(tmp_path: Path) -> None:
    """A declared drift is captured but stamped layer:business; an undeclared
    drift keeps candidate-common. Both envelopes are still built (safety net)."""
    keep = _seed_managed(tmp_path, ".claude/hooks/keep.py", b"orig\n")
    other = _seed_managed(tmp_path, ".claude/hooks/other.py", b"orig\n")
    installer._write_installed_manifest(
        tmp_path, [(keep, "hook"), (other, "hook")])
    keep.write_bytes(b"consumer permanent edit\n")   # intentional drift
    other.write_bytes(b"unrelated drift\n")           # normal drift
    _write_intentional(tmp_path, [".claude/hooks/keep.py"])

    drifted = installer._capture_drift(tmp_path, "test-consumer", dry_run=False)
    assert set(drifted) == {".claude/hooks/keep.py", ".claude/hooks/other.py"}

    layers = _drift_envelope_layers(tmp_path)
    assert layers[".claude/hooks/keep.py"] == "business"
    assert layers[".claude/hooks/other.py"] == "candidate-common"
