---
title: Knowledge Carrier Classes (P-0053)
status: active
created: 2026-05-13
updated: 2026-05-13
owner: core
carrier_class: reference
tags: [governance, knowledge, taxonomy, carrier-class, p-0053]
related:
  - contracts/knowledge_frontmatter_schema.md
  - knowledge/governance/sub-constitution-red-lines.md
  - knowledge/governance/memory-staleness-policy.md
---

# Knowledge Carrier Classes

P-0053 落地的知识分类与载体边界。本文与 `contracts/knowledge_frontmatter_schema.md`
v1.1.0 的 `carrier_class` 必填字段一一对应——schema 是契约，本文是分类语义说明。

P-0054 在此之上决定每类的具体载体形式（MD vs HTML profile + autogen 数据块），
本文**不**规定载体形式。

## 1. 为什么需要分类

在引入 carrier class 之前，`knowledge/` 下不同性质的文档（一次性决策、不漂移
叙事、操作步骤、frozen 实验报告、会随生产漂移的现状汇总、提炼出的可复用因果
模式）混存在同一目录树，Agent 在 read / write / audit 时无法机读区分：

- 哪些应该当 decision record（写定不动）？
- 哪些是 reference（更新触发器是"系统变了"）？
- 哪些会过期（数字漂移）？
- 哪些可作 lesson 被 router 触发？

参考 Codex story-dreamer 项目的 P-0021（Knowledge Taxonomy and Lesson
Boundaries）的核心论点：**decision record ≠ lesson；reference ≠ lesson；
不能把背景架构图当 lesson 用**。这个分类边界在本项目同样成立，但本项目多
一个 codex 没有的 class：**current-state**——会随生产漂移的数字快照。

## 2. 六个 Carrier Class

| Class | 内容性质 | 主要存放路径 | 允许 autogen 块 | 可作 lesson |
|---|---|---|---|---|
| `decision-record` | 一次性决策 + 上下文 + tradeoff | `knowledge/decisions/adr-*.md` | 否 | 否（可提炼 derived-lesson） |
| `reference` | 不漂移叙事 / 系统结构 / 概念图 | `knowledge/{domain,governance,methodology,research,data-quality,trading,skills,features}/` | 否 | 否 |
| `runbook` | 操作步骤 / playbook | `knowledge/operations/*-manual.md` | 否 | 否 |
| `experiment-record` | frozen 实验报告（experiment_protocol 已强制冻结） | `knowledge/experiments/`（含 `archive/`）、`knowledge/datasets/` | 否 | 否 |
| `current-state` | **会随生产漂移**的现状汇总（数字快照 + 当前配置 + 当前数据集 ref） | `knowledge/models/*_current.md` | **是（强制）** | 否 |
| `derived-lesson` | 从事故 / 决策提炼的 reusable 因果模式 | `knowledge/lessons/`（P-0053 新增目录） | 否 | **是（唯一可作 lesson 的 class）** |

### 2.1 `decision-record`

**性质**：一次性决策的完整记录——背景、选项、tradeoff、决策、后果。一旦决策
作出 + 实施完成，内容写定不动；如果后续被新决策取代，加 `superseded_by`
指向新文件，自身保持原貌。

**更新触发**：仅在以下情况编辑：
- 实施过程中发现表述错误（typo / 链接失效）
- 决策被新 proposal 推翻 → 加 `status: deprecated` + `superseded_by`

**禁止**：用 decision-record 滚动追加新观察——那是 reference 或 current-state 的工作。

**示例**：`knowledge/decisions/adr-001-w120-window.md`、`adr-strangle-kline-lookback-and-snapshot.md`

### 2.2 `reference`

**性质**：系统结构 / 概念图 / 不漂移叙事 / 方法论 / 操作手册之外的"是什么"
类知识。不绑定具体时间点的数字。

**更新触发**：**系统行为变化**触发——例如 hook 调用链改了、scope 规则改了、
某个机制新增/删除。**不**因为某天指标更新而触发。

**禁止**：内嵌会随生产漂移的具体数字（precision、N、阈值……）。如果一份
reference 文档想展示当前数字，要么拆成 reference + current-state 两份，要么
就属于 current-state 而非 reference。

**示例**：`knowledge/domain/strangle_mechanics.md`、`knowledge/governance/data-flow.md`、
`knowledge/methodology/evaluation_metrics.md`

### 2.3 `runbook`

**性质**：操作步骤——按顺序执行的指令序列。读者预期照单执行，不预期理解
背后原理（原理在 reference / decision-record 里）。

**更新触发**：步骤本身变化——命令改了、顺序改了、增加 / 删除步骤。

**禁止**：把方法论 / 系统说明塞进 runbook（应在对应 reference 里 cross-link）。

**示例**：`knowledge/operations/core-manual.md`、`data-manual.md`、`trade-manual.md`

### 2.4 `experiment-record`

**性质**：一次实验的 frozen 报告——配置 / 数据集 / 结果 / 结论。
`experiment_protocol`（`knowledge/methodology/experiment_protocol.md`）已强制
要求这类报告写定不动；本 class 把该约束显式化。

**更新触发**：原则上**不更新**。仅允许后续 superseding 实验报告通过 `supersedes`
反向声明替代关系。

**禁止**：用 experiment-record 当 reference 用（"看这个实验报告了解系统怎么
工作"——错；应当从实验报告**抽取**结论到 reference 或 derived-lesson）。

**示例**：`knowledge/experiments/EXP-2026-0009-*.md`、`knowledge/datasets/dense_o2_2026-04-27.md`

数据集 snapshot 归入 experiment-record 是因为它们同样是一次性 frozen 产物——
某个时间点对某组数据的 manifest。

### 2.5 `current-state`

**性质**：会随生产漂移的现状汇总——某个 production model 当前的参数、
precision / N / 阈值、当前 canonical 数据集 ref、当前生效机制状态。

**更新触发**：**生产状态变化**触发——模型重训、参数调整、数据集换代。

**强制约束**：
1. 所有会漂移的数字 / 配置参数 **必须**封装在 autogen 块中（P-0054 定义协议；
   本文先要求占位符存在）
2. 手写数字 = audit fail（P-0053 Phase 2 起为 warning-only，P-0054 起为
   hard-fail）
3. 叙事部分（机制说明、公式推导、设计原理）人手写，与 autogen 块共存于同一
   文档

**禁止**：用 current-state 写已经 frozen 的历史（那是 experiment-record 的
工作）；用 current-state 写跨多个模型的对比（拆成多份 current-state 或归到
reference）。

**示例**：`knowledge/models/s30_current.md`、`knowledge/models/s50_current.md`

### 2.6 `derived-lesson`

**性质**：从事故 / 决策提炼的 **reusable causal pattern**：在 X 条件下，
因为 Y 原因，应该 / 不应该 Z。

**更新触发**：边界 / 条件 / 原因被新事件证伪或细化时更新。

**强制约束**（继承 codex P-0021 论点）：
1. 必须有"条件 / 原因 / 行动 / 边界"四元素，单纯"我们决定了什么"不是
   derived-lesson 而是 decision-record
2. 必须能 abstract 出**复用场景**——只发生过一次且不会再发生的事件不算
   derived-lesson
3. **唯一允许进 lesson 路由的 class**（如果未来引入 lesson-router）

**禁止**：把 decision-record 直接复制成 lesson（应当 abstract 出 reusable
reason，引用原 decision 即可）；把 reference / runbook 当 lesson。

**目录初始为空**：`knowledge/lessons/` 在 P-0053 Phase 1 建空目录 +
`INDEX.md`；具体 lesson 录入由各 agent 后续按需。

## 3. 现存子目录归属表

| 子目录 | 默认 carrier_class | 备注 |
|---|---|---|
| `knowledge/decisions/` | `decision-record` | ADR 类，一次性 |
| `knowledge/domain/` | `reference` | 领域知识 |
| `knowledge/governance/` | `reference` | 治理细则 |
| `knowledge/methodology/` | `reference` | 方法论 |
| `knowledge/operations/` | `runbook` | 操作手册 |
| `knowledge/experiments/` | `experiment-record` | 含 `archive/`，frozen |
| `knowledge/datasets/` | `experiment-record` | 数据集 snapshot 同理 frozen |
| `knowledge/models/` | **混合**：`*_current.md` → `current-state`；`*_evolution.md` / `production_changelog.md` → `reference`（append-only history） | 唯一需 per-file 判定的子目录 |
| `knowledge/features/` | `reference` | feature 清单，append-only 但不漂移 |
| `knowledge/research/` | `reference` | 调研报告 |
| `knowledge/research/inspiration/` | `reference` | 灵感来源 |
| `knowledge/data-quality/` | `reference` | 数据质量模式 |
| `knowledge/trading/` | `reference` | 交易知识 |
| `knowledge/skills/` | `reference` | skill 文档 |
| `knowledge/design/` | `reference` | UI / 组件 / 视觉设计参考（Phase 3 推断报告暴露的 governance gap，Phase 4 补录） |
| `knowledge/lessons/`（**P-0053 新增**） | `derived-lesson` | 唯一允许 derived-lesson |

`knowledge/models/` 是唯一需要 per-file 判定的子目录，因为它历史上同时承担
"当前生产快照"（漂移）与"演化历史"（frozen）两种角色。`audit_knowledge.py`
Phase 2 增加的 Check 会按文件名后缀 / 内容启发式给出推断（详见 P-0053 Phase 3）。

## 4. 与 `knowledge_frontmatter_schema.md` 的关系

P-0053 Phase 2 给 schema 增加必填字段：

```yaml
---
title: ...
status: active
created: ...
updated: ...
owner: core
carrier_class: reference   # ← 新增，必填
tags: [...]
---
```

枚举值即本文 §2 的六类。schema 版本 bump 1.1.0 → 1.2.0（minor，新增必填字段
但提供 transitional warn-only 期，遵守 schema §8 迁移政策）。

`audit_knowledge.py` 新增 Check：

1. **Check N+1**：`carrier_class` 字段存在且枚举合法
2. **Check N+2**：文件路径与 `carrier_class` 一致（参 §3 归属表）
3. **Check N+3**：`carrier_class: current-state` 文件含至少一个 autogen 块占位
   符（协议详见 P-0054；本 phase 仅检查标记 `<!-- autogen-placeholder -->`
   存在）

Phase 2 全部 Check 跑 **warning-only** 模式（schema §8.1 transitional），P-0054
完成后晋升 hard-fail。

## 5. 不在本 governance 范围

- **载体形式**（MD vs HTML）由 P-0054 决定，本文不涉及
- **autogen 块的具体语法**由 P-0054 定义，本文只约束"占位符必须存在"
- **批量回填现存 `knowledge/**/*.md` 的 `carrier_class` 字段**留给 P-0053
  Phase 3 之后的独立 backfill proposal（避免本 proposal 范围爆炸）
- **lesson-router 运行时机制**不引入（本项目用 `INDEX.routing.json` 已覆盖
  skill 路由场景）

## 6. 演进政策

新增 carrier class 需走 proposal 流程（修改本文 + 修改 schema + 修改 audit）。
**禁止**通过子宪法或 agent.md 单方面增加 class——本文是跨 agent 契约层。

class 重命名 / 删除视作 major version bump，触发全量 backfill。

## 7. 与现有相关文档的边界

| 邻近文档 | 边界 |
|---|---|
| `contracts/knowledge_frontmatter_schema.md` | schema 是契约（机器读），本文是分类语义说明（人读）。schema 列字段，本文释字段意义 |
| `knowledge/governance/memory-staleness-policy.md` | memory staleness 管的是 `~/.claude/.../memory/*.md`，与 `knowledge/**` 是两套系统。本文不覆盖 memory |
| `knowledge/governance/sub-constitution-red-lines.md` | 子宪法红线管 agent.md / 总宪法关系，与 carrier class 正交 |
| `knowledge/methodology/experiment_protocol.md` | experiment_protocol 强制 experiment-record 写定不动；本文将此约束抽象为 class-level rule |

---

**Status**: 本文随 P-0053 Phase 1 落地；P-0053 Phase 2-3 在 schema 与 audit 层
实施约束；P-0054 在此之上叠加 HTML profile + autogen 数据层。
