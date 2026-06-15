# -*- coding: utf-8 -*-
"""Tests for the proposal drafting suggestion helper (P-0097 / P-0100).

Covers the three mechanical recalls' hit / no-hit behaviour and the
no-silent-empty contract (each section renders （无）when empty).

Pure functions are exercised with synthetic data / temp files so the suite is
independent of the live proposal corpus; one integration smoke runs suggest()
against the real repo to confirm wiring.

Run from repo root:
    python tools/test_proposal_suggest.py
    # or: python -m pytest tools/test_proposal_suggest.py -q
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import proposal_suggest as ps


def out(line: str) -> None:
    sys.stdout.write(line + "\n")


# --- tokenization / matching primitives ------------------------------------

def test_tokens_ascii_and_cjk_bigrams():
    toks = ps.tokens("Hello 建议模块 ABC")
    assert "hello" in toks            # ascii lowercased, len>=3
    assert "abc" in toks
    assert "建议" not in toks          # stopword dropped
    assert "议模" in toks and "模块" in toks  # cjk bigrams
    assert "ab" not in toks           # ascii len<3 dropped


def test_kw_in_word_boundary_and_substring():
    assert ps.kw_in("PR", "cross-clone PR 风险")          # ascii word boundary
    assert not ps.kw_in("pr", "approve the change")       # no false substring match
    assert ps.kw_in("架构", "这是架构级改动")              # cjk substring
    assert not ps.kw_in("钩子", "纯文档润色")


def test_path_overlap():
    assert ps.path_overlap("tools", "tools/proposal_suggest.py")
    assert ps.path_overlap("knowledge/models", "knowledge")
    assert not ps.path_overlap("rules", "trade")
    assert not ps.path_overlap("", "tools")


# --- ① similar proposals ----------------------------------------------------

def _entries():
    return [
        {"id": "P-0001", "title": "todo proposal lifecycle linkage graduate",
         "slug": "p-0001-todo_linkage", "region": "archive",
         "blob": "todo proposal lifecycle linkage graduate"},
        {"id": "P-0002", "title": "knowledge dashboard briefing mode",
         "slug": "p-0002-briefing_mode", "region": "archive",
         "blob": "knowledge dashboard briefing mode"},
        {"id": "P-0003", "title": "lifecycle linkage hook",
         "slug": "p-0003-lifecycle_hook", "region": "in-flight",
         "blob": "lifecycle linkage hook"},
    ]


def test_score_corpus_orders_and_filters():
    desc = ps.tokens("lifecycle linkage graduate")
    res = ps.score_corpus(desc, _entries(), min_score=2, limit=5)
    ids = [e["id"] for e in res]
    assert "P-0001" in ids and "P-0003" in ids   # both share >=2 tokens
    assert "P-0002" not in ids                    # shares 0 → filtered
    assert res[0]["id"] == "P-0001"               # 3 shared > 2 shared, ranked first


def test_score_corpus_exclude_and_min_score():
    desc = ps.tokens("lifecycle linkage graduate")
    res = ps.score_corpus(desc, _entries(), min_score=2, limit=5, exclude="P-0001")
    assert "P-0001" not in [e["id"] for e in res]
    # raise threshold above any single entry's overlap → empty
    assert ps.score_corpus(desc, _entries(), min_score=99) == []


# --- ② checklist hits -------------------------------------------------------

_CHECKLIST = """# header preamble (ignored)

### Item A
- **触发**: 架构, multi-phase, binding
- **教训**: lessonA
- **怎么做**: howA
- **来源**: feedback_a

### Item B
- **触发**: 打包, wheel, package-data
- **教训**: lessonB
- **怎么做**: howB
- **来源**: feedback_b
"""


def _write_temp(name: str, content: str) -> Path:
    d = Path(tempfile.mkdtemp())
    p = d / name
    p.write_text(content, encoding="utf-8")
    return p


def test_parse_and_checklist_hit():
    items = ps.parse_checklist(_write_temp("c.md", _CHECKLIST))
    assert len(items) == 2
    assert items[0]["title"] == "Item A"
    assert items[0]["triggers"] == ["架构", "multi-phase", "binding"]
    assert items[0]["lesson"] == "lessonA"
    hits = ps.checklist_hits("这是一个架构级、多 phase 的改动", items)
    assert [h["title"] for h in hits] == ["Item A"]


def test_checklist_no_hit():
    items = ps.parse_checklist(_write_temp("c.md", _CHECKLIST))
    assert ps.checklist_hits("纯文案润色，无关治理", items) == []


# --- ③ likely scope ---------------------------------------------------------

def _allow_dir() -> Path:
    d = Path(tempfile.mkdtemp())
    (d / "core.allow.txt").write_text("tools/**\nknowledge_governance/**\n", encoding="utf-8")
    (d / "docs.allow.txt").write_text("docs/**\ncontracts/contract_x.md\n", encoding="utf-8")
    (d / "shared.deny.txt").write_text("secrets/**\n", encoding="utf-8")  # shared.* skipped
    return d


def test_scope_hit_path_and_alias():
    amap = ps.load_allow_map(_allow_dir())
    assert "shared" not in amap                          # shared.* excluded
    # explicit path token: "tools/..." in the description
    res = ps.scope_hits("改 tools/proposal_suggest.py 的逻辑", amap)
    assert "tools" in {r["token"] for r in res}
    tools_owners = next(r["owners"] for r in res if r["token"] == "tools")
    assert tools_owners == ["core"]                      # owned only by core
    # retained domain-neutral alias resolves with no explicit path: 工具 → tools
    res2 = ps.scope_hits("改一下工具脚本", amap)
    assert "tools" in {r["token"] for r in res2}


def test_scope_no_hit():
    amap = ps.load_allow_map(_allow_dir())
    assert ps.scope_hits("纯文档润色", amap) == []


# --- rendering: no silent empty (core acceptance) ---------------------------

def test_render_empty_emits_wu_for_all_three():
    empty = {"description": "x", "similar_proposals": [], "checklist": [], "scope": []}
    text = ps.render(empty)
    assert text.count("（无）") == 3                     # ①②③ each explicit
    assert "①" in text and "②" in text and "③" in text


def test_render_populated_shows_content():
    result = {
        "description": "x",
        "similar_proposals": [{"id": "P-0091", "title": "todo↔proposal 联动",
                               "slug": "s", "region": "archive", "score": 3}],
        "checklist": [{"title": "固化机制前实读", "lesson": "L", "how": "H", "source": "seed"}],
        "scope": [{"token": "tools", "owners": ["core"]}],
    }
    text = ps.render(result)
    assert "P-0091" in text and "固化机制前实读" in text and "tools" in text
    assert "（无）" not in text


# --- integration smoke against the real repo --------------------------------

def test_suggest_real_repo_structure():
    res = ps.suggest("todo 联动 proposal graduate 生命周期", limit=5)
    assert set(res) == {"description", "similar_proposals", "checklist", "scope"}
    assert isinstance(res["similar_proposals"], list)
    assert isinstance(res["checklist"], list)
    assert isinstance(res["scope"], list)
    # real checklist must parse to >0 items (the seed ships in the same PR)
    assert len(ps.parse_checklist(ps.CHECKLIST_PATH)) > 0


def _run() -> int:
    fns = [v for k, v in sorted(globals().items())
           if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            out(f"[PASS] {fn.__name__}")
        except Exception as exc:  # noqa: BLE001 — test runner reports all
            failed += 1
            out(f"[FAIL] {fn.__name__}: {exc!r}")
    out(f"\n{len(fns) - failed}/{len(fns)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(_run())
