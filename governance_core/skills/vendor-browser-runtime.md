---
theme: universal
---

# Vendoring a browser-side JS/CSS runtime (offline-first)

When the dashboard or any HTML artifact relies on a third-party runtime
(mermaid, cytoscape, d3, ...), **do not** load it from a public CDN.
GFW / corporate firewalls / air-gap dev silently fail and the artifact
falls back to a degraded view (e.g. mermaid's `:not([data-processed="true"])`
monospace fallback). Vendor the asset into the repo and load from
relative path.

## Three-step procedure

1. **Drop in the file**
   - Path: `knowledge/assets/vendor/<pkg>/<file>` (e.g. `mermaid/mermaid.min.js`)
   - Use the UMD/IIFE build, not ES modules — `file://` URLs can't load `import`
   - Source from `unpkg.com/<pkg>@<version>/...` or `cdn.jsdelivr.net/...`
   - Write `VERSION.md` next to it with: package name, version, source URL,
     license, file size, sha256, fetch date, bundle form, "why vendored",
     verification command, upgrade procedure (parity with
     `knowledge/assets/vendor/mermaid/VERSION.md`)

2. **Mark binary in `.gitattributes`**
   - `knowledge/assets/vendor/** binary` (already present since 2026-05-13)
   - **Why**: Windows clones with `core.autocrlf=true` will CRLF-convert
     the file on checkout, growing its size and invalidating the sha256
     in `VERSION.md`. Without `binary`, agent-core gets the canonical LF
     bytes but rules/trade/data/research get CRLF versions silently
     (browsers still load CRLF JS fine, so the bug hides until someone
     runs the sha256 verify step).
   - Migration: after the attribute lands, each clone with a stale CRLF
     copy runs `git checkout -- knowledge/assets/vendor/` to restore LF

3. **Update every consumer in the SAME commit**
   - Build script: copy `knowledge/assets/vendor/<pkg>/<file>` to the
     output artifact's sibling assets dir (see `tools/build_knowledge_dashboard.py`
     `build()` `vendored_assets` loop)
   - HTML templates: replace `<script src="https://cdn.../<pkg>/...">` with
     `<script src="./assets/vendor/<pkg>/<file>">` (relative path, NOT absolute)
   - Comments / docstrings / operations manual that mention "loaded from CDN":
     grep and update; otherwise drift between policy and artifact

## Verification before commit

```bash
# 1. sha256 matches VERSION.md
sha256sum knowledge/assets/vendor/<pkg>/<file>

# 2. No CDN URLs remain that should have been switched
grep -rn "cdn.jsdelivr\|unpkg.com\|cdnjs.cloudflare" knowledge/ tools/ .claude/ | grep -v VERSION.md

# 3. Rebuild artifact and confirm relative path in output
python -m tools.build_knowledge_dashboard
grep -n "<script src=" shared_state/knowledge/dashboard.html | grep -v "./assets/vendor/"
# expected: empty (no external script srcs left)

# 4. git check-attr confirms binary
git check-attr --all knowledge/assets/vendor/<pkg>/<file>
# expected: binary: set, text: unset
```

## Why this exists

2026-05-13: P-0054 Phase 2 vendored mermaid 11.4.1 (`knowledge/assets/vendor/mermaid/`)
but did **not** switch the dashboard's `<script src>` from CDN. Three
weeks later a user hit a flowchart that showed raw source instead of
SVG — silent CDN failure inside the GFW. The vendor file existed; the
consumer just wasn't using it. Same commit that fixed the dashboard
also vendored cytoscape (which had the identical CDN dependency) and
added `.gitattributes binary` after noticing CRLF drift across clones
(2,574,214 B vs canonical 2,571,900 B). All three steps must happen
together — vendoring without updating consumers, or without binary
attribute, leaves the system in a worse state than pure CDN (false
sense of offline-readiness).

## Related

- `knowledge/assets/vendor/mermaid/VERSION.md` — template for vendor sidecar
- `knowledge/governance/knowledge-html-profile.md` §5.2 — air-gap rationale
- `tools/build_knowledge_dashboard.py` `build()` — vendored_assets loop
- Commit `96e4ccce` — reference fix
