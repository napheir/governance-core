"""Hub-side: reject a candidate issue + append to rejected_registry.json.

When the maintainer judges an uplinked candidate to be business-layer
content (or otherwise unfit for the package), this tool packages the
reject into a durable, consumer-visible record:

  1. Fetches the issue body via `gh issue view`.
  2. Parses the embedded `### payload/<name>` fenced block using the
     same shared parser as P-0076 Phase 1 ledger recovery.
  3. Computes the payload's SHA-256 over the bytes the issue carries.
     For 0.8.0+ issues this matches the consumer's `payload_digest`;
     pre-0.8.0 issues had payload trailing whitespace stripped by an
     earlier `uplink.build_issue` so the digest is approximate -- the
     tool sets `block_by_name: true` in that case so the registry still
     blocks regardless of the consumer's exact bytes.
  4. Appends an entry to
     `governance_core/candidates/rejected_registry.json` (idempotent on
     issue url + skill name).
  5. With `--also-close`, posts the reason+advice as a comment and
     closes the issue as `not planned`.

Hub-only: lives under `maintainer/`, excluded from the wheel by the
`governance_core*` packages whitelist. Run from the governance-core
repository root.

Usage:
    python maintainer/reject_candidate.py \\
        --issue 4 \\
        --reason "Business-layer content. ..." \\
        --advice "Keep as a local learned skill in trade-agent. ..." \\
        [--also-close]
"""

from __future__ import annotations

import argparse
import datetime
import json
import logging
import subprocess
import sys
from pathlib import Path

from governance_core.candidates import ledger as _ledger
from governance_core.candidates import rejected as _rejected

logger = logging.getLogger("maintainer.reject_candidate")


def _gh_issue_view(issue: int, repo: str) -> dict:
    """Fetch issue title/body/url via `gh`. Raises CalledProcessError on failure."""
    argv = ["gh", "issue", "view", str(issue), "--repo", repo,
            "--json", "number,title,body,url,state"]
    result = subprocess.run(argv, capture_output=True, check=True)
    return json.loads(result.stdout.decode("utf-8", errors="replace"))


def _gh_close_with_comment(issue: int, repo: str, comment: str) -> None:
    """Post a comment then close the issue as `not planned`."""
    subprocess.run(["gh", "issue", "comment", str(issue), "--repo", repo,
                    "--body", comment], check=True)
    subprocess.run(["gh", "issue", "close", str(issue), "--repo", repo,
                    "--reason", "not planned"], check=True)


def _registry_diff(before: dict, after: dict) -> str:
    """Build a human-readable summary of registry changes."""
    before_keys = {(e["skill_name"],
                    e["payload_sha256"] if "payload_sha256" in e else None)
                   for e in before["rejected"]}
    after_keys = {(e["skill_name"],
                   e["payload_sha256"] if "payload_sha256" in e else None)
                  for e in after["rejected"]}
    added = after_keys - before_keys
    if not added:
        return "(no new entries -- idempotent or duplicate skipped)"
    lines = []
    for name, sha in added:
        lines.append(f"  + {name}  sha={sha or 'null'}")
    return "\n".join(lines)


def cmd_reject(args: argparse.Namespace) -> int:
    """Reject a candidate issue + append to rejected_registry.json."""
    repo = args.repo
    try:
        issue = _gh_issue_view(args.issue, repo)
    except FileNotFoundError:
        sys.stderr.write("[reject] `gh` CLI not found -- install GitHub CLI\n")
        return 2
    except subprocess.CalledProcessError as exc:
        sys.stderr.write(
            f"[reject] gh issue view failed: "
            f"{exc.stderr.decode('utf-8', errors='replace').strip()}\n")
        return 2

    body = issue["body"] if "body" in issue else ""
    try:
        meta, payload = _ledger.parse_payload_from_issue_body(body)
    except (ValueError, json.JSONDecodeError) as exc:
        sys.stderr.write(f"[reject] issue #{args.issue} body could not be "
                         f"parsed: {exc}\n")
        return 2

    if "origin" not in meta or "title" not in meta:
        sys.stderr.write(f"[reject] issue #{args.issue} candidate.json "
                         f"missing 'origin' or 'title'\n")
        return 2

    skill_name = meta["title"]
    origin = meta["origin"]
    digest = _ledger._hash_payload(list(payload.items()))

    # Pre-0.8.0 detection: heuristic on whether the parsed payload ends
    # with a newline. Older uplink.build_issue used .rstrip(), so an
    # rstripped payload almost certainly does NOT end in '\n'. The
    # caller can override.
    pre_080 = args.legacy_rstrip or (
        not args.legacy_rstrip_no
        and all(not b.endswith(b"\n") for b in payload.values()))

    registry_path = _rejected.registry_path()
    before = _rejected.load_rejected_registry()

    # Idempotent: same (skill_name, digest) skipped
    for entry in before["rejected"]:
        existing_sha = (entry["payload_sha256"]
                        if "payload_sha256" in entry else None)
        if (entry["skill_name"] == skill_name
                and existing_sha is not None and existing_sha == digest):
            sys.stdout.write(f"[reject] entry for {skill_name} sha={digest} "
                             f"already present -- nothing to add\n")
            if args.also_close:
                _close_with_advisory(args, issue)
            return 0

    new_entry = {
        "rejected_at": datetime.date.today().isoformat(),
        "skill_name": skill_name,
        "payload_sha256": None if pre_080 else digest,
        "block_by_name": pre_080,
        "origin": origin,
        "issue_urls": [issue["url"] if "url" in issue else ""],
        "reason": args.reason,
        "advice": args.advice,
    }

    # If a name-match entry already exists, fold this issue url into it
    # rather than adding a duplicate entry.
    merged_into_existing = False
    for entry in before["rejected"]:
        if entry["skill_name"] != skill_name:
            continue
        if "issue_urls" not in entry:
            entry["issue_urls"] = []
        if new_entry["issue_urls"][0] not in entry["issue_urls"]:
            entry["issue_urls"].append(new_entry["issue_urls"][0])
            entry["rejected_at"] = new_entry["rejected_at"]
        merged_into_existing = True
        break
    if not merged_into_existing:
        before["rejected"].append(new_entry)
    after = before
    after["updated"] = datetime.datetime.now(
        datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    if args.dry_run:
        sys.stdout.write(
            f"[reject] DRY RUN -- would add entry to {registry_path}:\n"
            f"  skill_name:     {new_entry['skill_name']}\n"
            f"  payload_sha256: {new_entry['payload_sha256']}\n"
            f"  block_by_name:  {new_entry['block_by_name']}\n"
            f"  origin:         {new_entry['origin']}\n"
            f"  issue_urls:     {new_entry['issue_urls']}\n"
            f"  reason:         {new_entry['reason'][:80]}...\n"
            f"  advice:         {new_entry['advice'][:80]}...\n"
            f"(pre-0.8.0 issue body detected: {pre_080})\n")
        return 0

    registry_path.write_text(
        json.dumps(after, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8")
    sys.stdout.write(f"[reject] registry updated: {registry_path}\n")
    sys.stdout.write(_registry_diff(
        {"rejected": [e for e in before["rejected"]
                      if e is not new_entry][:len(before["rejected"]) - 0]},
        after) + "\n")

    if args.also_close:
        _close_with_advisory(args, issue)
    else:
        sys.stdout.write(
            f"[reject] issue #{args.issue} NOT closed (no --also-close). "
            "Close manually if desired.\n")
    return 0


def _close_with_advisory(args: argparse.Namespace, issue: dict) -> None:
    """Post the reason+advice comment then close the issue."""
    comment = (
        "Rejected by hub. Added to "
        "`governance_core/candidates/rejected_registry.json` "
        "(P-0076 Phase 2) so consumer-side sweep will surface the advice "
        "at the next session start / wrap-up.\n\n"
        f"**Reason**: {args.reason}\n\n"
        f"**Advice**: {args.advice}\n")
    try:
        _gh_close_with_comment(
            issue["number"], args.repo, comment)
        sys.stdout.write(f"[reject] issue #{issue['number']} closed + "
                         "comment posted\n")
    except subprocess.CalledProcessError as exc:
        sys.stderr.write(
            f"[reject] close-with-comment failed: "
            f"{exc.stderr.decode('utf-8', errors='replace').strip()}\n")


def main() -> int:
    """CLI entry point."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(
        prog="reject_candidate.py",
        description="Hub-side reject a candidate issue + register the "
                    "advisory in rejected_registry.json")
    parser.add_argument("--issue", type=int, required=True,
                        help="GitHub issue number to reject")
    parser.add_argument("--reason", required=True,
                        help="Why the candidate was rejected (consumer-visible)")
    parser.add_argument("--advice", required=True,
                        help="What the consumer's owner should do "
                             "(consumer-visible)")
    parser.add_argument("--repo", default="napheir/governance-core",
                        help="GitHub repo (default: napheir/governance-core)")
    parser.add_argument("--also-close", action="store_true",
                        help="Post the reason+advice as a comment and close "
                             "the issue as 'not planned'")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would change without writing")
    g = parser.add_mutually_exclusive_group()
    g.add_argument("--legacy-rstrip", action="store_true",
                   help="Force pre-0.8.0 mode: sha is approximate, set "
                        "block_by_name=true regardless of payload bytes")
    g.add_argument("--legacy-rstrip-no", action="store_true",
                   help="Force post-0.8.0 mode: sha is authoritative, "
                        "block_by_name=false unless --block-by-name set")
    args = parser.parse_args()
    return cmd_reject(args)


if __name__ == "__main__":
    sys.exit(main())
