"""tools/upgrade_review.py -- deterministic upgrade drift-risk pre-pass.

Runs the governance-core upgrade dry-run, classifies the drift risk
mechanically, and writes a structured report. It **never applies** the upgrade
(read-only). A consumer's scheduled routine (or a human) runs this; on
YELLOW/RED an LLM semantic review of each drift diff can be added before
pinging the operator. Apply always stays a human action -- this tool only
surfaces risk, it never decides.

Verdicts (also printed to stdout, machine-readable for a routine):
  NONE   -- already up to date (version X -> X)
  GREEN  -- new version, zero drift, no cross-minor -> "ready; say `upgrade`"
  YELLOW -- new version with drift (local edits would be reverted) -> review
  RED    -- drift touches a protected-local-fix path (the upgrade would revert
            a fix the consumer deliberately keeps), or a cross-minor jump with
            drift -> the operator must look before applying.

A `protected_drift.json` ({"paths": [...]}) next to the report lists
gc-managed files the consumer deliberately keeps as local drift (re-applied
each upgrade until gc promotes the fix). A drift on such a path -> RED: the
upgrade would silently revert it.

Exit code is always 0 -- this is a review tool, not a gate.
"""
from __future__ import annotations

import datetime as _dt
import json
import logging
import os
import re
import subprocess
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="[upgrade-review] %(message)s")
log = logging.getLogger("upgrade_review")

REPO = Path(__file__).resolve().parent.parent
REPORT_DIR = REPO / "audit" / "upgrade_review"
# gc-managed files the consumer deliberately keeps as local drift (re-applied
# each upgrade until gc promotes the fix). A drift here -> RED: upgrade reverts.
PROTECTED_DRIFT_FILE = REPORT_DIR / "protected_drift.json"


def run_dryrun() -> str:
    """Run `governance-core upgrade --dry-run` and return its combined output.

    Forces UTF-8 decoding so a Windows GBK console does not corrupt the report
    text the regexes below parse.
    """
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    r = subprocess.run(
        ["governance-core", "upgrade", "--project-root", str(REPO), "--dry-run"],
        capture_output=True, text=True, env=env, encoding="utf-8",
        errors="replace",
    )
    return (r.stdout or "") + (r.stderr or "")


def parse(report: str) -> dict:
    """Extract version delta, cross-minor flag, and drifted paths from output."""
    ver = re.search(r"version:\s*([0-9][0-9.]*)\s*->\s*([0-9][0-9.]*)", report)
    cur, inc = (ver.group(1), ver.group(2)) if ver else (None, None)
    cross_minor = bool(re.search(r"crosses\s+\d+\s+minor", report))
    drift = sorted(set(re.findall(r"drift diff:\s*(.+?)\s*---", report)))
    return {"current": cur, "incoming": inc, "cross_minor": cross_minor,
            "drift": drift}


def load_protected() -> list[str]:
    """Return the consumer's protected-drift path list (empty if none)."""
    if PROTECTED_DRIFT_FILE.is_file():
        try:
            data = json.loads(PROTECTED_DRIFT_FILE.read_text(encoding="utf-8"))
            return [p for p in data.get("paths", []) if isinstance(p, str)]
        except (OSError, json.JSONDecodeError):
            return []
    return []


def classify(info: dict, protected: list[str]) -> tuple[str, list[str]]:
    """Map parsed dry-run info + protected list to a verdict + reasons.

    Verdict contract (see module docstring):
      NONE   -- up to date
      GREEN  -- new version, zero drift, no cross-minor
      YELLOW -- new version with drift, or a cross-minor jump (review needed)
      RED    -- drift on a protected-local-fix path, or a cross-minor jump
                that also carries drift (breaking changes + lost local edits)
    """
    if not info["current"] or info["current"] == info["incoming"]:
        return "NONE", ["already up to date"]
    reasons: list[str] = []
    drift = info["drift"]
    if drift:
        reasons.append(f"{len(drift)} drift file(s): " + ", ".join(drift))
    hit_protected = [d for d in drift if d in protected]
    for d in hit_protected:
        reasons.append(
            f"drift on protected local fix `{d}` -- upgrade would revert it")
    if info["cross_minor"]:
        reasons.append(
            "crosses minor version line(s) -- review contracts/breaking")
    if hit_protected or (info["cross_minor"] and drift):
        return "RED", reasons
    if drift or info["cross_minor"]:
        return "YELLOW", reasons
    return "GREEN", ["new version, zero drift -- ready; say `upgrade` to apply"]


def main() -> int:
    """Run the dry-run, classify, write the report, print the verdict."""
    info = parse(run_dryrun())
    verdict, reasons = classify(info, load_protected())
    ts = _dt.datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    md = (
        f"# upgrade-review {ts}\n\n"
        f"- verdict: **{verdict}**\n"
        f"- version: {info['current']} -> {info['incoming']}\n"
        f"- drift files: {info['drift'] or 'none'}\n\n"
        "## reasons\n" + "\n".join(f"- {r}" for r in reasons) + "\n\n"
        "_Deterministic pre-pass. On YELLOW/RED a routine can add an LLM "
        "semantic review of each drift diff before pinging the operator. NEVER "
        "auto-applies; apply is a human action._\n"
    )
    (REPORT_DIR / f"{ts}.md").write_text(md, encoding="utf-8")
    log.info("verdict=%s version=%s->%s drift=%d", verdict, info["current"],
             info["incoming"], len(info["drift"]))
    sys.stdout.write(verdict + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
