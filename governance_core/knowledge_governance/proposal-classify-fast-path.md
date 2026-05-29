---
title: Proposal Classify Gate — Fast-Path Hard-Block (P-0076)
status: active
created: 2026-05-26
updated: 2026-05-26
owner: core
carrier_class: reference
tags: [governance, proposal, classify, hook, enforcement, p-0076]
related:
  - .claude/commands/proposal.md
  - .governance/clauses/art_05_cross_agent_collaboration.md
  - .claude/skills/proposal-vs-plan-mode-vs-commit.md
  - knowledge/governance/scope-enforcement-mechanism.md
---

# Proposal Classify Fast-Path Hard-Block

P-0076 在 Art.5.4 Proposal Classify Gate 的 4 层 soft enforcement 之上加了**第 5 层
machine hard-block**。本文是该机制的 reference doc。

> **TL;DR**：触及 17 类高敏路径（governance / harness / routing / infra / settings）
> 的 Edit/Write，session 内若未跑过 `/proposal classify`，PreToolUse hook 直接 exit 2
> BLOCK。Wall-time ~200ms，false-positive 由 fail-open + escape hatch 兜底。

## 1. 起源：2026-05-26 dogfood 事故

事故链：
1. user 报 "trade 给的是 MD 不是 HTML，可我们有 skill 判定载体啊" → 诊断 P-0053/P-0054
   规则齐备但 router triggers 全是术语化短语，自然语言零命中
2. agent (core) 决定改 `.claude/commands/learn.md` 加 Step 0 + 扩 router 触发词
3. **agent 跳过 `/proposal classify`**，直接 Edit 上述两文件，理由："两个文件都在 core
   scope 内，不需要 cross-agent proposal"
4. user 事后审视："判断是否进 proposal 的标准变成了只看是否 cross-agent，这让我担心"
5. agent 反思：违反 Art.5.4 第三段（明令反对 "all-own-scope" 为唯一筛）；改 `.claude/
   commands/learn.md` = **改 skill 体系**，按 L2 §1 必判 PROPOSAL_REQUIRED

事故原因可归到 user 提出的另一观察："C 加一个规则要 30s ？我以为 30ms" ——
当前 `/proposal classify` 是 LLM-driven judgment（5-15s），但 hard-block 路径根本
不需要 LLM；dict lookup + regex 30-200ms 就够。**架构本身可以拆 fast machine path +
slow LLM path**。

## 2. 5 层防御现状

| Layer | 实现 | 强度 | 触发 |
|---|---|---|---|
| **L1 治理条款** | `.governance/clauses/art_05_*.md` §5.4 | 治理硬要求 | agent 自觉读取 |
| **L2 skill 子命令** | `.claude/commands/proposal.md` `classify` | LLM-driven，仅被调用时生效 | agent 主动调 |
| **L3 决策 guide** | `.claude/skills/proposal-vs-plan-mode-vs-commit.md` | 决策辅助 | agent 想起来读 |
| **L4 keyword soft reminder** | `tools/proposal-classify-reminder.py` UserPromptSubmit | soft，不阻断 | prompt 含 32 keyword 之一 |
| **L5 machine hard-block** | `.claude/hooks/proposal-classify-fast.py` PreToolUse | **hard-block exit 2** | Edit/Write target ∈ paths 白名单 + session 无 classify log |

P-0076 加的是 L5。L1-L4 全保留，不替换。

## 3. fast-path 决策树

```
Edit/Write triggered
    ↓
[ enviroment check ]
    CLAUDE_CLASSIFY_FAST_DISABLE=1 ?
    Yes ──→ exit 0 (escape hatch; audited at audit/proposal_classify_fast_errors.jsonl + boundary_override_audit)
    No  ↓

[ path normalize ]
    extract tool_input.{file_path,path,notebook_path}
    normalize backslash → /, strip leading ./, strip _REPO_ROOT prefix
    ↓

[ allowlist match ]
    consult tools/proposal-classify-paths.json (17 globs / 5 categories)
    via tools/_classify_match.py (gitignore-style ** vs *)
    No match ──→ exit 0 (allow; ~95% of Edits, e.g. analysis/, models/, tests/)
    Match    ↓

[ session log check ]
    read .claude/cache/classify_log.jsonl
    find entry where session_id == current AND path in entry['paths']
    Found    ──→ exit 0 (allow + stderr "session has prior classify entry")
    Not found ↓

[ HARD BLOCK ]
    exit 2 + stderr (target / category / glob / fix cmd / escape hatch)
```

## 4. paths.json 白名单（17 globs / 5 categories）

| Category | Globs | Why |
|---|---|---|
| **governance** | `CLAUDE.md` / `constitution/**/*.md` / `contracts/**/*` / `agent_rules/**/*` / `.governance/**/*` | Constitution-level files; editing = governance change (L1 Art.13 + L2 §1 改全局治理) |
| **harness** | `.claude/commands/**/*.md` / `.claude/hooks/**/*.py` / `.claude/skills/*.md` / `.claude/agents/**/*.md` | Skill/hook/agent definitions; editing changes claude harness behavior. `.claude/skills/learned/*.md` excluded (agent-generated extractions) |
| **routing** | `knowledge/INDEX.routing.json` / `tools/proposal-classify-keywords.json` / `tools/proposal-classify-paths.json` | Router/keyword configs driving auto-injection and gate behavior |
| **infra** | `tools/sync_infra.py` / `tools/proposal_lib.py` / `tools/audit_*.py` | Cross-clone sync / proposal lifecycle / audit tooling; affects all 5 clones |
| **settings** | `.claude/settings.local.json` / `.claude/settings.json` | Claude Code permissions / hook registration |

Total empirical match: 133 files (~9% of repo); 91% of routine Edits pass through unimpeded.

## 5. Quick classify CLI（清账机制）

```bash
python tools/proposal_lib.py classify \
  --path "<target file>" \
  --description "<what & why>" \
  --quick
```

Behavior:
- Path 命中 paths.json OR description 命中 keywords.json → `PROPOSAL_REQUIRED`
- 否则 → `NO_PROPOSAL`
- 每次调用 append 一行到 `.claude/cache/classify_log.jsonl`
- 之后该 session 内对同 path 的 Edit 不再被 hook BLOCK

Wall-time: ~150-200 ms（含 Python startup）

## 6. Fail-open contract

下列情况 hook **必须** exit 0（不阻断）：
- stdin JSON 解析失败
- paths.json 缺失 / 无法读取
- _classify_match 导入失败
- classify_log.jsonl 路径不可写
- 任何未捕获 exception

所有 fail-open 事件写一行到 `audit/proposal_classify_fast_errors.jsonl`（含
ts / reason / exc_type / exc_msg / traceback）。

理由：宁愿放过一次错误的 Edit，也不能因 hook 自身 bug 锁死全 repo。

## 7. Escape hatch（环境变量）

```bash
$env:CLAUDE_CLASSIFY_FAST_DISABLE=1  # PowerShell
export CLAUDE_CLASSIFY_FAST_DISABLE=1  # bash
```

设置后，hook 立即 exit 0 不做任何检查。**仅在以下情况使用**：
- 调试 hook 自身（true positive 还是 bug？）
- batch operation（已 classified 多 path，session log 未刷盘 race）
- 紧急 disable（hook 误锁全 repo 需立刻恢复工作）

每次启用时 audit 到 `audit/proposal_classify_fast_errors.jsonl`（pending Phase 6
实现 startup banner）。**禁止**作为日常工作模式。

## 8. Session id 解析

按优先级：
1. `$CLAUDE_SESSION_ID`（Claude Code 注入）
2. `~/.claude/session_id_current.txt`（fallback）
3. `"unknown"`（最后兜底；同 session 的 classify log 仍可关联，但不同 session 共用
   "unknown" 也会被认为同一 session — 仅在极端 fallback 时短暂出现）

跨 session 的 log entry 不影响新 session 的 hook 判定（hook 比对 current
session_id 才认）。

## 9. 何时**不**走 fast-path

- 路径不在 17 globs 内 → 直接 NO_PROPOSAL，不进 hook 阻断
- description 含 architectural / ceremonial / handoff 等需 LLM 判断的描述 → 用
  LLM-mode `/proposal classify <description>` 走完整决策树（5-15s，但只在边缘
  case 调用）
- agent 不确定是 ceremonial vs. necessary proposal → LLM-mode

LLM-mode 的判定参考 `.claude/skills/proposal-vs-plan-mode-vs-commit.md`
（特别是 anti-pattern 部分判 ceremonial）。

## 10. 与现有防御的边界

| 邻近防御 | 边界 |
|---|---|
| `edit-write-guard.py` | 它管 cross-repo / scope / knowledge entry-point；本 hook 管 classify 入口。两 hook **均在** PreToolUse 链中，顺序：fast → edit-write → data-source → sensi → constitutional |
| `scope-guard.py` | Bash 命令的 scope 检查；与本 hook 在 Edit/Write 路径正交 |
| `session-boundary-guard.py` | cross-boundary 写阻断；本 hook 在 boundary 内额外加 classify gate |
| `command-guard.py` | shell deny list；不重叠 |

## 11. 演进政策

- **加 path 到白名单** → 改 paths.json + 跑 `python tools/test_proposal_classify_paths.py` 验证 budget < 150
- **加 keyword** → 改 keywords.json；本身在白名单内，需先 classify
- **移除 path / keyword** → 通过 proposal（弱化 enforcement 算 architectural change）
- **改 hook 行为** → proposal（hook 源 = L2 §1 必判 PROPOSAL_REQUIRED）
- **改 fail-open 语义** → proposal（动 fail-safe contract）

## 12. 6 周 retro（P-0076 Phase 6 计划）

待数据收集完成后跑：
- `tools/scan_classify_log.py`（待开发）→ 多少次 BLOCK / 多少 false positive / fail-open 次数 / wall-time 分布
- 根据数据调 paths.json + keywords.json
- 写 retro 到 `knowledge/decisions/adr-classify-fast-path.md`

---

**Status**：本文随 P-0076 Phase 5 落地。Phase 4 实施 hook，Phase 5 文档 + sync，
Phase 6 (optional) retro。
