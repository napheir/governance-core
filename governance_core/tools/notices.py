#!/usr/bin/env python3
"""List or acknowledge shared_state ownership notices (P-0135).

Usage:
    python tools/notices.py list [--agent X | --all]
    python tools/notices.py ack <id> [--agent X]

A notice tells an agent, and its owner, that someone else changed the
agent's shared_state content or that core's branch audit found a scope
violation (contracts/shared_state_ownership.md §5). Alerts repeat at every
SessionStart until acked. **Ack an alert only when the owner says so.**
An agent may ack its own notices; the core agent may ack any.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from governance_core import ownership

ROOT = Path(__file__).resolve().parents[1]


def _out(line: str) -> None:
    sys.stdout.write(line + "\n")


def main(argv=None) -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--project-root", default=str(ROOT))
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("list", help="un-acked notices")
    p.add_argument("--agent", default=None, help="default: this clone's agent")
    p.add_argument("--all", action="store_true", help="every agent")
    p = sub.add_parser("ack", help="acknowledge one notice (owner's word only)")
    p.add_argument("id")
    p.add_argument("--agent", default=None, help="default: this clone's agent")
    args = parser.parse_args(argv)

    root = Path(args.project_root).resolve()
    try:
        topo = ownership.topology(root)
    except ownership.OwnershipError as exc:
        sys.stderr.write(f"[FAIL] {exc}\n")
        return 2
    shared = ownership.shared_root(root)
    me = topo["self"]
    if args.cmd == "list":
        agents = topo["agents"] if args.all else [args.agent or me]
        total = 0
        for agent in agents:
            for n in ownership.list_notices(shared, agent):
                total += 1
                _out(f"[{n['severity']}] {agent} {n['id']}: {n['kind']} from "
                     f"{n['from']} -- {', '.join(n['paths'])}"
                     + (f" ({n['detail']})" if n["detail"] else ""))
        if not total:
            _out("[OK] no un-acked notices")
        return 0
    agent = args.agent or me
    if agent != me and me != topo["core"]:
        sys.stderr.write(f"[FAIL] notices of {agent} can be acked by {agent} or "
                         f"the core agent; this clone is {me}\n")
        return 1
    try:
        ownership.ack_notice(shared, agent, args.id, me)
    except ownership.OwnershipError as exc:
        sys.stderr.write(f"[FAIL] {exc}\n")
        return 1
    _out(f"[OK] acked {args.id} for {agent} (by {me})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
