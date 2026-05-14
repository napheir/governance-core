"""Build / refresh `<section class="autogen-block">` content in knowledge HTML files.

P-0054 Phase 4. Implements the autogen-block protocol defined in
`knowledge/governance/knowledge-html-profile.md` §4 — the mechanism that
solves `current-state` carrier-class number drift (`s50_current.md` had
manually-typed precision / N / threshold values that went stale).

Each autogen block declares its data source (`data-source` repo-relative
path), an optional `data-source-jsonpath` (for JSON sources), and a
renderer identified by `data-autogen-id`. This script walks
`knowledge/**/*.html`, locates every autogen block, looks up its
registered renderer, loads + parses the source file, and rewrites the
content between `<!-- BEGIN AUTOGEN -->` / `<!-- END AUTOGEN -->`
fences atomically (filelock + os.replace).

Source missing -> retain old content + flag `data-render-status="stale"`;
never fabricate (governance §4.4 red line).

Renderer registry is intentionally narrow: each `data-autogen-id` must
map to exactly one registered function. Adding new blocks requires a
new renderer registration (or reusing one of the generic renderers).
This is a feature: code review surfaces every new autogen surface.

Usage:
    python tools/build_autogen_blocks.py                       # walk all knowledge/**/*.html
    python tools/build_autogen_blocks.py path/to/file.html ... # restrict to specific files
    python tools/build_autogen_blocks.py --check               # exit 1 if any block out of date (no writes)

Exit codes:
    0  success (or --check with everything fresh)
    1  --check found stale block(s), or a hard error (unregistered id /
       parse error / write failure)
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

try:
    from filelock import FileLock, Timeout
except ImportError:
    FileLock = None  # type: ignore[assignment,misc]
    Timeout = Exception  # type: ignore[assignment,misc]

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(message)s")

REPO_ROOT = Path(__file__).resolve().parent.parent
KNOWLEDGE_DIR = REPO_ROOT / "knowledge"
AUDIT_LOG_DIR = REPO_ROOT / "audit"
LOCK_TIMEOUT_S = 10

# Path prefixes (relative to knowledge/) skipped during default discovery.
# `assets/` holds the CSS / JS / vendor runtime PLUS `_fixture.html`,
# whose autogen blocks are static visual demos of the rendered / stale
# CSS states — they are not intended to be rebuilt by this tool. Mirror
# the same exclusion applied in tools/audit_knowledge.py.
SKIP_PATH_PREFIXES = ("assets/",)

# --- block discovery -----------------------------------------------------

# Matches the entire <section class="autogen-block" ...> ... </section>
# element. Requires the class to be exactly "autogen-block" (not just
# containing it) so we don't accidentally rewrite unrelated sections.
# DOTALL across the inner content; the outer <section> must be on its
# own opening line per the HTML profile (§2.3 indented form).
SECTION_RE = re.compile(
    r'(<section\b[^>]*\bclass="autogen-block"[^>]*>)'
    r'(.*?)'
    r'(</section>)',
    re.DOTALL,
)

# Fence markers inside the block (governance §4.1).
BEGIN_FENCE_RE = re.compile(r'<!--\s*BEGIN AUTOGEN[^>]*-->')
END_FENCE_RE = re.compile(r'<!--\s*END AUTOGEN[^>]*-->')

# Pulls a single `data-foo="bar"` attribute value out of an opening tag.
ATTR_RE_TMPL = r'\b{name}="([^"]*)"'


# --- renderer registry ---------------------------------------------------

RENDERERS: dict[str, "Renderer"] = {}


class Renderer:
    """Render a source-file payload into the inner HTML of an autogen block.

    Implementations receive:
      - `payload`: the parsed contents of `data-source` (dict / list / str
        depending on source type), already narrowed by `data-source-jsonpath`
        if present.
      - `attrs`: the opening tag's attribute dict (so renderers can read
        ancillary hints like a custom column order).

    Implementations return the HTML string that will replace the content
    between BEGIN/END fences. Whitespace at start/end is fine; the
    rewriter normalizes newlines.
    """

    def __init__(self, fn):
        self.fn = fn

    def __call__(self, payload, attrs: dict[str, str]) -> str:
        return self.fn(payload, attrs)


def register(autogen_id: str):
    """Decorator: bind a renderer to a single autogen-id."""
    def deco(fn):
        if autogen_id in RENDERERS:
            raise RuntimeError(f"duplicate renderer registration: {autogen_id!r}")
        RENDERERS[autogen_id] = Renderer(fn)
        return fn
    return deco


@register("demo-passthrough")
def _render_demo_passthrough(payload, attrs: dict[str, str]) -> str:
    """Reference renderer + smoke-test target.

    Emits a <pre>JSON</pre> dump of the payload. Used by the unit tests
    and by integrators who want to verify the build pipeline before
    writing a real renderer. Not intended for production knowledge files.
    """
    text = json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True)
    return f'  <pre><code class="language-json">{text}</code></pre>\n'


# --- core building -------------------------------------------------------

def _attrs_dict(opening_tag: str) -> dict[str, str]:
    """Extract every data-* attribute from a <section ...> opening tag."""
    out = {}
    for m in re.finditer(r'\b(data-[\w-]+)="([^"]*)"', opening_tag):
        out[m.group(1)] = m.group(2)
    # Also surface class for diagnostic logging.
    cls_m = re.search(r'\bclass="([^"]*)"', opening_tag)
    if cls_m:
        out["class"] = cls_m.group(1)
    return out


def _replace_attr(opening_tag: str, name: str, value: str) -> str:
    """Replace `data-NAME="..."` with the given value in an opening tag."""
    pattern = re.compile(ATTR_RE_TMPL.format(name=re.escape(name)))
    if pattern.search(opening_tag):
        return pattern.sub(f'{name}="{value}"', opening_tag, count=1)
    # Attribute absent — insert before the closing `>` (or `/>` if
    # somehow self-closing, but autogen blocks are non-empty).
    insertion = f' {name}="{value}"'
    return opening_tag[:-1] + insertion + opening_tag[-1]


def _apply_jsonpath(payload, jsonpath: str | None):
    """Narrow a JSON payload by a `$.foo.bar`-style path.

    Only supports dotted keys + bracket-int index — covers every
    real use case we have without dragging in a jsonpath library.
    Returns the payload unchanged when jsonpath is empty or "$".
    """
    if not jsonpath or jsonpath == "$":
        return payload
    if not jsonpath.startswith("$"):
        raise ValueError(f"jsonpath must start with $: {jsonpath!r}")
    cur = payload
    # Strip the leading $ then split tokens like .foo or [0]
    rest = jsonpath[1:]
    token_re = re.compile(r'\.([a-zA-Z_][\w-]*)|\[(\d+)\]')
    pos = 0
    while pos < len(rest):
        m = token_re.match(rest, pos)
        if not m:
            raise ValueError(f"jsonpath parse error near {rest[pos:]!r}")
        if m.group(1) is not None:
            cur = cur[m.group(1)]
        else:
            cur = cur[int(m.group(2))]
        pos = m.end()
    return cur


def _load_source(source_path: Path, jsonpath: str | None):
    """Load source file, parsing JSON when extension is .json."""
    if source_path.suffix.lower() == ".json":
        with source_path.open("r", encoding="utf-8") as fh:
            payload = json.load(fh)
        return _apply_jsonpath(payload, jsonpath)
    # Text fallback — renderer decides how to interpret.
    return source_path.read_text(encoding="utf-8")


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%dT%H:%M:%S%z")


def _mtime_iso(p: Path) -> str:
    return datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc).astimezone().strftime("%Y-%m-%dT%H:%M:%S%z")


# --- block-level rewrite -------------------------------------------------

class BlockResult:
    __slots__ = ("autogen_id", "status", "message")

    def __init__(self, autogen_id: str, status: str, message: str = ""):
        self.autogen_id = autogen_id
        self.status = status  # "rendered" | "stale" | "skipped" | "error"
        self.message = message


def _rewrite_one_block(match: re.Match, file_path: Path) -> tuple[str, BlockResult]:
    opening, inner, closing = match.group(1), match.group(2), match.group(3)
    attrs = _attrs_dict(opening)
    autogen_id = attrs.get("data-autogen-id", "")
    if not autogen_id:
        return match.group(0), BlockResult("<missing-id>", "error", "block missing data-autogen-id")

    renderer = RENDERERS.get(autogen_id)
    if renderer is None:
        return match.group(0), BlockResult(autogen_id, "error", f"no renderer registered for {autogen_id!r}")

    source_rel = attrs.get("data-source", "")
    if not source_rel:
        return match.group(0), BlockResult(autogen_id, "error", "block missing data-source")
    source_path = (REPO_ROOT / source_rel).resolve()

    # Source-missing branch (governance §4.3): retain old content, set
    # data-render-status="stale". Never fabricate.
    if not source_path.is_file():
        new_opening = _replace_attr(opening, "data-render-status", "stale")
        return new_opening + inner + closing, BlockResult(
            autogen_id, "stale", f"source missing: {source_rel}"
        )

    try:
        payload = _load_source(source_path, attrs.get("data-source-jsonpath") or None)
    except Exception as exc:
        return match.group(0), BlockResult(autogen_id, "error", f"source parse failed: {exc}")

    try:
        rendered = renderer(payload, attrs)
    except Exception as exc:
        return match.group(0), BlockResult(autogen_id, "error", f"renderer raised: {exc}")

    begin_m = BEGIN_FENCE_RE.search(inner)
    end_m = END_FENCE_RE.search(inner)
    if not begin_m or not end_m or end_m.start() <= begin_m.end():
        return match.group(0), BlockResult(autogen_id, "error", "missing or out-of-order BEGIN/END fence")

    new_inner = (
        inner[:begin_m.end()]
        + "\n"
        + rendered.rstrip("\n") + "\n"
        + inner[end_m.start():]
    )

    # Stamp timestamps on the opening tag.
    new_opening = _replace_attr(opening, "data-generated-at", _now_iso())
    new_opening = _replace_attr(new_opening, "data-source-mtime", _mtime_iso(source_path))
    # Clear any prior stale flag now that we have fresh data.
    new_opening = re.sub(r'\s+data-render-status="[^"]*"', '', new_opening)

    return new_opening + new_inner + closing, BlockResult(autogen_id, "rendered")


def _atomic_write(target: Path, content: str) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", newline="",
        dir=target.parent, prefix=".autogen-", suffix=".tmp", delete=False,
    )
    try:
        tmp.write(content)
        tmp.flush()
        os.fsync(tmp.fileno())
        tmp.close()
        os.replace(tmp.name, target)
    except Exception:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass
        raise


def process_file(file_path: Path, check_only: bool = False) -> list[BlockResult]:
    """Rewrite every autogen block in one HTML file (filelock-guarded)."""
    if not file_path.is_file():
        return [BlockResult("<file>", "error", f"not a file: {file_path}")]

    lock_path = file_path.with_suffix(file_path.suffix + ".lock")
    cm = FileLock(str(lock_path), timeout=LOCK_TIMEOUT_S) if FileLock else _NullLock()
    with cm:
        original = file_path.read_text(encoding="utf-8")
        results: list[BlockResult] = []
        rewritten_parts: list[str] = []
        cursor = 0
        for match in SECTION_RE.finditer(original):
            rewritten_parts.append(original[cursor:match.start()])
            replacement, result = _rewrite_one_block(match, file_path)
            rewritten_parts.append(replacement)
            cursor = match.end()
            results.append(result)
        rewritten_parts.append(original[cursor:])
        new_content = "".join(rewritten_parts)

        if not check_only and new_content != original:
            _atomic_write(file_path, new_content)

    return results


class _NullLock:
    """Fallback when `filelock` is not installed; serial scripts are fine."""
    def __enter__(self): return self
    def __exit__(self, *exc): return False


# --- CLI ----------------------------------------------------------------

def _discover_files(args_files: list[str]) -> list[Path]:
    if args_files:
        return [Path(p).resolve() for p in args_files]
    return sorted(
        p for p in KNOWLEDGE_DIR.rglob("*.html")
        if not any(
            p.relative_to(KNOWLEDGE_DIR).as_posix().startswith(pre)
            for pre in SKIP_PATH_PREFIXES
        )
    )


def _write_audit_log(all_results: dict[Path, list[BlockResult]]) -> Path:
    AUDIT_LOG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    log_path = AUDIT_LOG_DIR / f"autogen_build_{stamp}.log"
    lines = [f"# autogen-block build log {stamp}", ""]
    for fp, results in all_results.items():
        rel = fp.relative_to(REPO_ROOT) if fp.is_relative_to(REPO_ROOT) else fp
        lines.append(f"## {rel.as_posix()}")
        if not results:
            lines.append("  (no autogen blocks)")
        for r in results:
            lines.append(f"  [{r.status}] {r.autogen_id}" + (f" -- {r.message}" if r.message else ""))
        lines.append("")
    log_path.write_text("\n".join(lines), encoding="utf-8")
    return log_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh autogen-block content in knowledge HTML files")
    parser.add_argument("files", nargs="*", help="Specific files (default: knowledge/**/*.html)")
    parser.add_argument("--check", action="store_true", help="Report stale/error blocks; do not write")
    args = parser.parse_args()

    files = _discover_files(args.files)
    if not files:
        logger.info("[INFO] no HTML files found under %s", KNOWLEDGE_DIR)
        return 0

    all_results: dict[Path, list[BlockResult]] = {}
    error_count = 0
    stale_count = 0
    rendered_count = 0
    for fp in files:
        try:
            results = process_file(fp, check_only=args.check)
        except Timeout:
            logger.error("[FAIL] lock timeout: %s", fp)
            error_count += 1
            continue
        all_results[fp] = results
        for r in results:
            if r.status == "error":
                error_count += 1
            elif r.status == "stale":
                stale_count += 1
            elif r.status == "rendered":
                rendered_count += 1

    log_path = _write_audit_log(all_results)
    logger.info(
        "[OK] processed %d files: rendered=%d stale=%d error=%d (log: %s)",
        len(files), rendered_count, stale_count, error_count, log_path.relative_to(REPO_ROOT).as_posix(),
    )

    if args.check and (stale_count or error_count):
        return 1
    if error_count:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
