"""Validate a candidate envelope directory (P-0065 Phase 3).

Checks a candidate envelope against the format spec: candidate.json present
and well-formed (schema, kind, layer, required keys, drift-field
consistency) and every declared payload path on disk.

Usage:
    python tools/validate_candidate.py <envelope-dir>

Exit codes:
    0 = valid   1 = invalid   2 = usage error
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from governance_core.candidates import envelope


def main() -> int:
    """Validate one candidate envelope directory and report the verdict."""
    parser = argparse.ArgumentParser(prog="validate_candidate")
    parser.add_argument("envelope_dir",
                        help="path to a candidate envelope directory")
    args = parser.parse_args()

    path = Path(args.envelope_dir)
    if not path.is_dir():
        sys.stderr.write(f"[validate_candidate] not a directory: {path}\n")
        return 2

    try:
        meta = envelope.validate_envelope(path)
    except envelope.EnvelopeError as exc:
        sys.stderr.write(f"[validate_candidate] INVALID: {exc}\n")
        return 1

    sys.stdout.write(
        f"[validate_candidate] OK: {meta['id']} kind={meta['kind']} "
        f"layer={meta['layer']} origin={meta['origin']} "
        f"payload={len(meta['source_paths'])}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
