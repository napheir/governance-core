"""Audit knowledge HTML profile compliance (P-0054 Phase 6).

Validates every `knowledge/**/*.html` file against the spec in
`knowledge/governance/knowledge-html-profile.md`. Complements
`audit_knowledge.py` (which only scans .md) and `build_autogen_blocks.py`
(which writes content). This audit is the gate that catches profile
drift before it ships.

Checks (severity in brackets):
  1. Single top-level <article class="knowledge-record">             [fail]
  2. data-carrier-class attribute present + matches P-0053 enum      [fail]
  3. <meta name="kc:*"> metadata complete (carrier-class, title,
     owner, status, created, updated, tags)                          [fail]
  4. <title> matches <meta name="kc:title">                          [warn]
  5. No remote URLs in <link href> / <script src> / inline           [fail]
  6. Forbidden elements absent (<form>, <iframe>)                    [fail]
  7. Required sections per carrier_class present                     [fail]
  8. Mermaid figures have both .diagram-render + <details
     class="diagram-source"> with <code class="language-mermaid">    [fail]
  9. Autogen blocks: required data-* attributes complete             [fail]
 10. Autogen blocks: distance since data-generated-at within
     data-stale-after-days                                           [warn]
 11. Autogen blocks: data-source path resolves under repo            [warn]

Exits 0 on no failures, 1 otherwise. Warnings never fail the build.

Usage:
    python tools/audit_html_profile.py                      # walk all knowledge/**/*.html
    python tools/audit_html_profile.py path/to/file.html    # single file
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(message)s")

REPO_ROOT = Path(__file__).resolve().parent.parent
KNOWLEDGE_DIR = REPO_ROOT / "knowledge"

# Mirror audit_knowledge.py and build_autogen_blocks.py: skip the vendor
# + rendering asset tree.
SKIP_PATH_PREFIXES = ("assets/",)

# P-0053 carrier_class enum (kept in sync with
# contracts/knowledge_frontmatter_schema.md §3.4 + tools/audit_knowledge.py).
CARRIER_CLASSES = {
    "decision-record",
    "reference",
    "runbook",
    "experiment-record",
    "current-state",
    "derived-lesson",
}

# Required <section id="..."> ids per carrier_class, per
# knowledge/governance/knowledge-html-profile.md §2.4.
REQUIRED_SECTIONS: dict[str, list[str]] = {
    "reference": ["purpose", "current-model", "concepts", "diagrams", "update-triggers", "related"],
    "runbook": ["purpose", "preconditions", "steps", "verification", "rollback", "failure-modes", "related"],
    "current-state": ["purpose", "mechanism", "autogen-metrics", "update-triggers", "sources", "related"],
    "derived-lesson": ["summary", "condition", "reason", "action", "boundary", "source", "validation", "related"],
}

REQUIRED_META = ("carrier-class", "title", "owner", "status", "created", "updated", "tags")

# Patterns for remote URL detection. The principle (governance §2.3):
# everything must be relative; no scheme://host loads.
REMOTE_SRC_RE = re.compile(
    r'(?:<link\b[^>]*\bhref=|<script\b[^>]*\bsrc=|<img\b[^>]*\bsrc=)"\s*(?:https?:)?//',
    re.IGNORECASE,
)
INLINE_FETCH_RE = re.compile(r'\bfetch\s*\(\s*["\']https?://', re.IGNORECASE)

FORBIDDEN_TAG_RE = re.compile(r'<(form|iframe)\b', re.IGNORECASE)

ARTICLE_RE = re.compile(
    r'<article\b[^>]*\bclass="knowledge-record"[^>]*>',
    re.IGNORECASE,
)
DATA_CARRIER_RE = re.compile(r'\bdata-carrier-class="([^"]*)"')
META_RE = re.compile(
    r'<meta\b[^>]*\bname="kc:([^"]+)"[^>]*\bcontent="([^"]*)"',
    re.IGNORECASE,
)
TITLE_RE = re.compile(r"<title>([^<]*)</title>", re.IGNORECASE)
SECTION_ID_RE = re.compile(r'<section\b[^>]*\bid="([^"]+)"', re.IGNORECASE)

FIGURE_MERMAID_RE = re.compile(
    r'<figure\b[^>]*\bclass="[^"]*\bdiagram-mermaid\b[^"]*"[^>]*>(.*?)</figure>',
    re.IGNORECASE | re.DOTALL,
)
DIAGRAM_RENDER_RE = re.compile(r'class="[^"]*\bdiagram-render\b[^"]*"', re.IGNORECASE)
DIAGRAM_SOURCE_RE = re.compile(
    r'<details\b[^>]*\bclass="[^"]*\bdiagram-source\b[^"]*"[^>]*>(.*?)</details>',
    re.IGNORECASE | re.DOTALL,
)
LANG_MERMAID_RE = re.compile(r'<code\b[^>]*\bclass="[^"]*\blanguage-mermaid\b[^"]*"', re.IGNORECASE)

AUTOGEN_OPEN_RE = re.compile(
    r'<section\b[^>]*\bclass="autogen-block"[^>]*>',
    re.IGNORECASE,
)
ATTR_RE_TMPL = r'\b{name}="([^"]*)"'

REQUIRED_AUTOGEN_ATTRS = (
    "data-autogen-id",
    "data-source",
    "data-generated-at",
    "data-stale-after-days",
    "data-build-script",
)

ISO_DT_RE = re.compile(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}([+-]\d{2}:?\d{2}|Z)?$')


# ------------------------------------------------------------------------

class Result:
    """Per-file outcome buckets."""
    __slots__ = ("path", "fails", "warns")

    def __init__(self, path: Path):
        self.path = path
        self.fails: list[str] = []
        self.warns: list[str] = []

    def fail(self, msg: str) -> None:
        self.fails.append(msg)

    def warn(self, msg: str) -> None:
        self.warns.append(msg)


def _attr(tag: str, name: str) -> str | None:
    m = re.search(ATTR_RE_TMPL.format(name=re.escape(name)), tag)
    return m.group(1) if m else None


def _audit_one(path: Path) -> Result:
    res = Result(path)
    text = path.read_text(encoding="utf-8")

    # --- Check 1: single top-level <article class="knowledge-record"> ---
    articles = ARTICLE_RE.findall(text)
    if len(articles) == 0:
        res.fail('no <article class="knowledge-record"> element found')
        return res
    if len(articles) > 1:
        res.fail(f'expected exactly one <article class="knowledge-record">, got {len(articles)}')

    article_open = articles[0]

    # --- Check 2: data-carrier-class enum ---
    cc_m = DATA_CARRIER_RE.search(article_open)
    carrier_class = cc_m.group(1) if cc_m else None
    if not carrier_class:
        res.fail("article missing data-carrier-class attribute")
    elif carrier_class not in CARRIER_CLASSES:
        res.fail(f"data-carrier-class {carrier_class!r} not in P-0053 enum {sorted(CARRIER_CLASSES)}")
        carrier_class = None  # don't try section check below

    # --- Check 3: <meta name="kc:*"> coverage ---
    meta_kv = {name: content for name, content in META_RE.findall(text)}
    missing_meta = [k for k in REQUIRED_META if k not in meta_kv]
    if missing_meta:
        res.fail(f"missing <meta name=\"kc:{','.join(missing_meta)}\">")

    # --- Check 4: <title> vs kc:title ---
    title_m = TITLE_RE.search(text)
    if title_m and "title" in meta_kv:
        if title_m.group(1).strip() != meta_kv["title"].strip():
            res.warn(f"<title> {title_m.group(1)!r} differs from kc:title {meta_kv['title']!r}")

    # --- Check 5: no remote URLs ---
    for m in REMOTE_SRC_RE.finditer(text):
        snippet = text[max(0, m.start() - 20):m.end() + 60]
        res.fail(f"remote URL detected near: ...{snippet.strip()}...")
    for m in INLINE_FETCH_RE.finditer(text):
        res.fail("inline JS fetch() to remote URL detected")

    # --- Check 6: forbidden tags ---
    for m in FORBIDDEN_TAG_RE.finditer(text):
        res.fail(f"forbidden element <{m.group(1)}> present")

    # --- Check 7: required sections per carrier_class ---
    if carrier_class and carrier_class in REQUIRED_SECTIONS:
        present_ids = set(SECTION_ID_RE.findall(text))
        for required_id in REQUIRED_SECTIONS[carrier_class]:
            if required_id not in present_ids:
                res.fail(f"required <section id=\"{required_id}\"> missing for carrier_class={carrier_class!r}")

    # --- Check 8: Mermaid figures have both render + source ---
    for body in FIGURE_MERMAID_RE.findall(text):
        if not DIAGRAM_RENDER_RE.search(body):
            res.fail("mermaid figure missing .diagram-render element")
        details_m = DIAGRAM_SOURCE_RE.search(body)
        if not details_m:
            res.fail("mermaid figure missing <details class=\"diagram-source\">")
        elif not LANG_MERMAID_RE.search(details_m.group(1)):
            res.fail("mermaid figure <details> missing <code class=\"language-mermaid\">")

    # --- Checks 9, 10, 11: autogen blocks ---
    now = datetime.now(timezone.utc)
    for tag in AUTOGEN_OPEN_RE.findall(text):
        autogen_id = _attr(tag, "data-autogen-id") or "<unknown>"
        # Check 9: required attrs
        missing_attrs = [a for a in REQUIRED_AUTOGEN_ATTRS if not _attr(tag, a)]
        if missing_attrs:
            res.fail(f"autogen-block id={autogen_id!r} missing attrs {missing_attrs}")
            continue
        # Check 11: source path resolves under repo
        src_rel = _attr(tag, "data-source") or ""
        if src_rel and not (REPO_ROOT / src_rel).exists():
            res.warn(f"autogen-block id={autogen_id!r}: data-source {src_rel!r} does not exist")
        # Check 10: staleness
        gen_at = _attr(tag, "data-generated-at") or ""
        stale_after = _attr(tag, "data-stale-after-days") or "0"
        if not ISO_DT_RE.match(gen_at.replace(":", "", 1) if gen_at.endswith(("+0800", "-0800")) else gen_at):
            # Tolerant: just warn on non-ISO, don't try to compute age.
            res.warn(f"autogen-block id={autogen_id!r}: data-generated-at {gen_at!r} not ISO-8601")
        else:
            try:
                # Python's fromisoformat handles +HH:MM. Normalize compact +HHMM by inserting colon.
                normalized = gen_at
                m = re.match(r"^(.*)([+-])(\d{2})(\d{2})$", gen_at)
                if m:
                    normalized = f"{m.group(1)}{m.group(2)}{m.group(3)}:{m.group(4)}"
                gen_dt = datetime.fromisoformat(normalized)
                if gen_dt.tzinfo is None:
                    gen_dt = gen_dt.replace(tzinfo=timezone.utc)
                age_days = (now - gen_dt).total_seconds() / 86400
                limit = int(stale_after) if stale_after.isdigit() else 0
                if limit and age_days > limit:
                    res.warn(
                        f"autogen-block id={autogen_id!r}: {age_days:.1f}d since generated, "
                        f"exceeds data-stale-after-days={limit}"
                    )
            except ValueError as exc:
                res.warn(f"autogen-block id={autogen_id!r}: stale-check parse failed: {exc}")

    return res


# ------------------------------------------------------------------------

def _discover(args_files: list[str]) -> list[Path]:
    if args_files:
        return [Path(p).resolve() for p in args_files]
    return sorted(
        p for p in KNOWLEDGE_DIR.rglob("*.html")
        if not any(
            p.relative_to(KNOWLEDGE_DIR).as_posix().startswith(pre)
            for pre in SKIP_PATH_PREFIXES
        )
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit Knowledge HTML Profile compliance")
    parser.add_argument("files", nargs="*", help="Specific files (default: knowledge/**/*.html minus assets/)")
    args = parser.parse_args()

    files = _discover(args.files)
    if not files:
        logger.info("[INFO] no HTML files found under %s", KNOWLEDGE_DIR)
        return 0

    total_fails = 0
    total_warns = 0
    for fp in files:
        try:
            res = _audit_one(fp)
        except Exception as exc:
            logger.error("[FAIL] %s: audit raised: %s", fp.relative_to(REPO_ROOT), exc)
            total_fails += 1
            continue
        rel = fp.relative_to(REPO_ROOT).as_posix()
        if res.fails:
            logger.warning("=== %s ===", rel)
            for msg in res.fails:
                logger.warning("  FAIL: %s", msg)
                total_fails += 1
        if res.warns:
            if not res.fails:
                logger.info("=== %s ===", rel)
            for msg in res.warns:
                logger.warning("  WARN: %s", msg)
                total_warns += 1
        if not res.fails and not res.warns:
            logger.info("[OK] %s", rel)

    logger.info("=" * 50)
    logger.info("  Files:    %d", len(files))
    logger.info("  Failed:   %d", total_fails)
    logger.info("  Warnings: %d", total_warns)
    logger.info("=" * 50)
    return 1 if total_fails else 0


if __name__ == "__main__":
    sys.exit(main())
