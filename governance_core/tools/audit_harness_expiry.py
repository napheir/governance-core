# -*- coding: utf-8 -*-
"""
tools/audit_harness_expiry.py - Harness component lifecycle audit
-----------------------------------------------------------------
Inspired by Anthropic's insight: "Every harness component is a hypothesis
about the current model's capability boundary. Hypotheses expire."

This tool reads harness_registry.json and checks:
1. Which components haven't been reviewed in >90 days
2. Which components have medium/high expiry likelihood (candidates for testing)
3. Overall harness health summary

Usage:
  python tools/audit_harness_expiry.py              # Standard report
  python tools/audit_harness_expiry.py --verbose     # Include notes and recommendations
  python tools/audit_harness_expiry.py --mark-reviewed <id>  # Update review date

The review process (manual, quarterly):
  1. Run this tool to identify overdue components
  2. For each overdue component with medium+ expiry likelihood:
     - Temporarily disable the hook
     - Run a representative workload
     - Check if quality degrades without the hook
  3. If no degradation: retire the component
  4. If degradation found: update last_reviewed date
"""
import io
import json
import os
import sys
from datetime import datetime

# Force UTF-8 output on Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

REGISTRY_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "harness_registry.json")
REVIEW_CYCLE_DAYS = 90

# Expiry likelihood ordering for sorting
EXPIRY_ORDER = {"none": 0, "low": 1, "medium": 2, "medium-high": 3, "high": 4}


def load_registry() -> dict:
    """Load harness registry from JSON."""
    with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_registry(registry: dict) -> None:
    """Save harness registry to JSON."""
    with open(REGISTRY_PATH, "w", encoding="utf-8") as f:
        json.dump(registry, f, indent=2, ensure_ascii=False)
        f.write("\n")


def days_since_review(last_reviewed: str) -> int:
    """Calculate days since last review."""
    last_date = datetime.strptime(last_reviewed, "%Y-%m-%d")
    return (datetime.now() - last_date).days


def check_file_exists(file_path: str) -> bool:
    """Check if hook file exists relative to project root."""
    return os.path.isfile(file_path)


def _expiry(comp: dict) -> str:
    """Extract expiry_likelihood from component dict."""
    return comp["expiry_likelihood"]


def _notes(comp: dict) -> str:
    """Extract notes from component dict."""
    return comp["notes"]


def audit_report(verbose: bool = False) -> int:
    """Generate harness expiry audit report. Returns number of issues found."""
    registry = load_registry()
    components = registry["components"]
    today = datetime.now().strftime("%Y-%m-%d")

    overdue = []
    candidates = []
    missing = []
    healthy = []

    for comp in components:
        days = days_since_review(comp["last_reviewed"])
        expiry = _expiry(comp)
        exists = check_file_exists(comp["file"])

        if not exists:
            missing.append(comp)
        elif days > REVIEW_CYCLE_DAYS:
            overdue.append((comp, days))
        elif EXPIRY_ORDER[expiry] >= 2:
            candidates.append(comp)
        else:
            healthy.append(comp)

    # --- Report ---
    sys.stdout.write(f"=== Harness Component Lifecycle Audit ({today}) ===\n\n")

    # Missing files
    if missing:
        sys.stdout.write(f"[FAIL] Missing hook files ({len(missing)}):\n")
        for comp in missing:
            sys.stdout.write(f"  - {comp['id']}: {comp['file']}\n")
        sys.stdout.write("\n")

    # Overdue reviews
    if overdue:
        sys.stdout.write(f"[WARN] Overdue for review ({len(overdue)}):\n")
        for comp, days in sorted(overdue, key=lambda x: x[1], reverse=True):
            expiry = _expiry(comp)
            sys.stdout.write(f"  - {comp['id']}: {days} days since review (expiry: {expiry})\n")
            if verbose:
                sys.stdout.write(f"    Hypothesis: {comp['hypothesis']}\n")
                action = "TEST removal" if EXPIRY_ORDER[expiry] >= 2 else "Re-review and update date"
                sys.stdout.write(f"    Action: {action}\n")
        sys.stdout.write("\n")

    # Retirement candidates (not overdue but medium+ expiry)
    if candidates:
        sys.stdout.write(f"[INFO] Retirement candidates - medium+ expiry likelihood ({len(candidates)}):\n")
        for comp in sorted(candidates, key=lambda c: EXPIRY_ORDER[_expiry(c)], reverse=True):
            expiry = _expiry(comp)
            days = days_since_review(comp["last_reviewed"])
            sys.stdout.write(f"  - {comp['id']}: expiry={expiry}, reviewed {days}d ago\n")
            if verbose:
                sys.stdout.write(f"    Hypothesis: {comp['hypothesis']}\n")
                sys.stdout.write(f"    Model assumption: {comp['model_assumption']}\n")
                sys.stdout.write(f"    Notes: {_notes(comp)}\n")
        sys.stdout.write("\n")

    # Healthy
    sys.stdout.write(f"[OK] Healthy components: {len(healthy)}\n")
    if verbose:
        for comp in healthy:
            days = days_since_review(comp["last_reviewed"])
            sys.stdout.write(f"  - {comp['id']}: reviewed {days}d ago, expiry={_expiry(comp)}\n")
    sys.stdout.write("\n")

    # Summary
    total = len(components)
    issues = len(missing) + len(overdue)
    sys.stdout.write(f"=== Summary: {total} components, {issues} issues, {len(candidates)} retirement candidates ===\n")

    # Architectural vs capability hooks
    arch_count = sum(1 for c in components if _expiry(c) == "none")
    cap_count = total - arch_count
    sys.stdout.write(f"  Architectural (never expire): {arch_count}\n")
    sys.stdout.write(f"  Capability-dependent (may expire): {cap_count}\n")

    if not issues and not candidates:
        max_days = max(days_since_review(c["last_reviewed"]) for c in components)
        sys.stdout.write(f"\n[PASS] All components healthy. Next review due in {REVIEW_CYCLE_DAYS - max_days}d.\n")
    elif issues:
        sys.stdout.write(f"\n[ACTION REQUIRED] {issues} component(s) need attention.\n")

    return issues


def mark_reviewed(component_id: str) -> None:
    """Update a component's last_reviewed date to today."""
    registry = load_registry()
    today = datetime.now().strftime("%Y-%m-%d")

    for comp in registry["components"]:
        if comp["id"] == component_id:
            old_date = comp["last_reviewed"]
            comp["last_reviewed"] = today
            save_registry(registry)
            sys.stdout.write(f"[OK] {component_id}: last_reviewed {old_date} -> {today}\n")
            return

    sys.stdout.write(f"[FAIL] Component '{component_id}' not found in registry.\n")
    sys.exit(1)


def main() -> None:
    """Entry point."""
    args = sys.argv[1:]

    if "--mark-reviewed" in args:
        idx = args.index("--mark-reviewed")
        if idx + 1 >= len(args):
            sys.stdout.write("Usage: --mark-reviewed <component-id>\n")
            sys.exit(1)
        mark_reviewed(args[idx + 1])
        return

    verbose = "--verbose" in args
    issues = audit_report(verbose)
    sys.exit(1 if issues else 0)


if __name__ == "__main__":
    main()
