"""Build knowledge-base dashboard from INDEX.md-driven auto-discovery.

Scans `knowledge/` across all federated subdirectories and emits a
self-contained HTML dashboard to the path defined in
`config/dashboard_config.json` (default points to
`shared_state/knowledge/dashboard.html` — the single physical copy
shared across all clones, governed by Art.4-1).

Replaces the rules-owned `knowledge/models/build_dashboard.py` (which
had a hardcoded CONCEPT_TREE and required rules edits for every new
category added by any agent — breaking the federated model).

Output path / lock path / lock timeout are config-driven (Art.4
no-hardcoding); concurrency uses `filelock.FileLock` + atomic
`os.replace()` per Art.4-1 shared-state writer protocol.

Data model (INDEX-driven):
  - Top categories: parsed from `knowledge/INDEX.md`'s "Subdirectory
    Overview" markdown table. Row columns: Subdirectory | Owner |
    Content | Sub-Index.
  - Category entries: `knowledge/{cat}/**/*.md` excluding INDEX.md /
    _TEMPLATE.md. Each file's frontmatter provides per-entry metadata.
  - Fallback: if the top INDEX.md is missing/unparseable, directory
    listing under `knowledge/` is used; each directory becomes a
    category with owner="unknown".

Frontmatter schema read per entry:
  - title (falls back to filename stem)
  - status, tags, created, updated (all optional)
  - owner (optional; annotates cross-agent authorship)

Usage:
    python tools/build_knowledge_dashboard.py
    python tools/build_knowledge_dashboard.py --root /path/to/agent-data
"""
import argparse
import html
import json
import logging
import os
import random
import re
import shutil
import sys
from datetime import datetime, timedelta
from pathlib import Path

from filelock import FileLock

try:
    import markdown as _markdown
    _MARKDOWN_AVAILABLE = True
except ImportError:
    _MARKDOWN_AVAILABLE = False

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(message)s")

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)
TABLE_ROW_RE = re.compile(r"^\s*\|(.+)\|\s*$")
SKIP_FILENAMES = {"INDEX.md", "_TEMPLATE.md", "_template.md"}
LINK_FIELDS = ["supersedes", "superseded_by", "related", "blocks", "blocked_by"]
_FIELD_LINE_RE = re.compile(r"^(\w+)[ \t]*:[ \t]*(.*)$")
_BLOCK_ITEM_RE = re.compile(r"^\s+-\s+(.+?)\s*$")


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """Return (fields_dict, body) split at the first '---\\n...---\\n' block.

    Tiny parser — handles three YAML surface forms used in the
    knowledge base:
      Scalar:        `key: value`
      Inline list:   `key: [a, b, c]`
      Block list:    `key:\\n  - a\\n  - b`
    Block lists are recognized via lookahead (matches the parser in
    `tools/audit_knowledge.py` so dashboard + audit see the same link
    graph; before this alignment, multi-line list `related:` /
    `supersedes:` fields silently dropped, hiding ~180 of ~200
    knowledge-internal cross-references from the graph view).
    NOT a general YAML parser; multi-line scalars and nested mappings
    are out of scope.
    """
    match = FRONTMATTER_RE.match(text)
    if not match:
        return {}, text
    fm_body, body = match.group(1), match.group(2)
    fields: dict = {}
    lines = fm_body.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        m = _FIELD_LINE_RE.match(line)
        if not m:
            i += 1
            continue
        key = m.group(1)
        raw = m.group(2).strip()
        if raw == "":
            # Block-list lookahead: collect indented `- item` lines
            items: list[str] = []
            j = i + 1
            while j < len(lines):
                bm = _BLOCK_ITEM_RE.match(lines[j])
                if not bm:
                    break
                items.append(bm.group(1).strip("\"'"))
                j += 1
            if items:
                fields[key] = items
                i = j
                continue
            fields[key] = ""
            i += 1
            continue
        if raw.startswith("[") and raw.endswith("]"):
            parts = [x.strip().strip("\"'") for x in raw[1:-1].split(",")]
            fields[key] = [x for x in parts if x]
        else:
            fields[key] = raw.strip("\"'")
        i += 1
    return fields, body


def _parse_subdirectory_table(index_md: Path) -> list[dict]:
    """Extract category metadata from the top INDEX.md subdirectory table.

    Looks for a markdown table whose header row contains 'Subdirectory'
    and 'Owner'. Returns list of {name, owner, content} dicts, one per
    data row. Header and separator rows are skipped. If no such table is
    found, returns an empty list (caller falls back to listdir).
    """
    if not index_md.is_file():
        return []
    text = index_md.read_text(encoding="utf-8")
    rows: list[dict] = []
    header_cols: list[str] | None = None
    for line in text.splitlines():
        m = TABLE_ROW_RE.match(line)
        if not m:
            if header_cols is not None:
                break  # table ended
            continue
        cells = [c.strip() for c in m.group(1).split("|")]
        if header_cols is None:
            normalized = [c.lower() for c in cells]
            if "subdirectory" in normalized and "owner" in normalized:
                header_cols = normalized
                continue
            # keep scanning for the right table
            continue
        if all(set(c) <= set("-: ") for c in cells):
            continue  # separator row
        row = dict(zip(header_cols, cells))
        name = row.get("subdirectory", "").strip("`/ ")
        if not name:
            continue
        rows.append({
            "name": name,
            "owner": row.get("owner", ""),
            "content": row.get("content", ""),
        })
    return rows


_MERMAID_BLOCK_RE = re.compile(
    r'<pre><code class="language-mermaid">(.*?)</code></pre>', re.DOTALL
)

# Tags that swallow subsequent content as raw text in the HTML parser
# (script/style/textarea/title) or otherwise break entry-body containment
# (iframe/object/embed). python-markdown passes inline HTML through, so a
# bare `<script type='application/json' ...>` in prose (e.g. inside a
# `<li>`) opens a real <script> tag that consumes all subsequent HTML
# until the next </script> — including the dashboard's own
# `<script src="...mermaid">` tag. Symptom (2026-05-13): mermaid never
# loads, console has no errors. Defense: post-render, escape opening
# brackets of these tags inside entry-body HTML. Mermaid blocks survive
# because they're wrapped in <div class="mermaid">, not <script>.
_DANGEROUS_TAGS = ("script", "style", "textarea", "title", "iframe", "object", "embed")
_DANGEROUS_TAG_RE = re.compile(
    r"<(/?)(" + "|".join(_DANGEROUS_TAGS) + r")\b",
    re.IGNORECASE,
)


def _sanitize_dangerous_tags(rendered: str) -> str:
    """Escape tags that would break entry-body containment in the dashboard."""
    return _DANGEROUS_TAG_RE.sub(r"&lt;\1\2", rendered)


def _transform_mermaid_blocks(rendered: str) -> str:
    """Rewrite python-markdown's mermaid fence output into Mermaid.js targets.

    fenced_code emits ```mermaid ...``` as
        <pre><code class="language-mermaid">ESCAPED_SRC</code></pre>
    Mermaid.js (v10, loaded via CDN in the page <body>) renders elements
    matching `.mermaid` whose textContent is the raw diagram source — so we
    unescape the HTML entities the markdown lib introduced and swap the
    container. Rendering is deferred to modal open (see _DASHBOARD_JS) so
    the cost is paid only when the user actually views a diagram.
    """
    def _sub(m: "re.Match[str]") -> str:
        return f'<div class="mermaid">{html.unescape(m.group(1))}</div>'
    return _MERMAID_BLOCK_RE.sub(_sub, rendered)


def _render_body_html(body: str) -> str:
    """Render a markdown body to HTML. Falls back to <pre> if markdown lib absent."""
    if _MARKDOWN_AVAILABLE:
        rendered = _markdown.markdown(
            body,
            extensions=["tables", "fenced_code", "sane_lists"],
            output_format="html5",
        )
        return _sanitize_dangerous_tags(_transform_mermaid_blocks(rendered))
    return f"<pre>{html.escape(body)}</pre>"


_SUMMARY_MAX_CHARS = 240
_TLDR_RE = re.compile(r"^\s*(?:>\s*)?\*\*TL;DR\*\*\s*[:：]?\s*(.+?)$", re.MULTILINE)
_INLINE_FMT_RE = re.compile(r"\*\*(.+?)\*\*|\*(.+?)\*|`(.+?)`|\[(.+?)\]\([^)]*\)")


def _extract_summary(body: str) -> str:
    """First TL;DR line OR first ordinary paragraph from a markdown body.

    Used by Briefing-mode panels (Pinned / Serendipity) where each entry
    is rendered as a card with a one-paragraph teaser. Heuristic order:
      1. If body has a `**TL;DR**: ...` line, use that
      2. Else first paragraph that isn't a heading / blockquote / code fence
    Result is stripped of bold/italic/code/link markdown noise and capped
    at _SUMMARY_MAX_CHARS (word-boundary aware).
    Returns "" if no usable paragraph found.
    """
    m = _TLDR_RE.search(body)
    if m:
        candidate = m.group(1).strip()
    else:
        candidate = ""
        for para in body.split("\n\n"):
            p = para.strip()
            if not p:
                continue
            if p.startswith(("#", ">", "```", "---", "|", "- ", "* ", "1. ")):
                continue
            candidate = p
            break
    if not candidate:
        return ""

    def _strip_inline(m: "re.Match[str]") -> str:
        return next((g for g in m.groups() if g), "")

    cleaned = _INLINE_FMT_RE.sub(_strip_inline, candidate)
    cleaned = cleaned.replace("\n", " ").strip()
    if len(cleaned) > _SUMMARY_MAX_CHARS:
        truncated = cleaned[:_SUMMARY_MAX_CHARS]
        space = truncated.rfind(" ")
        if space > _SUMMARY_MAX_CHARS - 40:
            truncated = truncated[:space]
        cleaned = truncated + "..."
    return cleaned


def _collect_entries(category_dir: Path, knowledge_root: Path) -> list[dict]:
    """Scan a category directory for knowledge files + metadata.

    Uses rglob as the fallback / default scan — the top INDEX is the
    source of truth for category list, but INSIDE a category we walk
    the filesystem directly so entries aren't missed if a contributor
    forgets to update the per-category INDEX.
    """
    entries: list[dict] = []
    if not category_dir.is_dir():
        return entries
    for path in sorted(category_dir.rglob("*.md")):
        if path.name in SKIP_FILENAMES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            logger.warning("skip %s: %s", path, exc)
            continue
        fields, body = _parse_frontmatter(text)
        links: dict[str, list[str]] = {}
        for field in LINK_FIELDS:
            raw = fields[field] if field in fields else ""
            if isinstance(raw, list):
                links[field] = [str(x).strip() for x in raw if x]
            elif raw:
                if raw.startswith("[") and raw.endswith("]"):
                    links[field] = [x.strip().strip("\"'") for x in raw[1:-1].split(",") if x.strip()]
                else:
                    links[field] = [raw.strip().strip("\"'")]
            else:
                links[field] = []
        title_val = fields["title"] if "title" in fields else path.stem.replace("_", " ")
        tags_val = fields["tags"] if "tags" in fields and isinstance(fields["tags"], list) else []
        entries.append({
            "path": path,
            "rel": path.relative_to(category_dir).as_posix(),
            "knowledge_rel": path.relative_to(knowledge_root).as_posix(),
            "title": title_val,
            "status": fields["status"] if "status" in fields else "",
            "tags": tags_val,
            "created": fields["created"] if "created" in fields else "",
            "updated": fields["updated"] if "updated" in fields else "",
            "owner": fields["owner"] if "owner" in fields else "",
            # Dataset-specific metadata (empty for non-dataset entries; consumed
            # by _render_category_datasets to group + order by vintage)
            "kind": fields["kind"] if "kind" in fields else "",
            "arch_version": fields["arch_version"] if "arch_version" in fields else "",
            "valid_from": fields["valid_from"] if "valid_from" in fields else "",
            # Briefing-mode surfacing (knowledge_frontmatter_schema v1.1.0):
            # one of "pinned" / "serendipity" / "" (absent = not surfaced).
            "briefing": fields["briefing"] if "briefing" in fields else "",
            # Summary extracted at collect time (used by Briefing-mode panels;
            # avoids carrying the full body around in the entry dict).
            "summary": _extract_summary(body),
            "body_html": _render_body_html(body),
            "links": links,
            "referenced_by": [],  # populated after reverse-index pass
        })
    return entries


def _collect_all(knowledge_root: Path) -> list[dict]:
    """Assemble the full category -> entries tree from knowledge_root."""
    index_md = knowledge_root / "INDEX.md"
    categories = _parse_subdirectory_table(index_md)
    if not categories:
        logger.info("no subdirectory table in %s; falling back to listdir", index_md)
        for child in sorted(knowledge_root.iterdir()):
            if child.is_dir() and not child.name.startswith("."):
                categories.append({
                    "name": child.name,
                    "owner": "unknown",
                    "content": "",
                })
    for cat in categories:
        cat_dir = knowledge_root / cat["name"]
        cat["entries"] = _collect_entries(cat_dir, knowledge_root)

    # Build reverse-link index: for each entry's outbound refs, record
    # the source on the target's "referenced_by" list. Only considers
    # targets that exist as knowledge entries (external implementation
    # pointers are valid per contract §5.3 but not navigable from the
    # dashboard back-link view).
    by_knowledge_rel: dict[str, dict] = {
        e["knowledge_rel"]: e for cat in categories for e in cat["entries"]
    }
    for cat in categories:
        for source in cat["entries"]:
            src_rel = source["knowledge_rel"]
            src_title = source["title"]
            for field, targets in source["links"].items():
                for target in targets:
                    target_clean = target.rstrip("/")
                    if target_clean in by_knowledge_rel:
                        by_knowledge_rel[target_clean]["referenced_by"].append({
                            "source_rel": src_rel,
                            "source_title": src_title,
                            "field": field,
                        })
    return categories


def _collect_graph_data(categories: list[dict]) -> dict:
    """Build cytoscape.js-compatible nodes/edges from collected entries.

    Nodes: one per knowledge entry; carries owner / status / tags / degree
    so the client-side renderer can color, size, and filter without a
    second pass over the page DOM.

    Edges: derived from each entry's `links` map. Only emit edges whose
    target also exists as a knowledge entry (external repo-relative
    pointers are valid per contract §5.3 but not navigable in the graph).

    Edge dedupe rules:
      - `supersedes` / `superseded_by` are inverses; emit only the
        `supersedes` direction (source -> target).
      - `blocks` / `blocked_by` are inverses; emit only `blocks`.
      - `related` is symmetric; emit one edge per unordered pair (the
        first direction we see), so two entries that mutually declare
        `related` don't appear as parallel edges.
    """
    by_rel: dict[str, dict] = {
        e["knowledge_rel"]: e for cat in categories for e in cat["entries"]
    }
    nodes: list[dict] = []
    degree: dict[str, int] = {rel: 0 for rel in by_rel}
    edges: list[dict] = []
    seen_related: set[tuple[str, str]] = set()

    def _add_edge(src: str, tgt: str, etype: str) -> None:
        edges.append({"data": {
            "id": f"{etype}|{src}->{tgt}",
            "source": src,
            "target": tgt,
            "type": etype,
        }})
        degree[src] = degree.get(src, 0) + 1
        degree[tgt] = degree.get(tgt, 0) + 1

    for cat in categories:
        for e in cat["entries"]:
            src_rel = e["knowledge_rel"]
            for tgt in e["links"].get("supersedes", []):
                tgt_clean = tgt.rstrip("/")
                if tgt_clean in by_rel:
                    _add_edge(src_rel, tgt_clean, "supersedes")
            for tgt in e["links"].get("blocks", []):
                tgt_clean = tgt.rstrip("/")
                if tgt_clean in by_rel:
                    _add_edge(src_rel, tgt_clean, "blocks")
            for tgt in e["links"].get("related", []):
                tgt_clean = tgt.rstrip("/")
                if tgt_clean not in by_rel:
                    continue
                pair = tuple(sorted([src_rel, tgt_clean]))
                if pair in seen_related:
                    continue
                seen_related.add(pair)
                _add_edge(pair[0], pair[1], "related")

    for cat in categories:
        for e in cat["entries"]:
            rel = e["knowledge_rel"]
            tags_blob = " ".join(t.lower() for t in e["tags"])
            search_blob = " ".join([
                e["title"].lower(), rel.lower(), tags_blob,
            ])
            nodes.append({"data": {
                "id": rel,
                "label": e["title"],
                "owner": e["owner"] or "unknown",
                "status": e["status"] or "",
                "tags": tags_blob,
                "search": search_blob,
                "degree": degree.get(rel, 0),
            }})

    return {"nodes": nodes, "edges": edges}


def _collect_tag_cooccur_data(
    categories: list[dict], threshold: int,
) -> dict:
    """Build tag-cooccurrence graph data: edges between entries that share
    >= threshold tags.

    Same node shape as `_collect_graph_data` (so cytoscape can swap edges
    without rebuilding nodes); edges carry `weight = shared tag count` and
    `shared = "tag1, tag2"` for tooltip. Reveals implicit topical
    proximity that isn't declared via `related:` frontmatter.

    Performance: O(N^2) over entries (114^2 ≈ 13k pair comparisons in
    practice, completes well under 100ms — no need to bucket by tag-set
    intersection).
    """
    by_rel: dict[str, dict] = {
        e["knowledge_rel"]: e for cat in categories for e in cat["entries"]
    }
    tag_sets: list[tuple[str, set[str]]] = []
    for rel, e in by_rel.items():
        tags = {t.lower() for t in e["tags"] if t}
        tag_sets.append((rel, tags))

    edges: list[dict] = []
    degree: dict[str, int] = {rel: 0 for rel in by_rel}
    for i in range(len(tag_sets)):
        rel_a, tags_a = tag_sets[i]
        for j in range(i + 1, len(tag_sets)):
            rel_b, tags_b = tag_sets[j]
            shared = tags_a & tags_b
            if len(shared) < threshold:
                continue
            edges.append({"data": {
                "id": f"cooccur|{rel_a}|{rel_b}",
                "source": rel_a,
                "target": rel_b,
                "type": "cooccur",
                "weight": len(shared),
                "shared": ", ".join(sorted(shared)),
            }})
            degree[rel_a] += 1
            degree[rel_b] += 1

    nodes: list[dict] = []
    for cat in categories:
        for e in cat["entries"]:
            rel = e["knowledge_rel"]
            tags_blob = " ".join(t.lower() for t in e["tags"])
            search_blob = " ".join([
                e["title"].lower(), rel.lower(), tags_blob,
            ])
            nodes.append({"data": {
                "id": rel,
                "label": e["title"],
                "owner": e["owner"] or "unknown",
                "status": e["status"] or "",
                "tags": tags_blob,
                "search": search_blob,
                "degree": degree.get(rel, 0),
            }})

    return {"nodes": nodes, "edges": edges, "threshold": threshold}


def _relative_date(updated: str, now: datetime) -> str:
    """Render a YYYY-MM-DD as a compact relative phrase like '3d ago'.

    Buckets: today / Nd ago (1-6) / Nw ago (1-3 weeks) / Nmo ago / Ny ago.
    Empty / malformed input falls through to the original string so the
    user sees raw data rather than a misleading rendering.
    """
    if not updated or len(updated) < 10:
        return updated or ""
    try:
        dt = datetime.strptime(updated[:10], "%Y-%m-%d")
    except ValueError:
        return updated
    delta_days = (now - dt).days
    if delta_days < 0:
        return updated  # future date — show raw
    if delta_days == 0:
        return "today"
    if delta_days < 7:
        return f"{delta_days}d ago"
    if delta_days < 30:
        return f"{delta_days // 7}w ago"
    if delta_days < 365:
        return f"{delta_days // 30}mo ago"
    years = delta_days // 365
    return f"{years}y ago"


def _render_lineage_badges(entry: dict) -> str:
    """Render compact Lineage indicators for an entry card.

    Three relation types, one badge each (only when count > 0):
      ⇐ N  outbound supersedes (this entry replaces N others)
      ⇒ N  inbound superseded_by — frontmatter declares this entry was replaced
      ↑ N  referenced_by — count of inbound references via related/blocks/...

    Hover tooltip shows path detail; click bubbles up to entry card and
    opens the modal. Compact (each badge ~28px wide).
    """
    sup_n = len(entry["links"].get("supersedes", []))
    by_n = len(entry["links"].get("superseded_by", []))
    ref_n = len(entry.get("referenced_by", []))
    parts: list[str] = []
    if sup_n:
        title = "supersedes: " + "; ".join(entry["links"]["supersedes"])
        parts.append(
            f'<span class="lineage lineage-sup" title="{html.escape(title)}">'
            f'<span class="lineage-icon">&#x21D0;</span>{sup_n}</span>'
        )
    if by_n:
        title = "superseded by: " + "; ".join(entry["links"]["superseded_by"])
        parts.append(
            f'<span class="lineage lineage-by" title="{html.escape(title)}">'
            f'<span class="lineage-icon">&#x21D2;</span>{by_n}</span>'
        )
    if ref_n:
        ref_titles = "; ".join(
            f'{r["field"]} from {r["source_rel"]}'
            for r in entry["referenced_by"]
        )
        parts.append(
            f'<span class="lineage lineage-ref" title="{html.escape(ref_titles)}">'
            f'<span class="lineage-icon">&#x2191;</span>{ref_n}</span>'
        )
    return "".join(parts)


def _is_stale(updated: str, now: datetime, stale_days: int) -> bool:
    """Entry is stale iff its `updated` is more than `stale_days` ago.

    Missing/malformed dates are treated as not-stale so we don't surprise
    users with rows that look frozen for cosmetic data-quality reasons.
    """
    if not updated or len(updated) < 10:
        return False
    try:
        dt = datetime.strptime(updated[:10], "%Y-%m-%d")
    except ValueError:
        return False
    return (now - dt).days > stale_days


def _render_at_a_glance(
    categories: list[dict], now: datetime,
    recent_days: int, stale_days: int,
) -> str:
    """Single stale indicator — actionable when N>0, gray static when N=0.

    Replaces the wider KPI bar (total/recent/owner chips removed
    2026-05-06): the bar's other stats were passive and the owner
    chips are now subsumed by the top-level owner-tabs. Only stale
    deserved persistent visibility because 0 is a positive signal
    (no review backlog) and N>0 is a "click me to clean up" cue.

    Click handler in _DASHBOARD_JS toggles `state.stale` to filter
    the entry list to only stale rows when active. _recent_days is
    accepted but unused; kept in signature so callers don't break
    if reintroduced later.
    """
    _ = recent_days  # signature compat; not surfaced in current view
    stale_n = 0
    for cat in categories:
        for e in cat["entries"]:
            if e["status"] == "active" and _is_stale(e["updated"], now, stale_days):
                stale_n += 1

    klass = "stale-indicator" if stale_n > 0 else "stale-indicator stale-zero"
    label = (
        f'{stale_n} stale &gt;{stale_days}d'
        if stale_n > 0
        else f'0 stale &gt;{stale_days}d'
    )
    aria = f'Filter to {stale_n} stale entries' if stale_n > 0 else 'No stale entries'
    return (
        '<div class="stale-row">'
        f'<button id="stale-indicator" class="{klass}" '
        f'data-stale-count="{stale_n}" '
        f'aria-label="{html.escape(aria)}" '
        f'title="{html.escape(aria)}">'
        f'<span class="stale-icon">!</span>{label}'
        f'</button>'
        '</div>'
    )


def _render_entry(
    entry: dict, knowledge_root: Path,
    now: datetime, stale_days: int,
) -> str:
    """Render one knowledge file as an HTML row.

    Emits data-* attributes on the <tr> so client-side JS in the dashboard
    can filter without re-fetching or re-parsing:
      data-owner   — exact match filter
      data-status  — exact match filter
      data-tags    — space-separated list for tag-click / tag-filter
      data-search  — lowercase concat of title + tags + path for textbox

    `knowledge_root` is the absolute path to the knowledge/ directory of the
    clone that built this dashboard; used to emit absolute file:// hrefs that
    survive the dashboard living outside any clone (shared_state/).
    """
    tags_list = entry["tags"]
    # Tag chips on second line — limit to 6 to keep card height bounded;
    # remaining tags collapsed into a "+N more" affordance the user can
    # see by opening the modal.
    visible_tags = tags_list[:6]
    extra_tag_count = len(tags_list) - len(visible_tags)
    tags = "".join(
        f'<span class="tag" data-tag="{html.escape(t)}">{html.escape(t)}</span>'
        for t in visible_tags
    )
    if extra_tag_count > 0:
        tags += f'<span class="tag tag-more">+{extra_tag_count}</span>'

    status = entry["status"]
    status_html = (
        f'<span class="status status-{html.escape(status)}">{html.escape(status)}</span>'
        if status else ""
    )
    owner = entry["owner"]
    # Owner pill instead of bracketed badge — clickable to filter
    owner_html = (
        f'<span class="owner-badge owner-{html.escape(owner)}" '
        f'data-owner-click="{html.escape(owner)}">{html.escape(owner)}</span>'
        if owner else ""
    )
    lineage_html = _render_lineage_badges(entry)
    rel_date = _relative_date(
        entry["valid_from"] or entry["updated"] or entry["created"], now,
    )
    raw_date = entry["valid_from"] or entry["updated"] or entry["created"]

    # data-search: lowercase concat for textbox match (unchanged from
    # row-form so the IIFE filter loop sees the same shape)
    search_blob = " ".join([
        entry["title"].lower(),
        entry["rel"].lower(),
        " ".join(t.lower() for t in tags_list),
    ])

    # rel_js: title button uses inline onclick (the most defensive
    # form — survives any IIFE crash; see commit 2026-04-30 walk-back
    # in this file's git log for context). Single-quoted in onclick so
    # literal `"` in the rel doesn't break the HTML; html.escape
    # protects `'` / `<>`. Knowledge paths are ASCII so escape is
    # mainly defensive.
    rel_js = entry["knowledge_rel"].replace("'", "\\'")
    stale_attr = ' data-stale="1"' if (
        status == "active" and _is_stale(entry["updated"], now, stale_days)
    ) else ""
    onclick = f"window._dashboardOpenEntry('{html.escape(rel_js)}')"
    return (
        f'<div class="entry-card" data-entry="1" '
        f'data-entry-rel="{html.escape(entry["knowledge_rel"])}" '
        f'data-owner="{html.escape(owner)}" '
        f'data-status="{html.escape(status)}" '
        f'data-tags="{html.escape(" ".join(tags_list))}" '
        f'data-search="{html.escape(search_blob)}"{stale_attr}>'
        '<div class="entry-row1">'
        f'<button type="button" class="entry-title" onclick="{onclick}">'
        f'{html.escape(entry["title"])}</button>'
        f'{owner_html}{status_html}'
        f'<span class="entry-date" title="{html.escape(raw_date)}">'
        f'{html.escape(rel_date)}</span>'
        '</div>'
        f'<div class="entry-row2">{tags}{lineage_html}'
        f'<code class="entry-path">{html.escape(entry["rel"])}</code>'
        '</div>'
        '</div>'
    )


def _render_entry_bodies(categories: list[dict], knowledge_root: Path) -> str:
    """Emit all entry bodies as hidden containers for modal display.

    Each body is wrapped in a div keyed by knowledge-relative path so
    the modal JS can `document.querySelector('[data-entry-body="..."]')`.

    Also pre-renders skill .md files (from knowledge/skills/_tiers.json +
    registry) so the skills tier index can open them in the same modal
    instead of native-navigating to raw .md (file:// shows source not
    rendered HTML).
    """
    parts: list[str] = []
    for cat in categories:
        for entry in cat["entries"]:
            rel = html.escape(entry["knowledge_rel"])
            title = html.escape(entry["title"])
            path_disp = html.escape(f'knowledge/{entry["knowledge_rel"]}')
            body_html = entry["body_html"]
            parts.append(
                f'<div class="entry-body" data-entry-body="{rel}" '
                f'data-entry-title="{title}" data-entry-path="{path_disp}">'
                f'{body_html}</div>'
            )

    # Append skill bodies so the tier index's "skill:<name>" data-entry-body
    # keys resolve in the same _dashboardOpenEntry(rel) lookup.
    parts.extend(_render_skill_entry_bodies(knowledge_root))

    return '<div id="entry-bodies" hidden>' + "\n".join(parts) + '</div>'


def _render_skill_entry_bodies(knowledge_root: Path) -> list[str]:
    """Pre-render skill .md files as hidden entry-body divs for modal display.

    Reads knowledge/skills/_tiers.json to enumerate every classified skill,
    cross-references governance_core.discovery.registry for the actual .md path,
    and emits one div per skill keyed by data-entry-body="skill:<name>".

    Tolerates missing tiers.json (no skills section installed yet),
    missing registry import (running in a stripped clone), and per-skill
    read/render errors (one bad skill should not break the dashboard).
    """
    tiers_path = knowledge_root / "skills" / "_tiers.json"
    if not tiers_path.is_file():
        return []

    try:
        tiers_data = json.loads(tiers_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []

    project_root = knowledge_root.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    try:
        from governance_core.discovery.registry import SkillRegistry
    except ImportError:
        return []

    try:
        reg = SkillRegistry(track_usage=False)
        reg.scan()
    except Exception:
        return []

    by_name = {
        s["name"]: s for s in reg.manifest()
        if s["source_type"] != "module"
    }

    parts: list[str] = []
    seen: set[str] = set()
    for tier_body in tiers_data.get("tiers", {}).values():
        for name in tier_body.get("skills", []):
            if name in seen:
                continue
            seen.add(name)
            entry = by_name.get(name)
            if entry is None:
                continue
            try:
                content = Path(entry["file_path"]).read_text(encoding="utf-8")
                _, body = _parse_frontmatter(content)
                body_html = _render_body_html(body)
                rel_disp = Path(entry["file_path"]).relative_to(project_root).as_posix()
            except (OSError, ValueError):
                continue
            parts.append(
                f'<div class="entry-body" data-entry-body="skill:{html.escape(name)}" '
                f'data-entry-title="{html.escape(name)}" '
                f'data-entry-path="{html.escape(rel_disp)}">'
                f'{body_html}</div>'
            )
    return parts


def _render_category(
    cat: dict, knowledge_root: Path,
    now: datetime, stale_days: int,
) -> str:
    """Render one category section as a native <details> disclosure.

    Default open. The IIFE filter loop hides empty sections via
    `section.cat.hidden` (works with the <details> wrapper because
    rows live inside it; selectors still match).
    """
    if cat["name"] == "datasets":
        return _render_category_datasets(cat, knowledge_root, now, stale_days)
    if cat["name"] == "skills":
        return _render_category_skills(cat, knowledge_root)
    name = html.escape(cat["name"])
    owner = html.escape(cat["owner"])
    content = html.escape(cat["content"])
    entries = cat["entries"]
    if not entries:
        body = '<p class="empty">(no entries yet)</p>'
    else:
        cards = "\n".join(
            _render_entry(e, knowledge_root, now, stale_days) for e in entries
        )
        body = f'<div class="entry-list">{cards}</div>'
    return (
        f'<section class="cat" data-cat-owner="{owner}"><details open>'
        f'<summary><h2>{name} <span class="owner">({owner})</span>'
        f'<span class="cat-count">({len(entries)})</span></h2></summary>'
        f'<p class="cat-content">{content}</p>{body}'
        f'</details></section>'
    )


def _render_category_datasets(
    cat: dict, knowledge_root: Path,
    now: datetime, stale_days: int,
) -> str:
    """Render datasets category with two-level grouping by `kind`.

    Layout: a single <section> with one <h3> sub-header per `kind`, each
    listing entries sorted by `valid_from` desc (newest vintage first).
    Entries lacking `kind` fall into a trailing "uncategorized" group.
    Status `in_use` (green) vs `deprecated` (gray) — see CSS rules.

    Per proposal `dataset_registry_and_unified_artifacts_layout.md` §3.3.3.
    """
    name = html.escape(cat["name"])
    owner = html.escape(cat["owner"])
    content = html.escape(cat["content"])
    entries = cat["entries"]
    if not entries:
        body = '<p class="empty">(no entries yet)</p>'
        return (
            f'<section class="cat" data-cat-owner="{owner}"><details open>'
            f'<summary><h2>{name} <span class="owner">({owner})</span>'
            f'<span class="cat-count">(0)</span></h2></summary>'
            f'<p class="cat-content">{content}</p>{body}'
            f'</details></section>'
        )

    # Group by kind; preserve a stable kind order (canonical per VALID_KINDS
    # in dataset_registry, with anything unrecognized appended at the end).
    canonical_kind_order = ["dense", "oos", "training", "kdaily_cache", "derived_features"]
    by_kind: dict[str, list[dict]] = {}
    for entry in entries:
        kind = entry["kind"] or "_uncategorized"
        by_kind.setdefault(kind, []).append(entry)

    ordered_kinds = [k for k in canonical_kind_order if k in by_kind]
    ordered_kinds += sorted(k for k in by_kind if k not in canonical_kind_order)

    parts: list[str] = []
    for kind in ordered_kinds:
        # Sort by valid_from desc; entries lacking valid_from sort last.
        items = sorted(
            by_kind[kind],
            key=lambda e: (e["valid_from"] or "0000-00-00"),
            reverse=True,
        )
        cards = "\n".join(
            _render_entry(e, knowledge_root, now, stale_days) for e in items
        )
        kind_label = html.escape(kind)
        parts.append(
            f'<h3 class="dataset-kind">{kind_label} <span class="kind-count">({len(items)})</span></h3>'
            f'<div class="entry-list">{cards}</div>'
        )
    body = "\n".join(parts)
    return (
        f'<section class="cat" data-cat-owner="{owner}"><details open>'
        f'<summary><h2>{name} <span class="owner">({owner})</span>'
        f'<span class="cat-count">({len(entries)})</span></h2></summary>'
        f'<p class="cat-content">{content}</p>{body}'
        f'</details></section>'
    )


def _render_category_skills(cat: dict, knowledge_root: Path) -> str:
    """Render skills/ category by embedding the auto-generated INDEX.md.

    The skills/ directory has no per-entry .md files — its INDEX.md (built
    by tools/build_skill_index.py) is the catalog itself, grouping ~70
    md-skills under T1 universal / T2 project / T3 branch. Default
    _render_category would show "(no entries yet)" because INDEX.md is in
    SKIP_FILENAMES. This special case renders the INDEX body inline.
    """
    name = html.escape(cat["name"])
    owner = html.escape(cat["owner"])
    content = html.escape(cat["content"])

    index_path = knowledge_root / "skills" / "INDEX.md"
    tiers_path = knowledge_root / "skills" / "_tiers.json"

    # Compute total skill count from _tiers.json so the header stays in sync
    total = 0
    tier_count = 0
    if tiers_path.is_file():
        try:
            tiers_data = json.loads(tiers_path.read_text(encoding="utf-8"))
            for tier_id, tier_body in tiers_data.get("tiers", {}).items():
                names = tier_body.get("skills", [])
                if names:
                    tier_count += 1
                    total += len(names)
        except (OSError, ValueError):
            pass

    if not index_path.is_file():
        body = ('<p class="empty">(skills/INDEX.md missing — run '
                '<code>python tools/build_skill_index.py</code>)</p>')
        count_label = "(0)"
    else:
        text = index_path.read_text(encoding="utf-8")
        _, md_body = _parse_frontmatter(text)
        # Strip the "# Skill Index" h1 since dashboard wraps it in h2
        md_body = re.sub(r"^# Skill Index\s*\n", "", md_body, count=1)
        body_html = _render_body_html(md_body)
        # Rewrite skill .md links to fire _dashboardOpenEntry('skill:<name>')
        # so clicks open the rendered modal (same UX as knowledge entries)
        # instead of native-navigating to raw .md source. Catches the three
        # markdown-skill source dirs: .claude/commands/, .claude/skills/, and
        # .claude/skills/learned/. The skill name is the basename without
        # the trailing .md extension. Pre-rendered HTML for each skill is
        # emitted by _render_skill_entry_bodies() into the hidden entry-bodies
        # block, so _dashboardOpenEntry can find it via data-entry-body.
        # Mark skill links with a data attribute; a delegated click listener
        # (added near the existing document-click handler) reads the attr
        # and calls _dashboardOpenEntry. Avoids inline-onclick escape
        # fragility (Python f-string ↔ HTML attr ↔ JS string layering).
        body_html = re.sub(
            r'href="\.claude/(?:commands|skills/learned|skills)/([^"/]+)\.md"',
            lambda m: f'href="#" data-skill-modal="{m.group(1)}"',
            body_html,
        )
        body = f'<div class="skill-tier-index">{body_html}</div>'
        count_label = (
            f"({total} skills across {tier_count} tiers)"
            if total else "(0)"
        )

    return (
        f'<section class="cat" data-cat-owner="{owner}"><details open>'
        f'<summary><h2>{name} <span class="owner">({owner})</span>'
        f'<span class="cat-count">{count_label}</span></h2></summary>'
        f'<p class="cat-content">{content}</p>{body}'
        f'</details></section>'
    )


def _load_feature_attempts(knowledge_root: Path) -> list[dict]:
    """Read knowledge/experiments/feature_attempts.jsonl, returning entries.

    Per proposal `evaluator_contract_and_feature_graveyard.md` §3.1.1
    (B1 revision: file lives under knowledge/experiments/, not artifacts/,
    so it git-syncs across clones and the core dashboard can read it).

    Returns empty list if the file is missing or empty — graveyard section
    then renders as an explicit "no data" placeholder rather than vanishing
    silently. Bad lines are skipped (the registry's own validate runs at
    write time; this reader is best-effort for visualization).
    """
    path = knowledge_root / "experiments" / "feature_attempts.jsonl"
    if not path.is_file():
        return []
    entries: list[dict] = []
    try:
        with path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except (json.JSONDecodeError, ValueError):
                    continue
    except OSError:
        return []
    return entries


def _aggregate_feature_attempts(entries: list[dict]) -> dict:
    """Aggregate feature_attempts entries for the graveyard view.

    Returns:
      {
        'total': int,
        'by_decision': {decision: count},
        'features': [{feature, total, rejected, latest_reason, latest_at}],
        'recent_rejects': [{feature, attempt_id, decision_reason, created_at}, ...],
      }

    `features` sorted by rejected count desc; `recent_rejects` is the most
    recent 20 entries with decision='rejected', sorted by created_at desc.
    """
    by_decision: dict[str, int] = {}
    by_feature: dict[str, dict] = {}
    rejected_entries: list[dict] = []

    for e in entries:
        decision = e.get("decision", "unknown")
        by_decision[decision] = by_decision.get(decision, 0) + 1
        created_at = e.get("created_at", "")
        reason = e.get("decision_reason", "")
        attempt_id = e.get("attempt_id", "")
        feats = e.get("candidate_features") or []
        if isinstance(feats, str):
            feats = [feats]
        for feat in feats:
            agg = by_feature.setdefault(
                feat,
                {"feature": feat, "total": 0, "rejected": 0,
                 "latest_reason": "", "latest_at": ""},
            )
            agg["total"] += 1
            if decision == "rejected":
                agg["rejected"] += 1
            if created_at > agg["latest_at"]:
                agg["latest_at"] = created_at
                agg["latest_reason"] = reason
        if decision == "rejected":
            rejected_entries.append({
                "features": ", ".join(feats) or "—",
                "attempt_id": attempt_id,
                "decision_reason": reason,
                "created_at": created_at,
            })

    features_sorted = sorted(
        by_feature.values(),
        key=lambda f: (-f["rejected"], -f["total"], f["feature"]),
    )
    rejected_entries.sort(key=lambda r: r["created_at"], reverse=True)

    return {
        "total": len(entries),
        "by_decision": by_decision,
        "features": features_sorted,
        "recent_rejects": rejected_entries[:20],
    }


def _render_graveyard_section(knowledge_root: Path) -> str:
    """Render the feature-attempts graveyard section.

    Per proposal `evaluator_contract_and_feature_graveyard.md` §3.4 R8:
    surface features / thresholds / decisions that have been tried so
    repeat experiments hit a visible warning instead of being silently
    re-attempted. Rendered as a top-level section alongside the knowledge
    categories.

    Source: knowledge/experiments/feature_attempts.jsonl (B1 revision).
    Missing or empty file renders an explicit "no data" placeholder so
    users can tell the section is wired vs. genuinely empty.
    """
    entries = _load_feature_attempts(knowledge_root)
    if not entries:
        return (
            '<section class="cat" id="graveyard"><details open>'
            '<summary><h2>Feature Attempts Graveyard '
            '<span class="owner">(rules)</span></h2></summary>'
            '<p class="cat-content">Aggregate view of feature / threshold attempts '
            'rejected by the evaluator. Source: '
            '<code>knowledge/experiments/feature_attempts.jsonl</code>.</p>'
            '<p class="empty">(no attempts recorded yet — graveyard activates '
            'after first <code>/evaluate-candidate</code> run)</p>'
            '</details></section>'
        )

    agg = _aggregate_feature_attempts(entries)

    decision_chips = "".join(
        f'<span class="status status-{html.escape(d)}">{html.escape(d)}: {n}</span> '
        for d, n in sorted(agg["by_decision"].items(), key=lambda kv: -kv[1])
    )

    feat_rows = []
    for f in agg["features"][:30]:
        reason_short = (f["latest_reason"] or "")[:120]
        feat_rows.append(
            "<tr>"
            f"<td class='title'>{html.escape(f['feature'])}</td>"
            f"<td>{f['total']}</td>"
            f"<td>{f['rejected']}</td>"
            f"<td class='date'>{html.escape(f['latest_at'][:10])}</td>"
            f"<td>{html.escape(reason_short)}</td>"
            "</tr>"
        )
    feat_table = (
        '<h3 class="dataset-kind">By feature '
        f'<span class="kind-count">({len(agg["features"])} unique)</span></h3>'
        '<table class="entries">'
        '<thead><tr><th>Feature</th><th>Total</th><th>Rejected</th>'
        '<th>Latest</th><th>Latest reason</th></tr></thead>'
        f'<tbody>{"".join(feat_rows)}</tbody></table>'
    ) if feat_rows else ""

    recent_rows = []
    for r in agg["recent_rejects"]:
        reason_short = (r["decision_reason"] or "")[:140]
        recent_rows.append(
            "<tr>"
            f"<td class='date'>{html.escape(r['created_at'][:10])}</td>"
            f"<td class='title'>{html.escape(r['features'])}</td>"
            f"<td><code>{html.escape(r['attempt_id'])}</code></td>"
            f"<td>{html.escape(reason_short)}</td>"
            "</tr>"
        )
    recent_table = (
        '<h3 class="dataset-kind">Recent rejects '
        f'<span class="kind-count">({len(agg["recent_rejects"])})</span></h3>'
        '<table class="entries">'
        '<thead><tr><th>Date</th><th>Features</th>'
        '<th>Attempt</th><th>Reason</th></tr></thead>'
        f'<tbody>{"".join(recent_rows)}</tbody></table>'
    ) if recent_rows else ""

    return (
        '<section class="cat" id="graveyard"><details open>'
        '<summary><h2>Feature Attempts Graveyard '
        '<span class="owner">(rules)</span></h2></summary>'
        '<p class="cat-content">Aggregate view of feature / threshold attempts. '
        f'Source: <code>knowledge/experiments/feature_attempts.jsonl</code> '
        f'· {agg["total"]} attempts. Distribution: {decision_chips}</p>'
        f'{feat_table}{recent_table}'
        '</details></section>'
    )


def _render_controls(categories: list[dict]) -> str:
    """Build the filter/search control row.

    Owner chips enumerate actual owners seen in the data. Status chips
    cover the full 4-value enum. Active-tag chip is added dynamically
    by JS when the user clicks a tag.
    """
    owners_seen = sorted({
        e["owner"] for cat in categories for e in cat["entries"] if e["owner"]
    })
    statuses_seen = sorted({
        e["status"] for cat in categories for e in cat["entries"] if e["status"]
    })
    owner_chips = "".join(
        f'<button class="chip" data-filter="owner" data-value="{html.escape(o)}">{html.escape(o)}</button>'
        for o in owners_seen
    )
    status_chips = "".join(
        f'<button class="chip" data-filter="status" data-value="{html.escape(s)}">{html.escape(s)}</button>'
        for s in statuses_seen
    )
    return f"""
<div class="controls">
  <input type="text" id="search" placeholder="Search title, tags, path..." autocomplete="off">
  <div class="filter-row">
    <span class="filter-label">Status:</span>
    <button class="chip active" data-filter="status" data-value="">all</button>
    {status_chips}
  </div>
  <div class="filter-row" id="tag-filter-row" style="display:none">
    <span class="filter-label">Tag:</span>
    <span id="active-tag"></span>
    <button class="chip chip-clear" id="clear-tag">clear</button>
  </div>
  <div class="result-row">
    <span class="result-count" id="result-count"></span>
    <button class="chip chip-clear" id="clear-all" hidden>× clear all filters</button>
  </div>
</div>
"""


def _render_owner_tabs(categories: list[dict]) -> str:
    """Top-level Owner navigation: All / rules / trade / data / research / core.

    Drives the same `state.owner` filter as the previous chip row in
    .controls — clicking a tab is equivalent to clicking the old owner
    chip. This elevates the most actionable filter to top-of-page so
    users coming with a role-driven question ("what should I as rules
    look at") have a primary entry point.

    Tabs only enumerate owners actually seen in the data so empty-by-
    construction owners don't appear (matches the behavior of the old
    chip row).
    """
    owners_seen = sorted({
        e["owner"] for cat in categories for e in cat["entries"] if e["owner"]
    })
    tabs = '<button class="owner-tab active" data-owner-tab="">All</button>'
    for o in owners_seen:
        tabs += (
            f'<button class="owner-tab owner-{html.escape(o)}" '
            f'data-owner-tab="{html.escape(o)}">{html.escape(o)}</button>'
        )
    return f'<div class="owner-tabs">{tabs}</div>'


def _render_mode_bar() -> str:
    """Top-of-page mode switcher between Index (find-stuff) and Briefing (read-this).

    Default mode (Index) is established at page-render time via body[data-mode="index"].
    A small JS handler in _DASHBOARD_JS toggles the attribute, persists the selection
    via URL hash (#briefing literal segment), and restores it on page load.
    """
    return """
<div class="mode-bar">
  <button type="button" class="mode-btn active" data-mode="index" id="mode-btn-index">Index</button>
  <button type="button" class="mode-btn" data-mode="briefing" id="mode-btn-briefing">Briefing</button>
</div>
"""


def _load_briefing_config(root: Path) -> dict:
    """Load `config/briefing_config.json`. No defaults (Art.4).

    Required keys per `proposals/dashboard_briefing_mode.md` §2.2:
      serendipity_per_week, exclude_status, exclude_tags_anywhere,
      iteration_window_days, stale_adr_days, stale_check_categories.
    Missing-key error fails fast rather than silently substituting.
    """
    cfg_path = root / "config" / "briefing_config.json"
    if not cfg_path.is_file():
        raise FileNotFoundError(
            f"Briefing config missing: {cfg_path}. "
            "This file is required (Art.4 no-default policy). "
            "See proposals/dashboard_briefing_mode.md."
        )
    cfg = json.loads(cfg_path.read_text(encoding="utf-8-sig"))
    required = (
        "serendipity_per_week", "exclude_status", "exclude_tags_anywhere",
        "iteration_window_days", "stale_adr_days", "stale_check_categories",
    )
    for key in required:
        if key not in cfg:
            raise KeyError(f"briefing_config.json missing required key: {key}")
    return cfg


def _collect_briefing_data(categories: list[dict], cfg: dict, today: datetime) -> dict:
    """Aggregate Briefing-mode panel data from frontmatter (no git diff).

    Three panels:
      Pinned          — every entry with briefing=pinned, grouped by owner
      Serendipity     — entries with briefing=serendipity, filtered by
                        exclude_status / exclude_tags_anywhere, then sampled
                        deterministically by ISO-week seed (so the same N
                        entries surface for everyone within one calendar week,
                        rotating the next week)
      Iteration       — recent_writes (updated within iteration_window_days)
                        + stale (active entries in stale_check_categories whose
                        updated date is older than stale_adr_days)

    Status-flip detection and within-window supersede-closure tracking would
    require git-log diffing across two states; deferred. Phase A surfaces the
    pure-frontmatter signals first.
    """
    pinned: list[dict] = []
    serendipity_pool: list[dict] = []
    recent_writes: list[dict] = []
    stale: list[dict] = []

    window_cutoff_dt = today - timedelta(days=int(cfg["iteration_window_days"]))
    stale_cutoff_dt = today - timedelta(days=int(cfg["stale_adr_days"]))
    window_cutoff = window_cutoff_dt.strftime("%Y-%m-%d")
    stale_cutoff = stale_cutoff_dt.strftime("%Y-%m-%d")
    today_iso = today.strftime("%Y-%m-%d")
    exclude_status = set(cfg["exclude_status"])
    exclude_tags = {t.lower() for t in cfg["exclude_tags_anywhere"]}
    stale_cats = set(cfg["stale_check_categories"])

    def _enrich(e: dict, cat_name: str) -> dict:
        return {
            "knowledge_rel": e["knowledge_rel"],
            "title": e["title"],
            "owner": e["owner"],
            "status": e["status"],
            "tags": e["tags"],
            "updated": e["updated"],
            "summary": e.get("summary", ""),
            "category": cat_name,
        }

    for cat in categories:
        cat_name = cat["name"]
        for e in cat["entries"]:
            briefing = e.get("briefing", "")
            tags_set = {t.lower() for t in e["tags"]}

            if briefing == "pinned":
                pinned.append(_enrich(e, cat_name))
            elif briefing == "serendipity":
                if e["status"] not in exclude_status and not (tags_set & exclude_tags):
                    serendipity_pool.append(_enrich(e, cat_name))

            updated = e["updated"]
            if updated and updated >= window_cutoff and updated <= today_iso:
                recent_writes.append(_enrich(e, cat_name))

            if (cat_name in stale_cats
                    and e["status"] == "active"
                    and updated
                    and updated < stale_cutoff):
                rec = _enrich(e, cat_name)
                try:
                    rec["days_stale"] = (today - datetime.strptime(updated, "%Y-%m-%d")).days
                except ValueError:
                    rec["days_stale"] = 0
                stale.append(rec)

    iso_year, iso_week, _ = today.isocalendar()
    seed = iso_year * 100 + iso_week
    rng = random.Random(seed)
    n_pick = min(int(cfg["serendipity_per_week"]), len(serendipity_pool))
    if n_pick > 0:
        # Sort pool by knowledge_rel for deterministic ordering before sampling
        sorted_pool = sorted(serendipity_pool, key=lambda x: x["knowledge_rel"])
        serendipity_picks = rng.sample(sorted_pool, n_pick)
    else:
        serendipity_picks = []

    pinned.sort(key=lambda e: (e["owner"], e["title"]))
    recent_writes.sort(key=lambda e: e["updated"], reverse=True)
    stale.sort(key=lambda e: e["updated"])

    return {
        "pinned": pinned,
        "serendipity_picks": serendipity_picks,
        "serendipity_pool_size": len(serendipity_pool),
        "recent_writes": recent_writes[:10],
        "recent_writes_total": len(recent_writes),
        "stale": stale,
        "iso_week": f"{iso_year}-W{iso_week:02d}",
        "window_days": int(cfg["iteration_window_days"]),
        "stale_days": int(cfg["stale_adr_days"]),
        "stale_categories": sorted(stale_cats),
    }


def _render_briefing_card(entry: dict) -> str:
    """Render one entry as a Briefing-panel card.

    Title is a button reusing window._dashboardOpenEntry so the existing
    modal handles full-body display (no parallel render path).
    """
    rel_js = entry["knowledge_rel"].replace("'", "\\'")
    owner = entry["owner"]
    owner_html = (
        f'<span class="owner-badge owner-{html.escape(owner)}">{html.escape(owner)}</span>'
        if owner else ""
    )
    status = entry["status"]
    status_html = (
        f'<span class="status status-{html.escape(status)}">{html.escape(status)}</span>'
        if status else ""
    )
    summary = entry.get("summary", "")
    summary_html = (
        f'<p class="briefing-summary">{html.escape(summary)}</p>' if summary else ""
    )
    extra = ""
    if "days_stale" in entry:
        extra = f'<span class="briefing-meta">{entry["days_stale"]}d stale</span>'
    elif entry.get("updated"):
        extra = f'<span class="briefing-meta">updated {html.escape(entry["updated"])}</span>'
    return (
        '<div class="briefing-card">'
        '<div class="briefing-card-head">'
        f'<button type="button" class="briefing-title entry-link" '
        f'onclick="window._dashboardOpenEntry(\'{html.escape(rel_js)}\')">'
        f'{html.escape(entry["title"])}</button>'
        f'{owner_html}{status_html}{extra}'
        '</div>'
        f'{summary_html}'
        f'<code class="briefing-path">knowledge/{html.escape(entry["knowledge_rel"])}</code>'
        '</div>'
    )


def _render_briefing_section(data: dict) -> str:
    """Render the Briefing-mode container.

    Phase A: section is present in DOM but `hidden` (no UI toggle yet).
    Phase B will add a top-level [Index | Briefing] mode switch and CSS
    that flips `hidden` based on `body[data-mode="briefing"]`.
    """
    pinned = data["pinned"]
    if pinned:
        pinned_cards = "\n".join(_render_briefing_card(e) for e in pinned)
        pinned_html = (
            '<div class="briefing-panel" id="briefing-pinned">'
            f'<h3 class="briefing-h3">Pinned <span class="briefing-count">({len(pinned)})</span></h3>'
            f'<div class="briefing-grid">{pinned_cards}</div>'
            '</div>'
        )
    else:
        pinned_html = (
            '<div class="briefing-panel" id="briefing-pinned">'
            '<h3 class="briefing-h3">Pinned</h3>'
            '<p class="briefing-empty">No entries marked <code>briefing: pinned</code> yet. '
            'Each agent self-marks their long-term high-priority entries.</p>'
            '</div>'
        )

    rw = data["recent_writes"]
    rw_total = data["recent_writes_total"]
    if rw:
        rw_cards = "\n".join(_render_briefing_card(e) for e in rw)
        rw_more = f' <span class="briefing-meta">(+{rw_total - len(rw)} more)</span>' if rw_total > len(rw) else ""
        rw_html = (
            f'<h4 class="briefing-h4">Recent writes (last {data["window_days"]}d){rw_more}</h4>'
            f'<div class="briefing-grid">{rw_cards}</div>'
        )
    else:
        rw_html = (
            f'<h4 class="briefing-h4">Recent writes (last {data["window_days"]}d)</h4>'
            '<p class="briefing-empty">No knowledge writes in window.</p>'
        )

    stale = data["stale"]
    if stale:
        stale_cards = "\n".join(_render_briefing_card(e) for e in stale)
        stale_html = (
            f'<h4 class="briefing-h4">Stale entries (>{data["stale_days"]}d in '
            f'<code>{html.escape(", ".join(data["stale_categories"]))}/</code>)</h4>'
            f'<div class="briefing-grid">{stale_cards}</div>'
        )
    else:
        stale_html = (
            f'<h4 class="briefing-h4">Stale entries (>{data["stale_days"]}d in '
            f'<code>{html.escape(", ".join(data["stale_categories"]))}/</code>)</h4>'
            '<p class="briefing-empty">No stale entries — all decisions fresh within window.</p>'
        )

    iter_html = (
        '<div class="briefing-panel" id="briefing-iteration">'
        f'<h3 class="briefing-h3">Iteration brief</h3>'
        f'{rw_html}{stale_html}'
        '</div>'
    )

    seren_picks = data["serendipity_picks"]
    seren_pool = data["serendipity_pool_size"]
    if seren_picks:
        seren_cards = "\n".join(_render_briefing_card(e) for e in seren_picks)
        seren_html = (
            '<div class="briefing-panel" id="briefing-serendipity">'
            f'<h3 class="briefing-h3">Serendipity '
            f'<span class="briefing-count">({len(seren_picks)} of {seren_pool} this week)</span></h3>'
            f'<p class="briefing-doc">Rotates weekly; current ISO week <code>{html.escape(data["iso_week"])}</code>.</p>'
            f'<div class="briefing-grid">{seren_cards}</div>'
            '</div>'
        )
    else:
        seren_html = (
            '<div class="briefing-panel" id="briefing-serendipity">'
            '<h3 class="briefing-h3">Serendipity</h3>'
            '<p class="briefing-empty">No entries marked <code>briefing: serendipity</code> yet '
            '(or all are filtered by exclude_status / exclude_tags). '
            'Inspiration / occasionally-revisit material lives here.</p>'
            '</div>'
        )

    return f"""
<section id="briefing-section">
  <div class="briefing-head">
    <h2>Briefing <span class="briefing-week">{html.escape(data["iso_week"])}</span></h2>
    <p class="briefing-doc">Curated reading view — what to look at, not what to find. Pinned + Iteration + Serendipity are auto-aggregated from <code>briefing:</code> frontmatter and <code>config/briefing_config.json</code>. Switch back to Index for full filter / table / graph.</p>
  </div>
  {pinned_html}
  {iter_html}
  {seren_html}
</section>
"""


def _render_graph_section(
    explicit_data: dict, cooccur_data: dict,
) -> str:
    """Render the knowledge-relationship graph section with mode switch.

    Two datasets emitted as separate JSON islands:
      - graph-data-explicit  — supersedes/related/blocks from frontmatter
      - graph-data-cooccur   — entries sharing >= N tags (N from config)
    JS in _GRAPH_JS reads `data-graph-mode` on the section root and
    swaps cy.elements() on mode button click. Default mode is `explicit`
    (preserves prior behavior).
    """
    n_nodes_e = len(explicit_data["nodes"])
    n_edges_e = len(explicit_data["edges"])
    n_edges_c = len(cooccur_data["edges"])
    threshold = cooccur_data.get("threshold", 2)
    payload_e = json.dumps(explicit_data, ensure_ascii=False).replace("</", "<\\/")
    payload_c = json.dumps(cooccur_data, ensure_ascii=False).replace("</", "<\\/")
    return f"""
<section id="graph-section" data-graph-mode="explicit">
  <div class="graph-head">
    <h2>Knowledge Graph
      <span class="graph-count" id="graph-count">({n_nodes_e} nodes · {n_edges_e} edges)</span>
    </h2>
    <div class="graph-mode-bar">
      <button type="button" class="graph-mode-btn active" data-graph-mode-btn="explicit">Explicit links</button>
      <button type="button" class="graph-mode-btn" data-graph-mode-btn="cooccur">Tag co-occurrence (≥{threshold})</button>
    </div>
    <div class="graph-controls">
      <label class="graph-toggle">
        <input type="checkbox" id="graph-hide-isolated" checked>
        hide isolated
      </label>
      <button type="button" class="gchip" id="graph-relayout">re-layout</button>
      <button type="button" class="gchip" id="graph-fit">fit</button>
      <button type="button" class="gchip" id="graph-collapse">hide</button>
    </div>
  </div>
  <div class="graph-legend" id="graph-legend-explicit">
    <span class="lg-edge lg-supersedes">— supersedes →</span>
    <span class="lg-edge lg-related">- - related - -</span>
    <span class="lg-edge lg-blocks">— blocks →</span>
    <span class="lg-sep">·</span>
    <span class="lg-node owner-rules">rules</span>
    <span class="lg-node owner-trade">trade</span>
    <span class="lg-node owner-data">data</span>
    <span class="lg-node owner-research">research</span>
    <span class="lg-node owner-core">core</span>
  </div>
  <div class="graph-legend" id="graph-legend-cooccur" hidden>
    <span class="lg-edge lg-cooccur">— shared {threshold}+ tags —</span>
    <span class="lg-meta">edge thickness ∝ shared-tag count · {n_edges_c} edges total</span>
    <span class="lg-sep">·</span>
    <span class="lg-node owner-rules">rules</span>
    <span class="lg-node owner-trade">trade</span>
    <span class="lg-node owner-data">data</span>
    <span class="lg-node owner-research">research</span>
    <span class="lg-node owner-core">core</span>
  </div>
  <div id="graph-canvas"><div id="graph-tip"></div></div>
  <script type="application/json" id="graph-data-explicit">{payload_e}</script>
  <script type="application/json" id="graph-data-cooccur">{payload_c}</script>
</section>
"""


_DASHBOARD_JS = """
// ============================================================================
// URL HASH STATE — multi-key persistence layer (P2-c, 2026-05-06)
// ----------------------------------------------------------------------------
// Hash schema: #k1=v1&k2=v2 with URL-encoded values. Empty/default values
// are omitted from the hash so a clean default state produces an empty hash.
//
// Recognized keys:
//   mode    : 'briefing'      (default 'index' is omitted)
//   owner   : 'rules' | ...   (default '' is omitted)
//   status  : 'active' | ...
//   tag     : <tag>
//   q       : <search>
//   stale   : '1' (toggle filter on; default off omitted)
//   entry   : <knowledge_rel> (modal target; transient, restored on close)
//
// Backward compat with the pre-P2-c single-token forms:
//   #briefing       -> {mode: 'briefing'}
//   #entry/<rel>    -> {entry: '<rel>'}
//
// Two-IIFE coordination: both filter and mode-toggle IIFEs call into
// window._dashboardHashSerialize(state) which they pass their own state
// fragment. The merge happens via window._dashboardHashState (a snapshot
// of last-applied hash kept globally so partial writes don't clobber
// keys the writer doesn't know about).
window._dashboardHashState = {};

window._dashboardHashParse = function(hash) {
  hash = hash || window.location.hash || '';
  if (hash.charAt(0) === '#') hash = hash.substring(1);
  var out = { mode: '', owner: '', status: '', tag: '', q: '', stale: '', entry: '' };
  if (!hash) return out;
  // Backward-compat single-token forms
  if (hash === 'briefing') { out.mode = 'briefing'; return out; }
  if (hash === 'index') { out.mode = 'index'; return out; }
  if (hash.indexOf('entry/') === 0) {
    try { out.entry = decodeURIComponent(hash.substring('entry/'.length)); } catch (e) {}
    return out;
  }
  // Multi-key form
  var pairs = hash.split('&');
  for (var i = 0; i < pairs.length; i++) {
    var eq = pairs[i].indexOf('=');
    if (eq < 0) continue;
    var k = pairs[i].substring(0, eq);
    var v = pairs[i].substring(eq + 1);
    try { v = decodeURIComponent(v); } catch (e) {}
    if (k in out) out[k] = v;
  }
  return out;
};

window._dashboardHashSerialize = function(state) {
  // Merge incoming state fragment over the cached state, then drop defaults
  var merged = window._dashboardHashState;
  for (var k in state) {
    if (Object.prototype.hasOwnProperty.call(state, k)) {
      merged[k] = state[k];
    }
  }
  var parts = [];
  // index is the default mode -> omit when mode==='index'
  if (merged.mode && merged.mode !== 'index') parts.push('mode=' + encodeURIComponent(merged.mode));
  if (merged.owner) parts.push('owner=' + encodeURIComponent(merged.owner));
  if (merged.status) parts.push('status=' + encodeURIComponent(merged.status));
  if (merged.tag) parts.push('tag=' + encodeURIComponent(merged.tag));
  if (merged.q) parts.push('q=' + encodeURIComponent(merged.q));
  if (merged.stale) parts.push('stale=1');
  if (merged.entry) parts.push('entry=' + encodeURIComponent(merged.entry));
  var newHash = parts.length ? '#' + parts.join('&') : '';
  // replaceState (not pushState) so back button doesn't accumulate every
  // keystroke in the search box; users still get a back-stop entry from
  // any link-followed navigation onto the page
  try {
    var url = window.location.pathname + window.location.search + newHash;
    if (url !== window.location.pathname + window.location.search + window.location.hash) {
      history.replaceState(null, '', url);
    }
  } catch (e) {}
};

// ============================================================================
// MODAL API -- defined BEFORE the IIFE on purpose.
//
// JavaScript hoists function declarations within the same script tag, so the
// `function _dashboardOpenEntry(...)` declarations below become available the
// moment the script tag begins executing. BUT the `window._dashboardOpenEntry
// = ...` lines are plain assignments that run in source order. If they were
// placed AFTER the IIFE and the IIFE threw an uncaught error mid-way, the
// browser would terminate this script tag's remaining execution and the
// window assignment would never run -- leaving inline onclick handlers with
// `window._dashboardOpenEntry is not a function` (round 4 failure mode
// observed 2026-04-30).
//
// Putting both the function declarations AND the window expose BEFORE the
// IIFE makes the modal API available regardless of whether the IIFE later
// blows up. The IIFE retains only search/filter/chip-tag concerns.
// ============================================================================

function _dashboardOpenEntry(rel) {
  // Use _dashboardEnsureModal() (defined in HEAD <script>) as the modal
  // accessor so the function survives the "entry-modal element exists in
  // HTML source but getElementById returns null" file:// browser quirk.
  // 2026-05-12: pre-existing architecture bug — the head <script> defined
  // a window._dashboardOpenEntry that used ensure-modal, but THIS body
  // function then overrode it via `window._dashboardOpenEntry = _dashboardOpenEntry`
  // (line ~1952). Fix is to align body version with head's defense.
  var modal = (typeof _dashboardEnsureModal === 'function')
    ? _dashboardEnsureModal()
    : document.getElementById('entry-modal');
  var modalBody = document.getElementById('modal-body');
  var modalTitle = document.getElementById('modal-title');
  var modalPath = document.getElementById('modal-path');
  if (!modal || !modalBody) return;
  var src = null;
  var bodies = document.querySelectorAll('[data-entry-body]');
  for (var i = 0; i < bodies.length; i++) {
    if (bodies[i].getAttribute('data-entry-body') === rel) {
      src = bodies[i];
      break;
    }
  }
  if (!src) return;
  modalBody.innerHTML = src.innerHTML;
  if (modalTitle) modalTitle.textContent = src.dataset.entryTitle || '';
  if (modalPath) modalPath.textContent = src.dataset.entryPath || '';
  // Both visibility paths: dynamically-ensured modals have inline
  // style display:none (won't yield to just clearing the hidden attr),
  // and HTML-rendered modals respond to hidden attr removal via CSS.
  modal.style.display = 'flex';
  modal.removeAttribute('hidden');
  document.body.style.overflow = 'hidden';
  modalBody.scrollTop = 0;
  // P2-c: persist entry rel to URL hash so a copy-pasted URL re-opens
  // the same modal. Other filter state preserved by the merging serializer.
  if (typeof window._dashboardHashSerialize === 'function') {
    window._dashboardHashSerialize({ entry: rel });
  }
  if (typeof mermaid !== 'undefined') {
    var mNodes = modalBody.querySelectorAll('.mermaid');
    if (mNodes.length) {
      try {
        mermaid.run({ nodes: mNodes });
        // Attach click-to-zoom handlers after render. Each .mermaid
        // becomes a "click to enlarge" target. The CSS sets cursor:
        // zoom-in and pointer-events:none on the inner svg so clicks
        // always fall through to the .mermaid wrapper itself.
        for (var mi = 0; mi < mNodes.length; mi++) {
          (function(node) {
            node.addEventListener('click', function(e) {
              var svg = node.querySelector('svg');
              if (!svg) return;
              e.stopPropagation();
              _dashboardOpenMermaidZoom(svg.outerHTML);
            });
          })(mNodes[mi]);
        }
      }
      catch (err) { /* ignore */ }
    }
  }
}

// Click-to-zoom modal for mermaid diagrams with wheel-zoom + drag-pan.
// Separate from entry modal (z-index 200 vs 100). Lazy-creates DOM
// on first open. Close: backdrop click / Escape / close button.
//
// Zoom controls:
//   - Mouse wheel        -> zoom in/out around cursor
//   - Click + drag       -> pan
//   - + / =              -> zoom in
//   - - / _              -> zoom out
//   - 0                  -> fit to screen
//   - Toolbar buttons    -> + / - / fit / reset(1:1)
// Sharp-zoom strategy: instead of CSS `transform: scale()` (which
// rasterizes the SVG at original size then magnifies, blurring text),
// we adjust the SVG's `width`/`height` attributes directly. The browser
// then re-rasterizes from the vector at the new dimensions, keeping
// text crisp. Translate is still done via CSS transform (translate
// alone does not blur).
var _mermaidZoomState = {
  scale: 1, tx: 0, ty: 0,
  svg: null, content: null,
  naturalW: 1, naturalH: 1
};

function _mermaidApplyTransform() {
  var s = _mermaidZoomState;
  if (!s.svg) return;
  var w = s.naturalW * s.scale;
  var h = s.naturalH * s.scale;
  s.svg.setAttribute('width', w);
  s.svg.setAttribute('height', h);
  // Translate-only transform (no scale) keeps text crisp.
  s.svg.style.transform = 'translate(' + s.tx + 'px,' + s.ty + 'px)';
  var label = document.getElementById('mermaid-zoom-scale');
  if (label) label.textContent = Math.round(s.scale * 100) + '%';
}

function _mermaidCaptureNaturalSize() {
  // Determine SVG's natural pixel size at scale=1. Prefer viewBox
  // (always present in mermaid output); fall back to bounding rect.
  var s = _mermaidZoomState;
  if (!s.svg) return;
  var vb = null;
  try { vb = s.svg.viewBox && s.svg.viewBox.baseVal; } catch (e) {}
  if (vb && vb.width && vb.height) {
    s.naturalW = vb.width;
    s.naturalH = vb.height;
    return;
  }
  // Reset attrs + measure
  var prevW = s.svg.getAttribute('width');
  var prevH = s.svg.getAttribute('height');
  s.svg.removeAttribute('width');
  s.svg.removeAttribute('height');
  var rect = s.svg.getBoundingClientRect();
  s.naturalW = rect.width || 800;
  s.naturalH = rect.height || 600;
  if (prevW) s.svg.setAttribute('width', prevW);
  if (prevH) s.svg.setAttribute('height', prevH);
}

function _mermaidFitToScreen() {
  var s = _mermaidZoomState;
  if (!s.svg || !s.content) return;
  var rect = s.content.getBoundingClientRect();
  var pad = 40;
  var fitX = (rect.width - pad * 2) / s.naturalW;
  var fitY = (rect.height - pad * 2) / s.naturalH;
  s.scale = Math.min(fitX, fitY, 4);  // cap fit-up at 4x
  if (s.scale < 0.05) s.scale = 0.05;
  // Center
  s.tx = (rect.width - s.naturalW * s.scale) / 2;
  s.ty = (rect.height - s.naturalH * s.scale) / 2;
  _mermaidApplyTransform();
}

function _mermaidZoomBy(factor, anchorX, anchorY) {
  var s = _mermaidZoomState;
  if (!s.svg || !s.content) return;
  var rect = s.content.getBoundingClientRect();
  if (anchorX === undefined) anchorX = rect.width / 2;
  if (anchorY === undefined) anchorY = rect.height / 2;
  var newScale = s.scale * factor;
  if (newScale < 0.05) newScale = 0.05;
  if (newScale > 20) newScale = 20;
  // Keep anchor point fixed in screen space
  var ratio = newScale / s.scale;
  s.tx = anchorX - ratio * (anchorX - s.tx);
  s.ty = anchorY - ratio * (anchorY - s.ty);
  s.scale = newScale;
  _mermaidApplyTransform();
}

function _dashboardOpenMermaidZoom(svgHtml) {
  var zoom = document.getElementById('mermaid-zoom-modal');
  if (!zoom) {
    zoom = document.createElement('div');
    zoom.id = 'mermaid-zoom-modal';
    var content = document.createElement('div');
    content.id = 'mermaid-zoom-content';
    zoom.appendChild(content);

    var controls = document.createElement('div');
    controls.id = 'mermaid-zoom-controls';
    var btnIn = document.createElement('button');
    btnIn.type = 'button'; btnIn.textContent = '+'; btnIn.title = 'Zoom in (+/=)';
    btnIn.addEventListener('click', function(e) { e.stopPropagation(); _mermaidZoomBy(1.25); });
    var btnOut = document.createElement('button');
    btnOut.type = 'button'; btnOut.textContent = '−'; btnOut.title = 'Zoom out (-)';
    btnOut.addEventListener('click', function(e) { e.stopPropagation(); _mermaidZoomBy(0.8); });
    var btnFit = document.createElement('button');
    btnFit.type = 'button'; btnFit.textContent = '⤢'; btnFit.title = 'Fit to screen (0)';
    btnFit.addEventListener('click', function(e) { e.stopPropagation(); _mermaidFitToScreen(); });
    var btnReset = document.createElement('button');
    btnReset.type = 'button'; btnReset.textContent = '1:1'; btnReset.title = 'Reset to 100%';
    btnReset.style.width = 'auto'; btnReset.style.padding = '0 8px';
    btnReset.addEventListener('click', function(e) {
      e.stopPropagation();
      var s = _mermaidZoomState;
      s.scale = 1;
      var rect = s.content.getBoundingClientRect();
      s.tx = (rect.width - s.naturalW * s.scale) / 2;
      s.ty = (rect.height - s.naturalH * s.scale) / 2;
      _mermaidApplyTransform();
    });
    var scaleLabel = document.createElement('span');
    scaleLabel.id = 'mermaid-zoom-scale';
    scaleLabel.textContent = '100%';
    controls.appendChild(btnOut);
    controls.appendChild(scaleLabel);
    controls.appendChild(btnIn);
    controls.appendChild(btnFit);
    controls.appendChild(btnReset);
    zoom.appendChild(controls);

    var closeBtn = document.createElement('button');
    closeBtn.id = 'mermaid-zoom-close';
    closeBtn.type = 'button';
    closeBtn.textContent = '×';
    closeBtn.setAttribute('aria-label', 'Close zoom');
    closeBtn.addEventListener('click', function(e) {
      e.stopPropagation();
      _dashboardCloseMermaidZoom();
    });
    zoom.appendChild(closeBtn);

    var hint = document.createElement('div');
    hint.id = 'mermaid-zoom-hint';
    hint.textContent = 'wheel: zoom · drag: pan · +/-: zoom · 0: fit · Esc: close';
    zoom.appendChild(hint);

    // Wheel-to-zoom (anchor at cursor)
    content.addEventListener('wheel', function(e) {
      e.preventDefault();
      var rect = content.getBoundingClientRect();
      var ax = e.clientX - rect.left;
      var ay = e.clientY - rect.top;
      var factor = e.deltaY < 0 ? 1.12 : (1 / 1.12);
      _mermaidZoomBy(factor, ax, ay);
    }, { passive: false });

    // Drag-to-pan
    var dragging = false, dragStartX = 0, dragStartY = 0, startTx = 0, startTy = 0;
    var dragMoved = false;
    content.addEventListener('mousedown', function(e) {
      if (e.button !== 0) return;
      dragging = true;
      dragMoved = false;
      dragStartX = e.clientX; dragStartY = e.clientY;
      startTx = _mermaidZoomState.tx; startTy = _mermaidZoomState.ty;
      content.classList.add('dragging');
      e.preventDefault();
    });
    document.addEventListener('mousemove', function(e) {
      if (!dragging) return;
      dragMoved = true;
      _mermaidZoomState.tx = startTx + (e.clientX - dragStartX);
      _mermaidZoomState.ty = startTy + (e.clientY - dragStartY);
      _mermaidApplyTransform();
    });
    document.addEventListener('mouseup', function() {
      if (dragging) { dragging = false; content.classList.remove('dragging'); }
    });

    // Backdrop click closes (only when not actively dragging)
    content.addEventListener('click', function(e) {
      if (e.target === content && !dragMoved) {
        _dashboardCloseMermaidZoom();
      }
    });

    document.body.appendChild(zoom);
  }

  var contentEl = document.getElementById('mermaid-zoom-content');
  contentEl.innerHTML = svgHtml;
  _mermaidZoomState.content = contentEl;
  _mermaidZoomState.svg = contentEl.querySelector('svg');
  _mermaidZoomState.scale = 1;
  _mermaidZoomState.tx = 0;
  _mermaidZoomState.ty = 0;
  // Strip max-width / max-height constraints from the cloned SVG so
  // setAttribute('width', ...) actually grows it. The original entry-
  // modal CSS caps SVGs at 100% width, which would prevent zoom-in.
  if (_mermaidZoomState.svg) {
    _mermaidZoomState.svg.style.maxWidth = 'none';
    _mermaidZoomState.svg.style.maxHeight = 'none';
  }
  zoom.hidden = false;
  // Capture natural size BEFORE first fit
  _mermaidCaptureNaturalSize();
  // Fit on open so user sees full diagram first
  setTimeout(_mermaidFitToScreen, 0);
}

function _dashboardCloseMermaidZoom() {
  var zoom = document.getElementById('mermaid-zoom-modal');
  if (zoom) zoom.hidden = true;
}

window._dashboardOpenMermaidZoom = _dashboardOpenMermaidZoom;
window._dashboardCloseMermaidZoom = _dashboardCloseMermaidZoom;

function _dashboardCloseEntry() {
  var modal = document.getElementById('entry-modal');
  if (!modal) return;
  modal.style.display = 'none';
  modal.setAttribute('hidden', 'hidden');
  document.body.style.overflow = '';
  // Multi-key hash schema (P2-c): clear entry param, preserve other state
  if (typeof window._dashboardHashSerialize === 'function') {
    window._dashboardHashSerialize({ entry: '' });
  }
}

function _dashboardOpenEntryFromHash() {
  // Multi-key hash schema (P2-c): look at entry param via central parser
  if (typeof window._dashboardHashParse !== 'function') return;
  var h = window._dashboardHashParse();
  if (h.entry) {
    try { _dashboardOpenEntry(h.entry); } catch (err) {}
  }
}

// Expose to window.* so inline onclick="window._dashboardOpenEntry(...)"
// works. This runs RIGHT NOW, before the IIFE; an IIFE error later cannot
// undo this assignment.
window._dashboardOpenEntry = _dashboardOpenEntry;
window._dashboardCloseEntry = _dashboardCloseEntry;
window._dashboardOpenEntryFromHash = _dashboardOpenEntryFromHash;

// Wire up modal close / Escape / backdrop / hashchange. Run on
// DOMContentLoaded so element lookups always succeed.
function _dashboardWireModal() {
  var modal = document.getElementById('entry-modal');
  var modalClose = document.getElementById('modal-close');
  if (modalClose) modalClose.addEventListener('click', _dashboardCloseEntry);
  if (modal) {
    modal.addEventListener('click', function(e) {
      if (e.target === modal) _dashboardCloseEntry();
    });
  }
  document.addEventListener('keydown', function(e) {
    var zoom = document.getElementById('mermaid-zoom-modal');
    var zoomOpen = zoom && !zoom.hidden;
    if (e.key === 'Escape') {
      // Mermaid zoom modal takes precedence (it's the topmost).
      if (zoomOpen) { _dashboardCloseMermaidZoom(); return; }
      if (modal && !modal.hidden) _dashboardCloseEntry();
      return;
    }
    // Zoom keyboard shortcuts only when zoom modal is open
    if (!zoomOpen) return;
    // Don't capture if user is typing into an input
    var ae = document.activeElement;
    if (ae && (ae.tagName === 'INPUT' || ae.tagName === 'TEXTAREA')) return;
    if (e.key === '+' || e.key === '=') {
      e.preventDefault(); _mermaidZoomBy(1.25);
    } else if (e.key === '-' || e.key === '_') {
      e.preventDefault(); _mermaidZoomBy(0.8);
    } else if (e.key === '0') {
      e.preventDefault(); _mermaidFitToScreen();
    }
  });
  _dashboardOpenEntryFromHash();
  window.addEventListener('hashchange', _dashboardOpenEntryFromHash);
}
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', _dashboardWireModal);
} else {
  _dashboardWireModal();
}

// ============================================================================
// IIFE: search / filter / chips. Isolated from modal API on purpose -- if
// anything in here throws, modal still works.
// ============================================================================

(function() {
  var search = document.getElementById('search');
  var resultCount = document.getElementById('result-count');
  var tagRow = document.getElementById('tag-filter-row');
  var activeTagEl = document.getElementById('active-tag');
  var clearTagBtn = document.getElementById('clear-tag');
  var clearAllBtn = document.getElementById('clear-all');
  var staleBtn = document.getElementById('stale-indicator');
  var state = { query: '', owner: '', status: '', tag: '', stale: false };

  function isAnyFilterActive() {
    return !!(state.query || state.owner || state.status || state.tag || state.stale);
  }

  function apply() {
    var q = state.query;
    var visible = 0, hidden = 0;
    var rows = document.querySelectorAll('[data-entry]');
    for (var i = 0; i < rows.length; i++) {
      var r = rows[i];
      var okQ = !q || (r.dataset.search || '').indexOf(q) !== -1;
      var okO = !state.owner || r.dataset.owner === state.owner;
      var okS = !state.status || r.dataset.status === state.status;
      var rowTags = (r.dataset.tags || '').split(' ');
      var okT = !state.tag || rowTags.indexOf(state.tag) !== -1;
      var okStale = !state.stale || r.dataset.stale === '1';
      var show = okQ && okO && okS && okT && okStale;
      r.classList.toggle('hidden', !show);
      if (show) visible++; else hidden++;
    }
    // Hide category sections that now have zero visible cards.
    // Exempt sections without any [data-entry] cards (static embeds like
    // the skills tier index): they don't participate in entry-level
    // filters, so the count-based hide would erase them on every render.
    var sections = document.querySelectorAll('section.cat');
    for (var j = 0; j < sections.length; j++) {
      var sec = sections[j];
      var totalCards = sec.querySelectorAll('[data-entry]').length;
      if (totalCards === 0) {
        sec.classList.remove('hidden');
        continue;
      }
      var any = sec.querySelectorAll('[data-entry]:not(.hidden)').length > 0;
      sec.classList.toggle('hidden', !any);
    }
    // Reflect state.owner in owner-tab active class (kept in sync whether
    // the owner change came from a tab click or an in-card owner-pill click)
    var tabs = document.querySelectorAll('button.owner-tab');
    for (var t = 0; t < tabs.length; t++) {
      tabs[t].classList.toggle('active', tabs[t].dataset.ownerTab === state.owner);
    }
    // Reflect state.stale on the stale-indicator (filter-on visual state)
    if (staleBtn) staleBtn.classList.toggle('stale-filter-on', !!state.stale);
    // Persist filter state to URL hash so refresh / share / back-button
    // restores the exact view (P2-c)
    if (typeof window._dashboardHashSerialize === 'function') {
      window._dashboardHashSerialize({
        owner: state.owner || '',
        status: state.status || '',
        tag: state.tag || '',
        q: state.query || '',
        stale: state.stale ? '1' : '',
      });
    }
    var active = isAnyFilterActive();
    resultCount.textContent = (active ? '[FILTERED] ' : '') + visible + ' of ' + rows.length + ' entries';
    resultCount.classList.toggle('result-count-active', active);
    if (clearAllBtn) clearAllBtn.hidden = !active;
    if (typeof window._dashboardSyncGraph === 'function') {
      try { window._dashboardSyncGraph(state); } catch (e) {}
    }
  }

  search.addEventListener('input', function(e) {
    state.query = e.target.value.trim().toLowerCase();
    apply();
  });

  document.addEventListener('click', function(e) {
    // Skill tier-index link click → open the rendered .md in the modal
    // (same UX as knowledge entries). data-skill-modal carries the skill
    // name; the body lives under data-entry-body="skill:<name>" in the
    // hidden entry-bodies block, emitted by _render_skill_entry_bodies.
    var skillLink = e.target.closest('a[data-skill-modal]');
    if (skillLink) {
      e.preventDefault();
      var name = skillLink.getAttribute('data-skill-modal');
      if (name && typeof window._dashboardOpenEntry === 'function') {
        window._dashboardOpenEntry('skill:' + name);
      }
      return;
    }
    // Owner tab (top-level) click — drives state.owner the same as the
    // old owner chip row did
    var tab = e.target.closest('button.owner-tab');
    if (tab) {
      state.owner = tab.dataset.ownerTab || '';
      apply();
      return;
    }
    // In-card owner pill click — clicking the owner badge inside an
    // entry card filters to that owner (faster than scrolling back up)
    var ownerPill = e.target.closest('[data-owner-click]');
    if (ownerPill) {
      state.owner = ownerPill.dataset.ownerClick || '';
      apply();
      // Stop propagation so the card's title button doesn't also fire
      e.stopPropagation();
      return;
    }
    var chip = e.target.closest('button.chip');
    if (chip && chip.id !== 'clear-tag') {
      var f = chip.dataset.filter;
      var v = chip.dataset.value;
      if (f === 'status') state.status = v;
      // Update active-class on sibling chips in the same filter group
      var siblings = document.querySelectorAll('button.chip[data-filter="' + f + '"]');
      for (var k = 0; k < siblings.length; k++) {
        siblings[k].classList.toggle('active', siblings[k] === chip);
      }
      apply();
      return;
    }
    var tagEl = e.target.closest('.tag[data-tag]');
    if (tagEl) {
      state.tag = tagEl.dataset.tag;
      activeTagEl.textContent = state.tag;
      tagRow.style.display = 'flex';
      apply();
    }
  });

  clearTagBtn.addEventListener('click', function() {
    state.tag = '';
    tagRow.style.display = 'none';
    apply();
  });

  if (clearAllBtn) {
    clearAllBtn.addEventListener('click', function() {
      state.query = '';
      state.owner = '';
      state.status = '';
      state.tag = '';
      state.stale = false;
      if (search) search.value = '';
      tagRow.style.display = 'none';
      // Reset chip active classes back to "all"
      var chips = document.querySelectorAll('button.chip[data-filter]');
      for (var i = 0; i < chips.length; i++) {
        var c = chips[i];
        c.classList.toggle('active', c.dataset.value === '');
      }
      apply();
    });
  }

  // Stale indicator: toggles state.stale when count > 0; gray no-op
  // when count = 0 (positive zero state, no filter to apply)
  if (staleBtn) {
    staleBtn.addEventListener('click', function() {
      var count = parseInt(staleBtn.dataset.staleCount, 10) || 0;
      if (count === 0) return;
      state.stale = !state.stale;
      apply();
    });
  }

  // Initial hash restoration (P2-c): if URL hash carries filter state,
  // hydrate state and chip/tab UI before first apply()
  function _hydrateFromHash() {
    if (typeof window._dashboardHashParse !== 'function') return;
    var h = window._dashboardHashParse();
    state.query = h.q || '';
    state.owner = h.owner || '';
    state.status = h.status || '';
    state.tag = h.tag || '';
    state.stale = h.stale === '1';
    if (search) search.value = state.query;
    if (state.tag) {
      activeTagEl.textContent = state.tag;
      tagRow.style.display = 'flex';
    }
    // Reflect chip active states for status (owner uses tabs, handled in apply)
    var statusChips = document.querySelectorAll('button.chip[data-filter="status"]');
    for (var i = 0; i < statusChips.length; i++) {
      statusChips[i].classList.toggle('active', statusChips[i].dataset.value === state.status);
    }
    // Cache the parsed snapshot so subsequent partial writes preserve unknown keys
    window._dashboardHashState = h;
  }
  _hydrateFromHash();

  // hashchange listener: re-hydrate on browser back/forward
  window.addEventListener('hashchange', function() {
    var h = window._dashboardHashParse();
    // If only entry param differs (modal open/close), don't re-apply filter
    if (h.entry !== window._dashboardHashState.entry) {
      window._dashboardHashState.entry = h.entry;
      return;
    }
    _hydrateFromHash();
    apply();
  });

  apply();
})();

// Mode toggle (Index / Briefing). Reads URL hash on load: '#briefing'
// activates Briefing mode, anything else (including '' or '#entry/X')
// keeps the page-default Index. Click handler updates body.dataset.mode,
// active-class on buttons, and replaces URL hash for shareability.
//
// Modal interaction: opening an entry sets hash to '#entry/...' and the
// existing close handler (window._dashboardCloseEntry) restores the
// current mode's hash on close — so modal-open+refresh stays in mode
// until the user explicitly switches.
//
// Defensive: nothing here depends on cytoscape / mermaid being loaded.
(function() {
  var indexBtn = document.getElementById('mode-btn-index');
  var briefingBtn = document.getElementById('mode-btn-briefing');
  if (!indexBtn || !briefingBtn) return;

  function setMode(mode) {
    document.body.dataset.mode = mode;
    indexBtn.classList.toggle('active', mode === 'index');
    briefingBtn.classList.toggle('active', mode === 'briefing');
    // Persist mode via the multi-key hash serializer (P2-c) — coexists
    // with owner/status/tag/q filter keys without clobbering them
    if (typeof window._dashboardHashSerialize === 'function') {
      window._dashboardHashSerialize({ mode: mode });
    }
  }

  indexBtn.addEventListener('click', function() { setMode('index'); });
  briefingBtn.addEventListener('click', function() { setMode('briefing'); });

  // Initial: parse multi-key hash for `mode`; fallback to legacy single-token
  var initial = 'index';
  if (typeof window._dashboardHashParse === 'function') {
    var h = window._dashboardHashParse();
    if (h.mode === 'briefing') initial = 'briefing';
  }
  setMode(initial);
})();
"""


# Graph init: parses the JSON island in #graph-data, boots a cytoscape
# instance into #graph-canvas, wires owner-color + edge-type styling,
# and exposes window._dashboardSyncGraph(state) so the IIFE filter
# loop above can hide nodes/edges to mirror the table view.
#
# Cytoscape is loaded from the vendored asset copied next to dashboard.html
# (`./assets/vendor/cytoscape/cytoscape.min.js`, see `build()`); if the
# asset is missing or the script fails to execute, the graph section
# silently no-ops — the rest of the dashboard stays usable.
_GRAPH_JS = """
(function() {
  if (typeof cytoscape === 'undefined') {
    var sec = document.getElementById('graph-section');
    if (sec) {
      var canvas = document.getElementById('graph-canvas');
      if (canvas) canvas.innerHTML =
        '<div class="graph-error">cytoscape failed to load (offline?). ' +
        'Graph view unavailable; entry table below still works.</div>';
    }
    return;
  }
  // P2-a: two datasets (explicit links + tag co-occurrence). Initial mode
  // is `explicit` per the section's data-graph-mode attribute; mode buttons
  // swap cy.elements() in place without re-creating the cytoscape instance.
  var explicitEl = document.getElementById('graph-data-explicit');
  var cooccurEl = document.getElementById('graph-data-cooccur');
  var datasets = { explicit: null, cooccur: null };
  try { if (explicitEl) datasets.explicit = JSON.parse(explicitEl.textContent); } catch (e) {}
  try { if (cooccurEl) datasets.cooccur = JSON.parse(cooccurEl.textContent); } catch (e) {}
  if (!datasets.explicit || !datasets.explicit.nodes) return;
  var graphData = datasets.explicit;

  var ownerColor = {
    rules:    '#bc8fd8',
    trade:    '#8fbcd8',
    data:     '#d8bc8f',
    research: '#8fd8bc',
    core:     '#d8a88f',
    unknown:  '#888888'
  };

  var elements = graphData.nodes.concat(graphData.edges);

  var cy = cytoscape({
    container: document.getElementById('graph-canvas'),
    elements: elements,
    wheelSensitivity: 0.2,
    style: [
      { selector: 'node', style: {
          'background-color': function(ele) {
            return ownerColor[ele.data('owner')] || ownerColor.unknown;
          },
          'label': 'data(label)',
          'color': '#ddd',
          'font-size': 10,
          'font-family': '-apple-system, Segoe UI, sans-serif',
          'text-valign': 'bottom',
          'text-halign': 'center',
          'text-margin-y': 4,
          'text-outline-color': '#1a1a1a',
          'text-outline-width': 2,
          'text-max-width': 120,
          'text-wrap': 'ellipsis',
          'border-color': '#1a1a1a',
          'border-width': 1,
          'width': function(ele) {
            return Math.max(14, Math.min(38, 14 + 4 * ele.data('degree')));
          },
          'height': function(ele) {
            return Math.max(14, Math.min(38, 14 + 4 * ele.data('degree')));
          }
      }},
      { selector: 'node.dimmed', style: {
          'opacity': 0.15,
          'text-opacity': 0
      }},
      { selector: 'node.hidden', style: {
          'display': 'none'
      }},
      { selector: 'node.archived, node[status = "archived"], node[status = "deprecated"]', style: {
          'background-opacity': 0.55,
          'border-color': '#555',
          'border-style': 'dashed'
      }},
      { selector: 'edge', style: {
          'curve-style': 'bezier',
          'width': 1.4,
          'opacity': 0.85
      }},
      { selector: 'edge[type = "supersedes"]', style: {
          'line-color': '#a88fbc',
          'target-arrow-color': '#a88fbc',
          'target-arrow-shape': 'triangle',
          'arrow-scale': 1.0,
          'width': 2
      }},
      { selector: 'edge[type = "blocks"]', style: {
          'line-color': '#d88f8f',
          'target-arrow-color': '#d88f8f',
          'target-arrow-shape': 'triangle',
          'arrow-scale': 1.0,
          'width': 2
      }},
      { selector: 'edge[type = "related"]', style: {
          'line-color': '#666',
          'line-style': 'dashed',
          'width': 1
      }},
      { selector: 'edge[type = "cooccur"]', style: {
          'line-color': '#5a8fa8',
          'opacity': 0.6,
          'curve-style': 'haystack',
          'haystack-radius': 0.4,
          'width': function(ele) {
            // Width 1.0 at weight 2; +0.7 per extra shared tag; cap at 4
            var w = ele.data('weight') || 2;
            return Math.min(4, 1.0 + 0.7 * (w - 2));
          }
      }},
      { selector: 'edge.hidden', style: {
          'display': 'none'
      }},
      { selector: 'node:selected', style: {
          'border-color': '#9cdcfe',
          'border-width': 3
      }}
    ],
    layout: {
      name: 'cose',
      idealEdgeLength: 90,
      nodeOverlap: 8,
      gravity: 0.25,
      numIter: 1200,
      fit: true,
      padding: 30,
      animate: false
    }
  });

  // Click node -> open existing entry modal (same path as table-row click)
  cy.on('tap', 'node', function(evt) {
    var rel = evt.target.id();
    if (window._dashboardOpenEntry) {
      try { window._dashboardOpenEntry(rel); } catch (e) {}
    }
  });

  // Tooltip via title attr on the canvas — cytoscape doesn't render
  // native tooltips, so we use mouseover to update an in-page label
  var tipEl = document.getElementById('graph-tip');
  cy.on('mouseover', 'node', function(evt) {
    if (!tipEl) return;
    var n = evt.target;
    tipEl.textContent = n.data('label') + '  ·  ' + n.id() +
      '  ·  owner=' + n.data('owner') +
      (n.data('status') ? '  ·  ' + n.data('status') : '') +
      '  ·  degree=' + n.data('degree');
    tipEl.style.opacity = '1';
  });
  cy.on('mouseout', 'node', function() {
    if (tipEl) tipEl.style.opacity = '0';
  });

  // Sync filter state from the IIFE: hide nodes whose owner/status/tag/
  // search don't match. Edges are auto-hidden when either endpoint is.
  function syncFromState(state) {
    var hideIso = document.getElementById('graph-hide-isolated');
    var hideIsolated = hideIso ? hideIso.checked : false;
    var q = (state && state.query) || '';
    var owner = (state && state.owner) || '';
    var status = (state && state.status) || '';
    var tag = (state && state.tag) || '';

    cy.batch(function() {
      cy.nodes().forEach(function(n) {
        var d = n.data();
        var okQ = !q || (d.search || '').indexOf(q) !== -1;
        var okO = !owner || d.owner === owner;
        var okS = !status || d.status === status;
        var nodeTags = (d.tags || '').split(' ');
        var okT = !tag || nodeTags.indexOf(tag) !== -1;
        n.toggleClass('hidden', !(okQ && okO && okS && okT));
      });
      // Hide edges where either endpoint is hidden
      cy.edges().forEach(function(e) {
        var srcHidden = e.source().hasClass('hidden');
        var tgtHidden = e.target().hasClass('hidden');
        e.toggleClass('hidden', srcHidden || tgtHidden);
      });
      // Optionally hide isolated nodes (zero visible edges)
      if (hideIsolated) {
        cy.nodes(':visible').forEach(function(n) {
          var visEdges = n.connectedEdges(':visible');
          if (visEdges.length === 0) n.addClass('hidden');
        });
      }
    });
  }
  window._dashboardSyncGraph = syncFromState;

  // Wire local controls
  var COSE_OPTS = { name: 'cose', idealEdgeLength: 90, nodeOverlap: 8,
                    gravity: 0.25, numIter: 1200, fit: true, padding: 30,
                    animate: false };
  var relay = document.getElementById('graph-relayout');
  if (relay) relay.addEventListener('click', function() {
    // Layout only on currently-visible elements so a focused subgraph
    // doesn't inherit positions imposed by the 100+ isolated nodes
    var vis = cy.elements(':visible');
    var src = vis.length > 0 ? vis : cy.elements();
    src.layout(COSE_OPTS).run();
  });
  var fitBtn = document.getElementById('graph-fit');
  if (fitBtn) fitBtn.addEventListener('click', function() { cy.fit(null, 30); });
  var collapse = document.getElementById('graph-collapse');
  if (collapse) collapse.addEventListener('click', function() {
    var sec = document.getElementById('graph-section');
    if (!sec) return;
    var collapsed = sec.classList.toggle('collapsed');
    collapse.textContent = collapsed ? 'show' : 'hide';
    if (!collapsed) {
      // Re-fit after re-show; container had zero height while collapsed
      setTimeout(function() { cy.resize(); cy.fit(null, 30); }, 0);
    }
  });
  // Mode switch (P2-a): swap cy.elements() between explicit and cooccur
  // datasets without rebuilding the cytoscape instance. Re-layout on
  // visible subset after swap so positions reflect the new edge topology.
  var sec = document.getElementById('graph-section');
  var graphCount = document.getElementById('graph-count');
  var legendExp = document.getElementById('graph-legend-explicit');
  var legendCo = document.getElementById('graph-legend-cooccur');
  function setGraphMode(mode) {
    var ds = datasets[mode];
    if (!ds || !ds.nodes) return;
    cy.elements().remove();
    cy.add(ds.nodes.concat(ds.edges));
    if (sec) sec.dataset.graphMode = mode;
    if (graphCount) {
      graphCount.textContent = '(' + ds.nodes.length + ' nodes · ' +
        ds.edges.length + ' edges)';
    }
    if (legendExp) legendExp.hidden = (mode !== 'explicit');
    if (legendCo) legendCo.hidden = (mode !== 'cooccur');
    var modeBtns = document.querySelectorAll('button.graph-mode-btn');
    for (var i = 0; i < modeBtns.length; i++) {
      modeBtns[i].classList.toggle('active', modeBtns[i].dataset.graphModeBtn === mode);
    }
    syncFromState({});
    setTimeout(function() {
      var vis = cy.elements(':visible');
      if (vis.length > 0 && vis.length < cy.elements().length) {
        vis.layout(COSE_OPTS).run();
      } else {
        cy.layout(COSE_OPTS).run();
      }
    }, 0);
  }
  var modeBtns = document.querySelectorAll('button.graph-mode-btn');
  for (var mi = 0; mi < modeBtns.length; mi++) {
    (function(btn) {
      btn.addEventListener('click', function() {
        setGraphMode(btn.dataset.graphModeBtn);
      });
    })(modeBtns[mi]);
  }

  var hideIsoEl = document.getElementById('graph-hide-isolated');
  if (hideIsoEl) hideIsoEl.addEventListener('change', function() {
    // Re-run sync with whatever the IIFE most recently passed; we don't
    // have it cached, so trigger a fresh apply by dispatching input on
    // the search box (no-op text change reuses current state)
    var s = document.getElementById('search');
    if (s) {
      var ev = new Event('input', { bubbles: true });
      s.dispatchEvent(ev);
    }
  });

  // Initial sync (in case a hash filter was applied before load).
  // Then re-layout on the visible subset so the connected component
  // isn't squished by repulsion from the (often many) isolated nodes
  // hidden via the default-on "hide isolated" toggle.
  syncFromState({});
  setTimeout(function() {
    var vis = cy.elements(':visible');
    if (vis.length > 0 && vis.length < cy.elements().length) {
      vis.layout(COSE_OPTS).run();
    }
  }, 0);
})();
"""


def _render_html(categories: list[dict], knowledge_root: Path, cfg: dict) -> str:
    """Render the full dashboard page.

    `cfg` is the parsed `config/dashboard_config.json` (consumed for the
    stale-threshold + recent-window-day knobs surfaced in the At-a-glance
    bar and the per-row stale-graying).
    """
    now = datetime.now()
    now_str = now.strftime("%Y-%m-%d %H:%M")
    total_entries = sum(len(c["entries"]) for c in categories)
    stale_days = int(cfg["stale_threshold_days"])
    recent_days = int(cfg["recent_window_days"])
    # Sort entries within each category by `updated` desc; stable for missing
    # dates (treat as oldest). Datasets category is intentionally exempt
    # (its own _render_category_datasets does kind-grouped vintage sort).
    for cat in categories:
        if cat["name"] == "datasets":
            continue
        cat["entries"].sort(
            key=lambda e: (e["updated"] or "0000-00-00"),
            reverse=True,
        )
    glance_bar = _render_at_a_glance(categories, now, recent_days, stale_days)
    sections = "\n".join(
        _render_category(c, knowledge_root, now, stale_days) for c in categories
    )
    graveyard = _render_graveyard_section(knowledge_root)
    controls = _render_controls(categories)
    cooccur_threshold = int(cfg["tag_cooccur_threshold"])
    graph_section = _render_graph_section(
        _collect_graph_data(categories),
        _collect_tag_cooccur_data(categories, cooccur_threshold),
    )
    briefing_cfg = _load_briefing_config(knowledge_root.parent)
    briefing_data = _collect_briefing_data(categories, briefing_cfg, now)
    briefing_section = _render_briefing_section(briefing_data)
    mode_bar = _render_mode_bar()
    owner_tabs = _render_owner_tabs(categories)
    entry_bodies = _render_entry_bodies(categories, knowledge_root)
    # Emoji owl rendered as an SVG favicon via data URL — works cross-browser
    # without needing a separate file to ship.
    favicon = (
        "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' "
        "viewBox='0 0 100 100'%3E%3Ctext y='.9em' font-size='90'%3E"
        "%F0%9F%A6%89%3C/text%3E%3C/svg%3E"
    )
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<title>🦉 Knowledge Base — {html.escape(knowledge_root.name)}</title>
<link rel="icon" type="image/svg+xml" href="{favicon}">
<style>
body{{font-family:-apple-system,Segoe UI,sans-serif;background:#1a1a1a;color:#e0e0e0;margin:0;padding:20px}}
header{{border-bottom:1px solid #333;padding-bottom:12px;margin-bottom:20px}}
header h1{{margin:0 0 6px 0;font-size:22px}}
header .meta{{color:#888;font-size:13px}}
/* Stale indicator — single actionable signal at top of page.
   N=0:  gray static, no hover/click (positive zero state, no review backlog)
   N>0:  orange button, click toggles state.stale (filter to stale rows only)
   filter-on: pronounced inset/outline so the toggle state is unambiguous */
#stale-indicator{{display:inline-flex;align-items:center;gap:6px;margin:6px auto 4px auto;padding:5px 14px;border-radius:14px;font-size:12px;font-family:Consolas,monospace;font-weight:500;cursor:pointer;background:#3a2a1a;color:#d8a88f;border:1px solid #5a3a2a;transition:background 0.12s ease,border-color 0.12s ease,color 0.12s ease}}
#stale-indicator:hover{{background:#4a3520;color:#f0c8a0;border-color:#7a5a3a}}
#stale-indicator.stale-filter-on{{background:#d8a88f;color:#1a1a1a;border-color:#d8a88f}}
#stale-indicator.stale-zero{{background:#1a1a1a;color:#555;border-color:#2a2a2a;cursor:default}}
#stale-indicator.stale-zero:hover{{background:#1a1a1a;color:#555;border-color:#2a2a2a}}
.stale-icon{{display:inline-flex;align-items:center;justify-content:center;width:16px;height:16px;border-radius:50%;background:rgba(0,0,0,0.25);font-weight:700;font-size:11px;line-height:1}}
.stale-zero .stale-icon{{background:#262626;color:#444}}
/* Wrap stale indicator in a centered row so it sits on its own line */
.stale-row{{display:flex;justify-content:center;margin:4px 0 0 0}}
/* Filter controls — sticky on scroll so chips stay reachable in long pages */
.controls{{position:sticky;top:0;z-index:30;background:#222;border:1px solid #333;border-radius:6px;padding:12px;margin:12px 0 20px 0;box-shadow:0 4px 12px rgba(0,0,0,0.35)}}
.controls input#search{{width:100%;padding:8px 10px;background:#1a1a1a;border:1px solid #444;border-radius:4px;color:#e0e0e0;font-size:13px;box-sizing:border-box;margin-bottom:10px}}
.controls input#search:focus{{outline:none;border-color:#9cdcfe}}
.filter-row{{display:flex;align-items:center;gap:6px;margin:6px 0;flex-wrap:wrap}}
.filter-label{{color:#888;font-size:12px;min-width:50px}}
.chip{{background:#2a2a2a;color:#aaa;border:1px solid #3a3a3a;padding:3px 10px;border-radius:12px;font-size:11px;cursor:pointer;font-family:inherit}}
.chip:hover{{background:#333;color:#ddd}}
.chip.active{{background:#3a4a5a;color:#9cdcfe;border-color:#9cdcfe}}
.chip-clear{{background:#4a2d2d;color:#bc8f8f;border-color:#6a3a3a}}
.result-row{{display:flex;align-items:center;gap:10px;margin-top:8px}}
.result-count{{color:#888;font-size:11px;font-family:Consolas,monospace}}
.result-count-active{{color:#9cdcfe;font-weight:500;background:rgba(60,80,100,0.4);padding:2px 8px;border-radius:8px}}
#active-tag{{display:inline-block;background:#3a4a5a;color:#9cdcfe;padding:2px 8px;border-radius:10px;font-size:11px}}
section.cat{{margin:24px 0;background:#222;border:1px solid #333;border-radius:6px;padding:16px}}
section.cat.hidden{{display:none}}
section.cat details{{margin:0}}
section.cat summary{{cursor:pointer;list-style:none;padding:0;margin:0}}
section.cat summary::-webkit-details-marker{{display:none}}
section.cat summary::before{{content:"▾ ";color:#9cdcfe;font-size:12px;display:inline-block;width:14px}}
section.cat details:not([open]) summary::before{{content:"▸ ";color:#888}}
section.cat summary h2{{display:inline;margin:0;font-size:18px;color:#9cdcfe;border:none;padding:0}}
section.cat .cat-count{{color:#666;font-size:13px;font-weight:normal;margin-left:6px}}
section.cat h2{{margin:0 0 8px 0;font-size:18px;color:#9cdcfe}}
/* Stale entry cards — visually de-emphasized so recent activity dominates */
.entry-card[data-stale="1"]{{opacity:0.55}}
.entry-card[data-stale="1"]:hover{{opacity:0.95}}
/* Owner tabs (top-level navigation, replaces owner chip row) */
.owner-tabs{{display:flex;flex-wrap:wrap;gap:4px;margin:10px auto;padding:4px;background:#1a1a1a;border:1px solid #2a2a2a;border-radius:8px;width:fit-content;max-width:100%}}
.owner-tab{{background:transparent;color:#888;border:none;padding:6px 16px;border-radius:6px;font-size:13px;cursor:pointer;font-family:inherit;font-weight:500;transition:background 0.12s ease,color 0.12s ease,box-shadow 0.12s ease}}
.owner-tab:hover{{color:#ddd;background:rgba(255,255,255,0.04)}}
.owner-tab.active{{color:#1a1a1a;font-weight:600;background:#9cdcfe}}
.owner-tab.active.owner-rules{{background:#bc8fd8;color:#1a1a1a}}
.owner-tab.active.owner-trade{{background:#8fbcd8;color:#1a1a1a}}
.owner-tab.active.owner-data{{background:#d8bc8f;color:#1a1a1a}}
.owner-tab.active.owner-research{{background:#8fd8bc;color:#1a1a1a}}
.owner-tab.active.owner-core{{background:#d8a88f;color:#1a1a1a}}
/* Entry-card list (replaces table view per P1-a 2026-05-06) */
.entry-list{{display:flex;flex-direction:column;gap:4px;margin-top:6px}}
.entry-card{{padding:8px 12px;border-left:3px solid transparent;border-radius:0 4px 4px 0;background:rgba(255,255,255,0.015);transition:background 0.1s ease,border-color 0.1s ease}}
.entry-card:hover{{background:rgba(156,220,254,0.05);border-left-color:#9cdcfe}}
.entry-card.hidden{{display:none}}
.entry-row1{{display:flex;align-items:center;gap:10px;flex-wrap:wrap}}
.entry-row2{{display:flex;align-items:center;gap:6px;margin-top:3px;flex-wrap:wrap}}
.entry-title{{background:none;border:none;padding:0;margin:0;color:#9cdcfe;cursor:pointer;font:inherit;font-size:14px;font-weight:500;text-align:left;flex:1;min-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.entry-title:hover{{text-decoration:underline}}
.entry-date{{color:#777;font-size:11px;font-family:Consolas,monospace;white-space:nowrap}}
.entry-path{{color:#555;font-size:10px;font-family:Consolas,monospace;background:transparent;padding:0;margin-left:auto}}
.tag-more{{background:#262626;color:#666;cursor:default;font-style:italic}}
/* Lineage badges (replaces in-line chain-row per P1-d 2026-05-06) */
.lineage{{display:inline-flex;align-items:center;gap:2px;padding:1px 6px;border-radius:8px;font-size:10px;font-family:Consolas,monospace;cursor:help;background:#1f1f1f;border:1px solid #2a2a2a}}
.lineage-icon{{font-size:11px;line-height:1}}
.lineage-sup{{color:#bc8fd8;border-color:rgba(188,143,216,0.3)}}
.lineage-by{{color:#d8a88f;border-color:rgba(216,168,143,0.3)}}
.lineage-ref{{color:#8fb8a8;border-color:rgba(143,184,168,0.3)}}
/* Owner pill in card — clickable to filter, separate from owner-tab */
.entry-card .owner-badge{{cursor:pointer}}
.entry-card .owner-badge:hover{{filter:brightness(1.25)}}
section.cat .owner{{color:#888;font-weight:normal;font-size:14px}}
section.cat .cat-content{{color:#aaa;font-size:13px;margin:0 0 12px 0}}
table.entries{{width:100%;border-collapse:collapse;font-size:13px}}
table.entries th{{text-align:left;padding:6px 8px;border-bottom:1px solid #333;color:#888;font-weight:500}}
table.entries td{{padding:6px 8px;border-bottom:1px solid #2a2a2a;vertical-align:top}}
table.entries tr.hidden{{display:none}}
table.entries td.title a{{color:#9cdcfe;text-decoration:none}}
table.entries td.title a:hover{{text-decoration:underline}}
table.entries td.title button.entry-link{{background:none;border:none;padding:0;margin:0;color:#9cdcfe;cursor:pointer;font:inherit;text-align:left;display:inline}}
table.entries td.title button.entry-link:hover{{text-decoration:underline}}
.tag{{display:inline-block;background:#333;color:#ccc;padding:1px 6px;border-radius:3px;font-size:11px;margin-right:3px;cursor:pointer}}
.tag:hover{{background:#444;color:#fff}}
.status{{display:inline-block;padding:1px 8px;border-radius:3px;font-size:11px;text-transform:uppercase}}
.status-active{{background:#2d4a2d;color:#8fbc8f}}
.status-in_use{{background:#2d4a2d;color:#8fbc8f}}
.status-archived{{background:#4a3a2d;color:#bc9f8f}}
.status-draft{{background:#2d3a4a;color:#8f9fbc}}
.status-deprecated{{background:#3a3a3a;color:#888}}
h3.dataset-kind{{margin:14px 0 6px 0;font-size:14px;color:#bbb;text-transform:uppercase;letter-spacing:0.5px}}
.kind-count{{color:#666;font-size:12px;font-weight:normal}}
.owner-badge{{display:inline-block;padding:1px 6px;border-radius:3px;font-size:11px;font-weight:500}}
.owner-rules{{background:#3a2d4a;color:#bc8fd8}}
.owner-trade{{background:#2d4a4a;color:#8fbcd8}}
.owner-data{{background:#4a4a2d;color:#d8bc8f}}
.owner-research{{background:#2d4a3a;color:#8fd8bc}}
.owner-core{{background:#4a3a2d;color:#d8a88f}}
.chain-row{{margin-top:4px;font-size:11px;line-height:1.5}}
.chain{{display:inline-block;color:#a88fbc;margin-right:8px}}
.refby{{display:inline-block;color:#8fb8a8;margin-right:8px}}
.chain code, .refby code{{color:inherit;background:rgba(255,255,255,0.05);padding:0 3px;border-radius:2px}}
.date,.path code{{color:#888;font-size:12px}}
p.empty{{color:#666;font-style:italic;margin:8px 0}}
/* ---- Modal + prose styles for rendered entry view ---- */
.owl{{display:inline-block;margin-right:6px;font-size:26px;vertical-align:-3px}}
#entry-modal{{position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.75);z-index:100;display:flex;align-items:flex-start;justify-content:center;padding:40px 20px;overflow-y:auto}}
#entry-modal[hidden]{{display:none}}
#modal-panel{{background:#1a1a1a;border:1px solid #3a3a3a;border-radius:8px;max-width:900px;width:100%;box-shadow:0 10px 40px rgba(0,0,0,0.5);display:flex;flex-direction:column;max-height:calc(100vh - 80px)}}
#modal-head{{display:flex;align-items:center;padding:12px 20px;border-bottom:1px solid #333;gap:12px}}
#modal-title{{margin:0;font-size:17px;color:#9cdcfe;flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
#modal-path{{font-size:11px;color:#888;font-family:monospace;background:#222;padding:2px 8px;border-radius:3px}}
#modal-close{{background:transparent;color:#888;border:1px solid #444;border-radius:4px;width:28px;height:28px;cursor:pointer;font-size:16px;font-family:inherit;padding:0}}
#modal-close:hover{{color:#fff;border-color:#888}}
#modal-body{{padding:20px 28px;overflow-y:auto;line-height:1.6;font-size:14px}}
#modal-body h1,#modal-body h2,#modal-body h3,#modal-body h4{{color:#9cdcfe;margin:1.2em 0 0.4em 0;border-bottom:1px solid #2a2a2a;padding-bottom:4px}}
#modal-body h1{{font-size:20px}}
#modal-body h2{{font-size:18px}}
#modal-body h3{{font-size:16px;border-bottom:none}}
#modal-body h4{{font-size:14px;border-bottom:none;color:#bbbbff}}
#modal-body p{{margin:0.6em 0;color:#ddd}}
#modal-body ul,#modal-body ol{{margin:0.6em 0;padding-left:1.8em;color:#ddd}}
#modal-body li{{margin:0.2em 0}}
#modal-body code{{background:#2a2a2a;color:#e9c46a;padding:1px 5px;border-radius:3px;font-size:12px}}
#modal-body pre{{background:#0f0f0f;border:1px solid #2a2a2a;border-radius:4px;padding:12px;overflow-x:auto;margin:0.8em 0}}
#modal-body pre code{{background:transparent;color:#e0e0e0;padding:0;font-size:12px}}
#modal-body blockquote{{border-left:3px solid #5a5a5a;padding:0.1em 14px;margin:0.8em 0;color:#bbb;background:rgba(255,255,255,0.02)}}
#modal-body a{{color:#9cdcfe}}
.skill-tier-index a{{color:#9cdcfe;text-decoration:none}}
.skill-tier-index a:hover{{color:#bce0ff;text-decoration:underline}}
.skill-tier-index code{{background:#1a1a1a;padding:1px 5px;border-radius:3px;color:#dcdcaa;font-family:'Cascadia Mono','SF Mono',Consolas,monospace}}
.skill-tier-index h2{{color:#9cdcfe;margin-top:24px;border-bottom:1px solid #333;padding-bottom:6px}}
.skill-tier-index h3{{color:#bc8fd8;margin-top:16px}}
.skill-tier-index blockquote{{border-left:3px solid #555;margin:8px 0;padding:6px 12px;background:#1a1a1a;color:#bbb;font-size:13px}}
#modal-body hr{{border:none;border-top:1px solid #333;margin:1.2em 0}}
#modal-body table{{border-collapse:collapse;margin:0.8em 0;font-size:13px;width:100%}}
#modal-body table th,#modal-body table td{{border:1px solid #333;padding:6px 10px;text-align:left}}
#modal-body table th{{background:#252525;color:#9cdcfe;font-weight:500}}
#modal-body table tr:nth-child(even){{background:rgba(255,255,255,0.02)}}
#modal-body strong{{color:#fff}}
#modal-body em{{color:#eee}}
/* Mermaid: keep diagrams within modal width; before render the source <pre>
   bleed through is suppressed so users don't see raw text flicker. */
#modal-body .mermaid{{margin:0.8em 0;text-align:center;cursor:zoom-in;border:1px dashed transparent;border-radius:4px;transition:border-color 0.15s ease}}
#modal-body .mermaid:hover{{border-color:#444}}
#modal-body .mermaid svg{{max-width:100%;height:auto;pointer-events:none}}
#modal-body .mermaid:not([data-processed="true"]){{color:#888;font-family:monospace;font-size:11px;white-space:pre-wrap;background:#0f0f0f;padding:8px;border-radius:4px;cursor:default}}
/* Mermaid zoom modal: fullscreen overlay with wheel-zoom + drag-pan */
#mermaid-zoom-modal{{position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.94);z-index:200;overflow:hidden}}
#mermaid-zoom-modal[hidden]{{display:none}}
#mermaid-zoom-content{{position:absolute;top:0;left:0;right:0;bottom:0;overflow:hidden;cursor:grab;user-select:none;-webkit-user-select:none}}
#mermaid-zoom-content.dragging{{cursor:grabbing}}
/* Inside zoom modal: strip any inherited max-width caps; width/height
   are set explicitly by JS on each scale change so the browser re-
   rasterizes the vector at the new size (sharp text). transform here
   is translate-only -- scale is applied via attribute, not CSS. */
#mermaid-zoom-content svg{{position:absolute;top:0;left:0;max-width:none !important;max-height:none !important;transform-origin:0 0;background:transparent;will-change:transform;shape-rendering:geometricPrecision;text-rendering:optimizeLegibility}}
#mermaid-zoom-close{{position:fixed;top:16px;right:20px;background:#1a1a1a;color:#ddd;border:1px solid #555;border-radius:6px;width:40px;height:40px;font-size:22px;line-height:1;cursor:pointer;font-family:inherit;z-index:201;padding:0}}
#mermaid-zoom-close:hover{{background:#2a2a2a;color:#fff;border-color:#888}}
#mermaid-zoom-controls{{position:fixed;top:16px;left:20px;display:flex;gap:6px;background:rgba(20,20,20,0.92);padding:6px;border-radius:8px;border:1px solid #333;z-index:201}}
#mermaid-zoom-controls button{{background:#1a1a1a;color:#ccc;border:1px solid #444;border-radius:4px;width:32px;height:32px;font-size:14px;line-height:1;cursor:pointer;font-family:inherit;padding:0}}
#mermaid-zoom-controls button:hover{{background:#2a2a2a;color:#fff;border-color:#777}}
#mermaid-zoom-scale{{display:inline-flex;align-items:center;justify-content:center;color:#888;font-size:11px;font-family:Consolas,monospace;min-width:46px;padding:0 6px}}
#mermaid-zoom-hint{{position:fixed;bottom:14px;left:50%;transform:translateX(-50%);color:#888;font-size:11px;background:rgba(20,20,20,0.85);padding:6px 12px;border-radius:14px;border:1px solid #333;pointer-events:none;z-index:201;font-family:Consolas,monospace}}
/* Mode bar (Index / Briefing toggle) */
.mode-bar{{display:flex;gap:6px;justify-content:center;margin:14px 0 8px 0;padding:6px;background:#1f1f1f;border:1px solid #2a2a2a;border-radius:24px;width:fit-content;margin-left:auto;margin-right:auto}}
.mode-btn{{background:transparent;color:#888;border:none;padding:6px 18px;border-radius:18px;font-size:13px;cursor:pointer;font-family:inherit;font-weight:500;transition:background 0.12s ease,color 0.12s ease}}
.mode-btn:hover{{color:#ddd}}
.mode-btn.active{{background:#3a4a5a;color:#9cdcfe}}
/* Mode visibility — Index hides briefing, Briefing hides everything else
   except mode-bar / header / modal / entry-bodies (latter two are display
   targets controlled by their own attributes). */
body[data-mode="index"] #briefing-section{{display:none}}
body[data-mode="briefing"] .controls,
body[data-mode="briefing"] #graph-section,
body[data-mode="briefing"] section.cat,
body[data-mode="briefing"] #graveyard{{display:none}}
/* Briefing panels */
#briefing-section{{margin:20px 0;background:#222;border:1px solid #333;border-radius:6px;padding:16px}}
.briefing-head{{margin-bottom:14px;padding-bottom:10px;border-bottom:1px solid #333}}
.briefing-head h2{{margin:0;font-size:18px;color:#9cdcfe}}
.briefing-week{{color:#888;font-weight:normal;font-size:13px;margin-left:8px;font-family:Consolas,monospace}}
.briefing-doc{{color:#888;font-size:12px;margin:6px 0 0 0;line-height:1.5}}
/* Briefing panels — distinct card form with left accent border to make
   the three modules visually locatable rather than running together */
.briefing-panel{{margin:24px 0;background:#1a1a1a;border:1px solid #2a2a2a;border-left:4px solid #555;border-radius:6px;padding:14px 16px}}
#briefing-pinned{{border-left-color:#d8a88f}}
#briefing-iteration{{border-left-color:#9cdcfe}}
#briefing-serendipity{{border-left-color:#bc8fd8}}
.briefing-h3{{margin:0 0 12px 0;font-size:15px;color:#ddd;text-transform:uppercase;letter-spacing:0.8px;font-weight:600;display:flex;align-items:center;gap:8px}}
.briefing-h3::before{{content:"";display:inline-block;width:6px;height:6px;border-radius:50%;background:currentColor;opacity:0.5}}
#briefing-pinned .briefing-h3{{color:#d8a88f}}
#briefing-iteration .briefing-h3{{color:#9cdcfe}}
#briefing-serendipity .briefing-h3{{color:#bc8fd8}}
.briefing-h4{{margin:14px 0 8px 0;font-size:12px;color:#888;font-weight:500;text-transform:uppercase;letter-spacing:0.4px}}
.briefing-count{{color:#666;font-size:12px;font-weight:normal;text-transform:none;letter-spacing:0}}
.briefing-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:10px}}
.briefing-card{{background:#1a1a1a;border:1px solid #2a2a2a;border-radius:5px;padding:10px 12px;transition:border-color 0.15s ease}}
.briefing-card:hover{{border-color:#3a3a3a}}
.briefing-card-head{{display:flex;flex-wrap:wrap;align-items:center;gap:6px;margin-bottom:6px}}
.briefing-title{{background:none;border:none;padding:0;margin:0;color:#9cdcfe;cursor:pointer;font:inherit;font-size:14px;font-weight:500;text-align:left;flex:1;min-width:0}}
.briefing-title:hover{{text-decoration:underline}}
.briefing-meta{{color:#888;font-size:11px;font-family:Consolas,monospace}}
.briefing-summary{{color:#bbb;font-size:12px;line-height:1.5;margin:4px 0 6px 0}}
.briefing-path{{display:block;color:#666;font-size:10px;font-family:Consolas,monospace}}
.briefing-empty{{color:#666;font-style:italic;font-size:12px;margin:6px 0}}
.briefing-empty code{{background:rgba(255,255,255,0.04);padding:1px 4px;border-radius:2px;font-style:normal}}
/* Knowledge graph */
#graph-section{{margin:20px 0;background:#222;border:1px solid #333;border-radius:6px;padding:14px}}
#graph-section.collapsed #graph-canvas,#graph-section.collapsed .graph-legend{{display:none}}
.graph-head{{display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:10px;margin-bottom:6px}}
.graph-head h2{{margin:0;font-size:18px;color:#9cdcfe}}
.graph-count{{color:#888;font-weight:normal;font-size:13px;margin-left:8px}}
.graph-controls{{display:flex;align-items:center;gap:8px;flex-wrap:wrap}}
.graph-toggle{{color:#aaa;font-size:12px;display:inline-flex;align-items:center;gap:4px;cursor:pointer}}
.graph-toggle input{{margin:0;cursor:pointer}}
.gchip{{background:#2a2a2a;color:#aaa;border:1px solid #3a3a3a;padding:3px 10px;border-radius:12px;font-size:11px;cursor:pointer;font-family:inherit}}
.gchip:hover{{background:#333;color:#ddd}}
.graph-legend{{display:flex;flex-wrap:wrap;gap:10px;align-items:center;color:#888;font-size:11px;font-family:Consolas,monospace;padding:6px 0;border-bottom:1px solid #2a2a2a;margin-bottom:8px}}
.lg-edge.lg-supersedes{{color:#bc8fd8}}
.lg-edge.lg-related{{color:#888}}
.lg-edge.lg-blocks{{color:#d88f8f}}
.lg-edge.lg-cooccur{{color:#5a8fa8}}
.lg-meta{{color:#666;font-size:11px;font-style:italic}}
.lg-sep{{color:#444}}
/* Graph mode bar (P2-a): Explicit links / Tag co-occurrence switch */
.graph-mode-bar{{display:flex;gap:4px;margin:6px 0 8px 0;background:#1a1a1a;border:1px solid #2a2a2a;border-radius:6px;padding:3px;width:fit-content}}
.graph-mode-btn{{background:transparent;color:#888;border:none;padding:5px 12px;border-radius:4px;font-size:12px;cursor:pointer;font-family:inherit;font-weight:500;transition:background 0.12s ease,color 0.12s ease}}
.graph-mode-btn:hover{{color:#ddd;background:rgba(255,255,255,0.04)}}
.graph-mode-btn.active{{background:#3a4a5a;color:#9cdcfe}}
.lg-node{{display:inline-block;padding:1px 6px;border-radius:3px;font-size:11px}}
#graph-canvas{{position:relative;width:100%;height:600px;background:#1a1a1a;border:1px solid #2a2a2a;border-radius:4px}}
#graph-tip{{position:absolute;bottom:6px;left:8px;color:#ccc;background:rgba(15,15,15,0.85);border:1px solid #333;padding:3px 8px;border-radius:4px;font-size:11px;font-family:Consolas,monospace;pointer-events:none;opacity:0;transition:opacity 0.12s ease;z-index:5}}
.graph-error{{color:#bc8f8f;padding:20px;font-size:12px}}
</style>
<script>
// HEAD-LEVEL MODAL API — defined here in <head> so it's available the
// instant the parser reaches the first <button onclick> in <body>.
// Any body-tail <script> failure cannot prevent this from running because
// it has already executed. This is the third concentric defense after
// (a) function declarations are hoisted within their script tag,
// (b) declarations + window.* expose are placed before the IIFE.
// Keeping all three in place because past 4 fix attempts each looked
// sufficient and weren't.
// Self-contained: create the modal on-the-fly if dashboard's pre-rendered
// one isn't reachable. User reports of "modal not found in DOM" despite
// the element being in the HTML source point to some browser/file://
// quirk we can't diagnose remotely; sidestep it by building modal in JS.
function _dashboardEnsureModal() {{
  var modal = document.getElementById('entry-modal');
  if (modal) return modal;
  // Build from scratch
  modal = document.createElement('div');
  modal.id = 'entry-modal';
  modal.setAttribute('style',
    'position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.75);' +
    'z-index:9999;display:none;align-items:flex-start;justify-content:center;' +
    'padding:40px 20px;overflow-y:auto;'
  );
  var panel = document.createElement('div');
  panel.id = 'modal-panel';
  panel.setAttribute('style',
    'background:#1a1a1a;border:1px solid #3a3a3a;border-radius:8px;' +
    'max-width:900px;width:100%;box-shadow:0 10px 40px rgba(0,0,0,0.5);' +
    'display:flex;flex-direction:column;max-height:calc(100vh - 80px);' +
    'color:#e0e0e0;font-family:-apple-system,Segoe UI,sans-serif;'
  );
  var head = document.createElement('div');
  head.setAttribute('style', 'display:flex;align-items:center;padding:12px 20px;border-bottom:1px solid #333;gap:12px;');
  var title = document.createElement('h2');
  title.id = 'modal-title';
  title.setAttribute('style', 'margin:0;font-size:17px;color:#9cdcfe;flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;');
  var path = document.createElement('span');
  path.id = 'modal-path';
  path.setAttribute('style', 'font-size:11px;color:#888;font-family:monospace;background:#222;padding:2px 8px;border-radius:3px;');
  var close = document.createElement('button');
  close.id = 'modal-close';
  close.type = 'button';
  close.setAttribute('aria-label', 'close');
  close.textContent = '✕';
  close.setAttribute('style', 'background:transparent;color:#888;border:1px solid #444;border-radius:4px;width:28px;height:28px;cursor:pointer;font-size:16px;font-family:inherit;padding:0;');
  close.onclick = function() {{ window._dashboardCloseEntry(); }};
  head.appendChild(title);
  head.appendChild(path);
  head.appendChild(close);
  var body = document.createElement('div');
  body.id = 'modal-body';
  body.setAttribute('style', 'padding:20px 28px;overflow-y:auto;line-height:1.6;font-size:14px;');
  panel.appendChild(head);
  panel.appendChild(body);
  modal.appendChild(panel);
  // Backdrop click closes
  modal.addEventListener('click', function(e) {{
    if (e.target === modal) window._dashboardCloseEntry();
  }});
  document.body.appendChild(modal);
  return modal;
}}

window._dashboardOpenEntry = function(rel) {{
  console.log('[dashboard] _dashboardOpenEntry called with rel=', JSON.stringify(rel));
  var modal = _dashboardEnsureModal();
  var modalBody = document.getElementById('modal-body');
  var modalTitle = document.getElementById('modal-title');
  var modalPath = document.getElementById('modal-path');
  console.log('[dashboard] modal=', !!modal, 'modalBody=', !!modalBody);
  if (!modalBody) throw new Error('[dashboard] #modal-body not found after ensure');
  var src = null;
  var bodies = document.querySelectorAll('[data-entry-body]');
  console.log('[dashboard] entry bodies count=', bodies.length);
  for (var i = 0; i < bodies.length; i++) {{
    if (bodies[i].getAttribute('data-entry-body') === rel) {{ src = bodies[i]; break; }}
  }}
  console.log('[dashboard] src found=', !!src);
  if (!src) throw new Error('[dashboard] no [data-entry-body] match for rel=' + rel);
  modalBody.innerHTML = src.innerHTML;
  if (modalTitle) modalTitle.textContent = src.dataset.entryTitle || rel;
  if (modalPath) modalPath.textContent = src.dataset.entryPath || ('knowledge/' + rel);
  modal.style.display = 'flex';
  modal.removeAttribute('hidden');
  document.body.style.overflow = 'hidden';
  modalBody.scrollTop = 0;
  console.log('[dashboard] modal shown, display=', modal.style.display);
  // P2-c: persist entry rel to URL hash so a copy-pasted URL re-opens
  // the same modal. Other filter state preserved by the merging serializer.
  if (typeof window._dashboardHashSerialize === 'function') {{
    window._dashboardHashSerialize({{ entry: rel }});
  }}
  if (typeof mermaid !== 'undefined') {{
    var mNodes = modalBody.querySelectorAll('.mermaid');
    if (mNodes.length) {{
      try {{ mermaid.run({{ nodes: mNodes }}); }} catch (e) {{}}
    }}
  }}
}};
window._dashboardCloseEntry = function() {{
  var modal = document.getElementById('entry-modal');
  if (!modal) return;
  modal.style.display = 'none';
  modal.setAttribute('hidden', 'hidden');
  document.body.style.overflow = '';
  // Multi-key hash schema (P2-c): clear entry param, preserve rest
  if (typeof window._dashboardHashSerialize === 'function') {{
    window._dashboardHashSerialize({{ entry: '' }});
  }}
}};
</script>
</head><body data-mode="index">
<header>
<h1><span class="owl">🦉</span>Knowledge Base Dashboard</h1>
<div class="meta">Root: <code>{html.escape(str(knowledge_root))}</code>
  · {len(categories)} categories · {total_entries} entries
  · Generated {now_str}</div>
</header>
{glance_bar}
{mode_bar}
{owner_tabs}
{controls}
{briefing_section}
{sections}
{graveyard}
{graph_section}
{entry_bodies}
<div id="entry-modal" hidden>
  <div id="modal-panel">
    <div id="modal-head">
      <h2 id="modal-title"></h2>
      <span id="modal-path"></span>
      <button id="modal-close" type="button" aria-label="close">✕</button>
    </div>
    <div id="modal-body"></div>
  </div>
</div>
<script src="./assets/vendor/mermaid/mermaid.min.js"></script>
<script>if(window.mermaid){{mermaid.initialize({{startOnLoad:false,theme:'dark',securityLevel:'loose',themeVariables:{{background:'#1a1a1a',clusterBkg:'#262626',clusterBorder:'#444',edgeLabelBackground:'#1a1a1a',tertiaryColor:'#262626',tertiaryBorderColor:'#444',tertiaryTextColor:'#ddd'}}}});}}</script>
<script src="./assets/vendor/cytoscape/cytoscape.min.js"></script>
<script>{_DASHBOARD_JS}</script>
<script>{_GRAPH_JS}</script>
</body></html>
"""


def _load_dashboard_config(root: Path) -> dict:
    """Load `config/dashboard_config.json`. No defaults (Art.4)."""
    cfg_path = root / "config" / "dashboard_config.json"
    if not cfg_path.is_file():
        raise FileNotFoundError(
            f"Dashboard config missing: {cfg_path}. "
            "This file is required (Art.4 no-default policy). "
            "See proposals/shared_state_knowledge_dashboard.md."
        )
    cfg = json.loads(cfg_path.read_text(encoding="utf-8-sig"))
    required = (
        "output_path", "lock_path", "lock_timeout_sec",
        "stale_threshold_days", "recent_window_days",
        "tag_cooccur_threshold",
    )
    for key in required:
        if key not in cfg:
            raise KeyError(
                f"dashboard_config.json missing required key: {key}"
            )
    return cfg


def build(root: Path) -> Path:
    """Scan knowledge/ under root and write dashboard via shared-state lock.

    Output path resolved from `config/dashboard_config.json` relative to
    `root` (e.g. `../shared_state/knowledge/dashboard.html` resolves to
    a single physical file outside any clone). Concurrency: `filelock`
    with config-driven timeout; atomic write via tmp + `os.replace`.
    """
    knowledge_root = root / "knowledge"
    if not knowledge_root.is_dir():
        raise FileNotFoundError(f"knowledge/ not found at {knowledge_root}")
    cfg = _load_dashboard_config(root)
    output = (root / cfg["output_path"]).resolve()
    lock_path = (root / cfg["lock_path"]).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    # Copy vendored web runtime assets next to dashboard.html so file://
    # loads work without CDN (which is unreliable inside the GFW). The
    # rendered HTML references each via `./assets/vendor/<pkg>/<file>`
    # relative to dashboard.html. Source lives under each clone's
    # `knowledge/assets/vendor/`; `.gitattributes` marks the tree binary
    # so sha256 (per VERSION.md) survives Windows autocrlf=true clones.
    vendored_assets = (
        ("mermaid", "mermaid.min.js"),       # P-0054 Phase 2 (mermaid 11.4.1)
        ("cytoscape", "cytoscape.min.js"),   # 2026-05-13 (cytoscape 3.30.1)
    )
    for pkg, fname in vendored_assets:
        src = knowledge_root / "assets" / "vendor" / pkg / fname
        if not src.is_file():
            raise FileNotFoundError(
                f"Vendored {pkg} missing: {src}. "
                f"See knowledge/assets/vendor/{pkg}/VERSION.md."
            )
        dst = output.parent / "assets" / "vendor" / pkg / fname
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)

    categories = _collect_all(knowledge_root)
    html_text = _render_html(categories, knowledge_root, cfg)
    tmp = output.with_suffix(output.suffix + ".tmp")

    with FileLock(str(lock_path), timeout=int(cfg["lock_timeout_sec"])):
        tmp.write_text(html_text, encoding="utf-8")
        os.replace(tmp, output)

    total = sum(len(c["entries"]) for c in categories)
    logger.info(
        "[OK] wrote %s (%d categories, %d entries)",
        output, len(categories), total,
    )
    return output


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Build knowledge dashboard")
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="Repo root (default: agent-core's parent of tools/)",
    )
    args = parser.parse_args()
    build(args.root.resolve())


if __name__ == "__main__":
    main()
