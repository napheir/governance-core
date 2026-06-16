---
theme: universal
---

# /learn - 知识库更新

回顾当前会话的工作，提取值得长期保留的知识并写入 `knowledge/`。

## 触发时机

- `/wrap-up` 的第 3 步会自动执行此流程
- 也可独立调用 `/learn` 在会话中途更新知识库（如刚做完一个重要实验）

## 执行流程

### Step 0: 判定 carrier_class + 载体形式（MD vs HTML profile）

**强制**：写入 `knowledge/**` 前必须先决定 carrier_class（P-0053）与载体形式
（P-0054）。这一步决定 Step 1 之后用什么模板、走 MD 还是 HTML profile。

**Step 0.1 — 判 carrier_class**（详见
`knowledge/governance/knowledge-carrier-classes.md` §2）：

| 内容性质 | carrier_class |
|---|---|
| 一次性决策 + tradeoff（写定不动） | `decision-record` |
| 系统结构 / 概念图 / 流程图 / 不漂移叙事 | `reference` |
| 操作步骤 / playbook | `runbook` |
| frozen 实验报告 / 数据集 snapshot | `experiment-record` |
| 会随生产漂移的现状（数字 / 参数 / 数据集 ref） | `current-state` |
| 从事故 / 决策提炼的 reusable 因果模式 | `derived-lesson` |

**Step 0.2 — 判载体形式**（详见
`knowledge/governance/knowledge-html-profile.md` §1）：

| carrier_class | 载体形式 |
|---|---|
| `reference` / `runbook` / `derived-lesson` | MD 默认；**含流程图 / 序列图 / 状态机 / 复杂叙事 → HTML profile（推荐）** |
| `current-state` | **强制 HTML profile**（v1.3.0 cutover 后；当前 pilot 期外的可留 MD，但新写应直接 HTML） |
| `decision-record` / `experiment-record` | **禁止 HTML**（diff-friendly 优先，必须 MD） |

**Step 0.3 — 输出**（在本次会话明确声明）：

```
[carrier_class] reference
[carrier_form] HTML profile   ← 因含"端到端流程图"
[target_path] knowledge/<domain>/<topic>-flow.html
```

**误用红线**：
- 写"端到端流程"、"管线流程图"、"数据流"、"调用链"类含流程图叙事 → 默认走
  **HTML profile + Mermaid 双层**，不要默认 MD
- 写 ADR / 实验报告 → **禁止 HTML**，必须 MD
- `current-state` 写漂移数字 → 必须含 autogen 块（`<!-- BEGIN AUTOGEN -->`）

判定完成后再进入 Step 1。HTML 载体的具体骨架 / Mermaid 双层 / autogen 协议见
`knowledge/governance/knowledge-html-profile.md` §2-§4，不在本 skill 复述。

### Step 1: 识别知识类型

回顾本次会话中的工作，识别属于哪类知识：

| 类型 | 目标文件 | 触发条件 |
|------|---------|---------|
| 实验结论 | `experiments/*.md` | 完成了实验，有 AUCPR/precision 等定量结果 |
| 生产变更 | `models/production_changelog.md` | 执行了 promote_model |
| 设计决策 | `decisions/adr-00X-*.md` | 做出了"选 A 不选 B"的决策并有理由 |
| 新坑/教训 | `methodology/known_pitfalls.md` | 发现了 bug、数据问题、方法论错误 |
| 特征变更 | `features/*.md` | 新增/废弃了特征，有验证数据 |
| 领域认知 | `domain/*.md` | 获得了关于市场/交易机制的新认识 |
| 模型状态 | `models/s30_evolution.md` 或 `s50_evolution.md` | 模型有里程碑变化 |

### Step 2: 判断是否值得记录

**记录标准**（满足任一）：
1. 定量结论：有数据支撑的实验结果（AUCPR, precision, signal count）
2. 决策理由：选择了方案 A，需要记住为什么不选 B
3. 失败教训：试过但失败了，未来不应重复
4. 认知变迁：之前以为 X，现在发现 Y

**不记录**：
- 纯代码重构（无新知识）
- Bug fix（除非揭示了方法论问题）
- 配置调整（除非改变了策略方向）

### Step 3: 写入知识文件

**更新已有文件时**：
1. Read 目标文件
2. 在合适位置追加新内容（Timeline 表格追加行、正文追加段落）
3. 更新载体的更新时间戳（**载体感知**）：**MD** → YAML frontmatter
   `updated:`；**HTML profile** → `kc:updated` meta 的 content（且若 status
   变了，同步 `kc:status`）。两种载体都必须 bump，否则 dashboard / staleness
   审计会读到陈旧时间戳。

**创建新文件时**：
1. 使用标准模板（见下方）
2. 在 `knowledge/INDEX.md` 的对应分类下注册

**一次不超过 3 个文件**。如有更多，优先级：production_changelog > known_pitfalls > experiments > decisions > features > domain

### Step 4: 验证 frontmatter 契约

符合 `contracts/knowledge_frontmatter_schema.md` v1.0.1+（6 必填字段）：

- [ ] `title` — 短标题（≤120 字符）
- [ ] `status` — 枚举 `{active, archived, draft, deprecated}`
- [ ] `created` — `YYYY-MM-DD`
- [ ] `updated` — `YYYY-MM-DD`，`>= created`
- [ ] `owner` — 枚举 `{rules, trade, data, research, core}`（本 agent 的 role）
- [ ] `tags` — 非空列表，lowercase kebab-case
- [ ] 有 TL;DR 一句话结论
- [ ] 只写结论，不复制原始数据（链接到 artifacts/REPORT.md）
- [ ] INDEX.md 已同步（如有新文件）
- [ ] 每个文件 < 100 行

> **HTML profile 载体**：上述 frontmatter 清单映射到 `kc:*` meta 集
> （`kc:title` / `kc:owner` / `kc:status` / `kc:created` / `kc:updated` /
> `kc:tags`），校验同样适用（含 `kc:updated >= kc:created`）。详见
> `knowledge/governance/knowledge-html-profile.md`。

**Decision-tracking 字段**（实验归档推生产时强制）：
- 若此 entry 替代了前代生产 entry → 加 `supersedes: experiments/archive/<prev>.md`
- 旧 entry 需同步 `status: archived` + `superseded_by: <new>` + `decision: ex_promoted`
- 这类"前后代对齐"推荐走 `experiment-manager` subagent 而非手写

## 文件模板

```yaml
---
title: 标题
status: active
created: YYYY-MM-DD
updated: YYYY-MM-DD
owner: rules          # 取本 agent role: rules/trade/data/research/core
tags: [tag1, tag2]
# 可选
related:
  - category/relevant-entry.md
supersedes: experiments/archive/EXP-prev.md     # 仅当替代前代时
---

> **TL;DR**: 一两句话结论。

## 背景

（为什么做这个事）

## 结论

（定量结果 + 关键发现）

## Evidence

- `artifacts/.../REPORT.md`
```

### Step 5: 重建 Dashboard（项目自备 renderer 时；可选）

> **gc #24 (P-0091)**：知识**渲染**工具已释放到 business/consumer 归属——gc
> 不再 ship knowledge renderer（gc 拥有治理内容 / 契约 / validator / taxonomy，
> 不拥有"项目如何渲染自己的知识"）。本步对 gc 治理工作流是**可选**的。

知识文件变更后，**若本项目拥有知识 renderer**（`tools/build_knowledge_dashboard.py`
存在，business-owned），重新生成统一 dashboard：

```bash
python tools/build_knowledge_dashboard.py
```

或用项目自备的 `/dashboard` 入口（若已采纳）。

- **无 renderer**（释放后从未采纳的项目）→ **跳过本步**，在检查清单注明
  "跳过（项目未采纳 dashboard renderer，gc #24）"。gc 治理工作流不强依赖 dashboard。

**输出**（若执行）: `shared_state/knowledge/dashboard.html`（浏览器打开即用；含客户端搜索 + owner/status/tag 过滤）

**触发判断**: 仅当项目有 renderer、且 Step 2 判定值得记录、且 Step 3 有实际文件写入时执行。纯 "[跳过] 本次为重构" 类不需要重建。

**验证**（若执行）: 命令成功的 stdout 必须含一行 `[OK] wrote <abs path>\shared_state\knowledge\dashboard.html (N categories, M entries)` 作为执行证据。**path 必须含 `shared_state`**。

### Step 6: 契约审计（强制）

写入后跑一次 audit 验证所有 entries 仍然合规：

```bash
python tools/audit_knowledge.py
```

**通过**: `Passed: N, Failed: 0`（Warnings 不阻塞）
**失败**: 读 FAIL 行修复再重跑。典型失败：owner 枚举错 / 日期格式错 / related 里 path 不存在

### Step 7: 跨 agent 发布（强制）

调用 `/publish-knowledge` skill 把本次 knowledge 写入推到 origin。

**为什么强制**：sync_infra 不路由 knowledge 内容，master 的统一 dashboard
要看到此次写入，本分支必须 push（或 core 跨 clone collect）。两次 dogfood
"dashboard 缺了最新 entry"（2026-04-24 EXP-2026-0010 + inspiration 库）
都是因为这一步被跳过——此 skill 把它从隐性纪律变成显式闭环。

**流程**：见 `.claude/commands/publish-knowledge.md`。简述：
- 非 core agent：commit + `git push origin HEAD`
- Core agent：额外跨 clone 采集其他 agent 未 push 的 knowledge + 重建 dashboard

## 输出

完成后输出更新摘要：

```
Knowledge 更新:
- [更新] experiments/xxx.md — 追加了 YYY 实验结论
- [新建] decisions/adr-007-xxx.md — ZZZ 决策记录
- [跳过] 原因: 本次为纯重构，无新知识
- [Dashboard] 已重建 -> shared_state/knowledge/dashboard.html
- [Audit]    Passed N, Failed 0
```
