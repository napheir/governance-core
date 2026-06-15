# -*- coding: utf-8 -*-
"""Proposal drafting suggestion helper (P-0097 / P-0100).

Read-only mechanical recall for the `/proposal classify` step. Given a free-text
requirement description, surfaces three kinds of drafting aids:

  ① 类似 proposal  — keyword overlap against the proposal corpus (in-flight +
                     archive + legacy) titles / slugs.
  ② 检查项 / 经验  — trigger-keyword hits against the git-tracked
                     knowledge/governance/proposal-drafting-checklist.md.
  ③ likely scope   — path / domain-alias tokens in the description matched
                     against agent_rules/*.allow.txt ownership.

Contract (P-0097):
  - Never mutates anything; never blocks. Each of the three sections emits an
    explicit `（无）` when nothing matches — NO silent empty.
  - Pure keyword recall: NO similarity ranking / embeddings (Non-Goals).
  - ② source is repo-tracked (NOT ~/.claude per-agent memory, which is
    machine-local / not cross-clone — see P-0097 ②数据源决策).
  - The drafting agent treats the output as candidates and decides; the helper
    does not conclude.

Pure functions take explicit roots/paths so they are unit-testable without the
real repo; `main()` wires the real corpus / checklist / agent_rules paths.

Run from repo root:
    python tools/proposal_suggest.py "<requirement description>"
    python tools/proposal_suggest.py --json "<description>"
    python tools/proposal_suggest.py --exclude P-0097 "<description>"
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Reuse proposal_lib's config-derived corpus roots (single source of truth).
sys.path.insert(0, str(REPO_ROOT / "tools"))
import proposal_lib as _pl  # noqa: E402

CHECKLIST_PATH = REPO_ROOT / "knowledge" / "governance" / "proposal-drafting-checklist.md"
ALLOW_DIR = REPO_ROOT / "agent_rules"

# Generic terms that would over-match in ① / ③ — dropped from token sets.
_STOPWORDS = {
    # English
    "proposal", "proposals", "the", "and", "for", "with", "this", "that", "from",
    "into", "add", "fix", "new", "use", "via", "per", "core", "agent", "agents",
    "skill", "skills", "todo", "txt", "via", "git",
    # Chinese bigrams (generic)
    "提案", "方案", "增加", "实现", "修改", "支持", "需要", "可以", "一个", "进行",
    "使用", "通过", "处理", "相关", "建议",
}

# Minimal NL-term -> path-token hints for ③. Domain-NEUTRAL structural aliases
# only (governance / infrastructure dirs that exist generically). Consumers
# extend this map with their own domain terms (e.g. a trading agent adds
# 回测->simu, 交易->trade, 信号->rules). The lookup mechanism is unchanged;
# only these data rows are project-specific.
_DOMAIN_ALIASES = {
    "宪法": "constitution", "constitution": "constitution",
    "契约": "contracts", "contract": "contracts",
    "钩子": ".claude", "hook": ".claude", "技能": ".claude", "slash": ".claude",
    "工具": "tools", "审计": "audit", "测试": "tests",
}


def out(line: str = "") -> None:
    """Write `line` + newline to stdout (constitution Art.7: no print)."""
    sys.stdout.write(line + "\n")


# ---------------------------------------------------------------------------
# Tokenization / matching primitives
# ---------------------------------------------------------------------------

def tokens(text: str) -> set:
    """Token set: ASCII words (len>=3) + CJK character bigrams, minus stopwords."""
    text = (text or "").lower()
    toks = set()
    for w in re.findall(r"[a-z0-9_]{3,}", text):
        if w not in _STOPWORDS:
            toks.add(w)
    for run in re.findall(r"[一-鿿]{2,}", text):
        for i in range(len(run) - 1):
            bg = run[i:i + 2]
            if bg not in _STOPWORDS:
                toks.add(bg)
    return toks


def kw_in(kw: str, desc: str) -> bool:
    """True if `kw` is present in `desc`.

    ASCII keywords match on word boundaries (case-insensitive); CJK keywords
    match as substrings.
    """
    kw = (kw or "").strip()
    if not kw:
        return False
    if kw.isascii():
        return re.search(r"\b" + re.escape(kw.lower()) + r"\b", (desc or "").lower()) is not None
    return kw in (desc or "")


def path_overlap(a: str, b: str) -> bool:
    """True if path `a` and `b` are segment-prefix-compatible (one ⊆ the other)."""
    aa = [s for s in a.strip("/").split("/") if s]
    bb = [s for s in b.strip("/").split("/") if s]
    if not aa or not bb:
        return False
    n = min(len(aa), len(bb))
    return aa[:n] == bb[:n]


# ---------------------------------------------------------------------------
# ① similar proposals
# ---------------------------------------------------------------------------

def _region_of(path: Path) -> str:
    s = str(path).replace("\\", "/")
    if "/shared_state/proposals/" in s:
        return "in-flight"
    if "/_archive/" in s:
        return "archive"
    return "legacy"


def corpus_files() -> list:
    """All proposal markdown files across in-flight / archive / legacy regions."""
    files = []
    inflight = _pl._in_flight_root()
    if inflight.exists():
        files += [p for p in inflight.glob("*/*.md")]
    archive = _pl._archive_root()
    if archive.exists():
        files += [p for p in archive.glob("*/*.md")]
    legacy = REPO_ROOT / "proposals"
    if legacy.exists():
        files += [p for p in legacy.glob("*.md")]
    return files


def corpus_entries(files: list) -> list:
    """Read each proposal file → {id, title, slug, region, blob}."""
    entries = []
    for path in files:
        try:
            head = path.read_text(encoding="utf-8", errors="ignore")[:2000]
        except OSError:
            continue
        slug = path.stem  # e.g. p-0091-todo_proposal_lifecycle_linkage
        m_id = re.search(r"^id:\s*(P-\d{4})", head, re.MULTILINE)
        if not m_id:
            m_id = re.search(r"(P-\d{4})", slug.upper())
        pid = m_id.group(1) if m_id else slug
        m_title = re.search(r"^title:\s*(.+)$", head, re.MULTILINE)
        if not m_title:
            m_title = re.search(r"^#\s+(?:Proposal\s+P-\d{4}:\s*)?(.+)$", head, re.MULTILINE)
        title = m_title.group(1).strip() if m_title else slug
        entries.append({
            "id": pid, "title": title, "slug": slug,
            "region": _region_of(path),
            "blob": title + " " + slug.replace("-", " ").replace("_", " "),
        })
    return entries


def score_corpus(desc_tokens: set, entries: list, *, min_score: int = 2,
                 limit: int = 5, exclude: str = "") -> list:
    """Rank corpus entries by shared-token count; keep score>=min_score, top `limit`."""
    scored = []
    for e in entries:
        if exclude and e["id"] == exclude:
            continue
        score = len(desc_tokens & tokens(e["blob"]))
        if score >= min_score:
            scored.append({**e, "score": score})
    scored.sort(key=lambda x: (-x["score"], x["id"]))
    return scored[:limit]


# ---------------------------------------------------------------------------
# ② checklist hits
# ---------------------------------------------------------------------------

def parse_checklist(path: Path) -> list:
    """Parse the fixed-format checklist into items with trigger/lesson/how/source."""
    items = []
    if not path.exists():
        return items
    text = path.read_text(encoding="utf-8", errors="ignore")
    # Split on level-3 headings; ignore preamble before the first one.
    blocks = re.split(r"^###\s+", text, flags=re.MULTILINE)[1:]
    for blk in blocks:
        lines = blk.splitlines()
        title = lines[0].strip() if lines else ""
        fields = {"触发": "", "教训": "", "怎么做": "", "来源": ""}
        for ln in lines[1:]:
            m = re.match(r"-\s*\*\*(触发|教训|怎么做|来源)\*\*\s*[:：]\s*(.*)$", ln.strip())
            if m:
                fields[m.group(1)] = m.group(2).strip()
        triggers = [t.strip() for t in re.split(r"[,，、]", fields["触发"]) if t.strip()]
        items.append({
            "title": title, "triggers": triggers,
            "lesson": fields["教训"], "how": fields["怎么做"], "source": fields["来源"],
        })
    return items


def checklist_hits(desc: str, items: list, *, limit: int = 6) -> list:
    """Items whose any trigger keyword is present in `desc`."""
    hits = []
    for item in items:
        if any(kw_in(kw, desc) for kw in item["triggers"]):
            hits.append(item)
    return hits[:limit]


# ---------------------------------------------------------------------------
# ③ likely scope
# ---------------------------------------------------------------------------

def load_allow_map(allow_dir: Path) -> dict:
    """{agent: [normalized owned path prefixes]} parsed from agent_rules/*.allow.txt."""
    amap = {}
    if not allow_dir.exists():
        return amap
    for f in sorted(allow_dir.glob("*.allow.txt")):
        agent = f.name.split(".")[0]
        if agent.startswith("shared"):
            continue
        prefixes = []
        for line in f.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            norm = line.replace("\\", "/").rstrip("*").rstrip("/")
            if norm:
                prefixes.append(norm)
        amap[agent] = prefixes
    return amap


def _candidate_path_tokens(desc: str, amap: dict) -> set:
    """Path-like tokens from the description: explicit paths + bare known dirs + aliases."""
    toks = set()
    # explicit paths containing a slash
    for m in re.findall(r"[A-Za-z_.][A-Za-z0-9_./*-]*/[A-Za-z0-9_./*-]*", desc):
        norm = m.replace("\\", "/").rstrip("*").rstrip("/")
        if norm:
            toks.add(norm)
    # bare top-level dir names known from the allow map
    known_tops = {p.split("/")[0] for prefs in amap.values() for p in prefs if p}
    for top in known_tops:
        if top and kw_in(top, desc):
            toks.add(top)
    # domain aliases
    for term, target in _DOMAIN_ALIASES.items():
        if kw_in(term, desc):
            toks.add(target)
    return toks


def scope_hits(desc: str, amap: dict) -> list:
    """[{token, owners:[agent...]}] — likely owners for each recognized path token."""
    results = []
    for tok in sorted(_candidate_path_tokens(desc, amap)):
        owners = []
        for agent, prefixes in amap.items():
            if any(path_overlap(tok, pref) for pref in prefixes):
                owners.append(agent)
        if owners:
            results.append({"token": tok, "owners": sorted(owners)})
    return results


# ---------------------------------------------------------------------------
# Orchestration + rendering
# ---------------------------------------------------------------------------

def suggest(desc: str, *, min_score: int = 2, limit: int = 5, exclude: str = "") -> dict:
    """Run all three mechanical recalls against the real repo paths."""
    desc_toks = tokens(desc)
    similar = score_corpus(desc_toks, corpus_entries(corpus_files()),
                           min_score=min_score, limit=limit, exclude=exclude)
    checks = checklist_hits(desc, parse_checklist(CHECKLIST_PATH))
    scope = scope_hits(desc, load_allow_map(ALLOW_DIR))
    return {"description": desc, "similar_proposals": similar,
            "checklist": checks, "scope": scope}


def render(result: dict) -> str:
    """Human-readable 💡 相关建议 block; each section emits （无）when empty."""
    lines = ["💡 相关建议（proposal_suggest，仅供参考、不阻断）", ""]

    lines.append("① 类似 / 相关 proposal:")
    if result["similar_proposals"]:
        for e in result["similar_proposals"]:
            lines.append(f"  - {e['id']}  {e['title']}  [{e['region']}]")
    else:
        lines.append("  （无）")
    lines.append("")

    lines.append("② 检查项 / 历史经验:")
    if result["checklist"]:
        for c in result["checklist"]:
            lines.append(f"  - {c['title']}")
            if c["lesson"]:
                lines.append(f"      教训: {c['lesson']}")
            if c["how"]:
                lines.append(f"      怎么做: {c['how']}")
            if c["source"]:
                lines.append(f"      来源: {c['source']}")
    else:
        lines.append("  （无）")
    lines.append("")

    lines.append("③ likely scope（按 agent_rules/*.allow.txt）:")
    if result["scope"]:
        for s in result["scope"]:
            lines.append(f"  - {s['token']}  →  {', '.join(s['owners'])}")
    else:
        lines.append("  （无）")
    return "\n".join(lines)


def main(argv=None) -> int:
    # Force UTF-8 stdout: the 💡 / CJK output is unencodable on Windows' default
    # GBK console (cp936). reconfigure is a no-op on already-utf8 streams.
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser(description="Proposal drafting suggestion helper (P-0097)")
    ap.add_argument("description", help="free-text requirement description")
    ap.add_argument("--json", action="store_true", help="emit JSON instead of text block")
    ap.add_argument("--exclude", default="", help="drop this P-NNNN from ① (e.g. the current draft)")
    ap.add_argument("--limit", type=int, default=5, help="max ① candidates (default 5)")
    ap.add_argument("--min-score", type=int, default=2, help="min shared tokens for ① (default 2)")
    args = ap.parse_args(argv)

    result = suggest(args.description, min_score=args.min_score,
                     limit=args.limit, exclude=args.exclude)
    if args.json:
        out(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        out(render(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
