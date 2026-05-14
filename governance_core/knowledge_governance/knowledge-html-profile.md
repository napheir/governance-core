---
title: Knowledge HTML Profile (P-0054)
status: active
created: 2026-05-13
updated: 2026-05-13
owner: core
carrier_class: reference
tags: [governance, knowledge, html-profile, mermaid, autogen, p-0054]
related:
  - knowledge/governance/knowledge-carrier-classes.md
  - contracts/knowledge_frontmatter_schema.md
  - knowledge/governance/data-flow.md
---

# Knowledge HTML Profile

P-0054 落地的"受限语义 HTML 载体"规范。本文规定哪些 carrier class（P-0053）
可走 HTML、HTML 文件长什么样、Mermaid 怎么双层渲染、autogen 数据块怎么写。

**前置依赖**：P-0053 `knowledge/governance/knowledge-carrier-classes.md`
已定义 6 个 carrier class；本文在分类层之上叠加载体形式层。

**借鉴源**：codex story-dreamer 项目 P-0022（Knowledge HTML Profile and
Mermaid Rendering）的"受限语义 HTML + Mermaid 双层"思路（render + source
同存），叠加本项目独有的 **autogen 数据块**协议（解决 current-state class
的数字漂移）。

## 1. 适用范围（哪些 class 可走 HTML）

| Carrier class | 是否走 HTML profile | 备注 |
|---|---|---|
| `reference` | **可选**（推荐复杂叙事 / 含流程图的文档迁 HTML）| MD 仍合法；profile 不强制迁移 |
| `runbook` | **可选** | 同上 |
| `current-state` | **强制**（v1.3.0 cutover 后；本 phase 仅 pilot 1 文件） | 必须配 autogen 块；不允许手写数字 |
| `derived-lesson` | **可选** | 同上 |
| `decision-record` | **禁止** | 一次性决策不需要 rich layout；MD 即可，diff-friendly 更重要 |
| `experiment-record` | **禁止** | frozen 报告由 `experiment_protocol` 强制冻结；不应改载体 |

**禁止迁 HTML 的元类型**（不在 carrier class 体系内）：
- `proposals/`（治理日志）
- `STATE.md` / `STATE_ARCHIVE.md`（append-only 历史）
- `.claude/skills/learned/*.json`（per-agent session state）
- `commit message` / PR description

## 2. HTML Profile 规范（受限语义子集）

### 2.1 文档骨架

```html
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="kc:carrier-class" content="reference">
  <meta name="kc:title" content="Harness Defense Mechanisms">
  <meta name="kc:owner" content="core">
  <meta name="kc:status" content="active">
  <meta name="kc:created" content="2026-04-10">
  <meta name="kc:updated" content="2026-05-13">
  <meta name="kc:tags" content="harness, hooks, defense, scope">
  <title>Harness Defense Mechanisms</title>
  <link rel="stylesheet" href="../assets/knowledge.css">
  <script defer src="../assets/vendor/mermaid/mermaid.min.js"></script>
  <script defer src="../assets/knowledge.js"></script>
</head>
<body>
  <article class="knowledge-record" data-carrier-class="reference">
    <header class="record-header">
      <h1>Harness Defense Mechanisms</h1>
      <p class="summary">One-paragraph TL;DR mirroring MD's TL;DR section.</p>
      <dl class="metadata">
        <dt>Carrier class</dt><dd>reference</dd>
        <dt>Owner</dt><dd>core</dd>
        <dt>Status</dt><dd>active</dd>
        <dt>Created</dt><dd>2026-04-10</dd>
        <dt>Updated</dt><dd>2026-05-13</dd>
        <dt>Tags</dt><dd>harness, hooks, defense, scope</dd>
      </dl>
    </header>

    <nav aria-label="Sections">
      <ol>
        <li><a href="#purpose">Purpose</a></li>
        <li><a href="#concepts">Concepts</a></li>
        <li><a href="#diagrams">Diagrams</a></li>
        <li><a href="#related">Related</a></li>
      </ol>
    </nav>

    <section id="purpose">
      <h2>Purpose</h2>
      <p>...</p>
    </section>

    <!-- additional sections per §2.4 required-sections table -->
  </article>
</body>
</html>
```

### 2.2 必填元数据

每份 HTML profile 文件 **必须**有：

1. **`<meta name="kc:*">` 双重镜像**（前缀 `kc:` = knowledge-class）：
   - `kc:carrier-class`（与 `data-carrier-class` 一致）
   - `kc:title` / `kc:owner` / `kc:status` / `kc:created` / `kc:updated` / `kc:tags`
   - 这是 frontmatter 在 HTML 里的等价物，audit 工具通过 meta 标签读取
2. **`<dl class="metadata">` 视觉镜像**：人读时看见的同一份元数据
3. **单一顶层 `<article class="knowledge-record" data-carrier-class="X">`**：
   - `X` 必须是 P-0053 的 6 类之一
   - 一份文件**只能**有一个顶层 `.knowledge-record`，禁止嵌套或多个并列
4. **`<title>` 与 `kc:title` 一致**
5. **`<html lang="zh-CN">`**（项目主语言；英文文件用 `en`）

### 2.3 格式硬约束

- **强制 indented、禁止 minify**：每个标签开新行，2 空格缩进
- **稳定 section id**：跨修订保持 id 稳定，避免破坏链接（如 `#purpose` 永远是 purpose section）
- **本地 CSS/JS only**：`<link rel="stylesheet">` 和 `<script>` 的 `src` / `href` 必须是相对路径，**禁止 CDN / 远程 URL**
- **禁止**：`<form>` / `<iframe>` / `<script src="https://...">` / `<link href="https://...">` /
  inline `<script>` 中含 `fetch(` / 任何 tracker / analytics
- **静态语义 HTML**：禁止 SPA / 动态加载内容 / mutation-heavy UI / hidden 内容
  在 JS 跑完后才显现的语义
- **不替换内容**：JS 可以增强（Mermaid 渲染、stale 标记）但**不能**通过 JS
  生成最终叙事文字——叙事必须在 HTML 源里就能 grep 到

### 2.4 必填 sections by carrier class

每类的 HTML profile 文件必须包含以下 `<section>`（按顺序）：

| `data-carrier-class` | 必填 sections |
|---|---|
| `reference` | `purpose` / `current-model`（叙事性"是什么"） / `concepts` / `diagrams` / `update-triggers` / `related` |
| `runbook` | `purpose` / `preconditions` / `steps` / `verification` / `rollback` / `failure-modes` / `related` |
| `current-state` | `purpose` / `mechanism` / `autogen-metrics`（**必须**含 autogen 块，见 §4）/ `update-triggers` / `sources` / `related` |
| `derived-lesson` | `summary` / `condition` / `reason` / `action` / `boundary` / `source` / `validation` / `related` |

`id` 命名规则：小写 kebab-case，无前缀。

audit 工具按 carrier class 校验 sections 存在；缺失即 fail。

## 3. Mermaid 双层模式

Mermaid 图必须同时满足"前端可渲染"和"源码可 grep"两个约束。统一模式：

```html
<figure class="diagram diagram-mermaid" id="diagram-governance-flow">
  <figcaption>Governance flow from task intake to wrap-up.</figcaption>
  <div class="diagram-render" aria-label="Rendered Mermaid diagram"></div>
  <details class="diagram-source">
    <summary>Mermaid source</summary>
    <pre><code class="language-mermaid">flowchart TD
  A[User task] --&gt; B[Governance check]
  B --&gt; C{Proposal needed?}
  C --&gt;|Yes| D[/proposal create]
  C --&gt;|No| E[Direct commit]
</code></pre>
  </details>
</figure>
```

### 3.1 渲染契约

`knowledge/assets/knowledge.js` 负责：

- 扫描 `.diagram-mermaid` 元素
- 把 `details.diagram-source code.language-mermaid` 里的源码读出来
- 用 Mermaid runtime 渲染成 SVG，注入 `.diagram-render`
- 设置 `data-render-status="rendered"`（成功）或 `data-render-status="error"`（失败）
- 失败时不抹除 `<details>` 源——source 永远可见

### 3.2 渲染失败回退（progressive enhancement）

CSS 必须让 `<details class="diagram-source">` 在 JS 失败时也清晰可读（默认展开
or 提供清晰的展开提示）。**source 可读性是 fallback，不是 debug-only 视图**。

### 3.3 安全要求

- Mermaid `securityLevel: "strict"`（禁止 arbitrary HTML labels）
- 不在 Mermaid 源里嵌入 raw `<script>` / `<iframe>` / `javascript:` URL
- Mermaid runtime 本地 vendored（pinned 版本 + license + integrity hash 记录），
  禁止 CDN（见 §5）

### 3.4 用 Mermaid 还是 SVG？

- **首选 Mermaid**：流程图、序列图、类图、状态图、ER、Gantt——可 diff 的文本源
- **退而求其次 SVG**：纯视觉图（截图导出、复杂排版）——把 SVG `<svg>` 内联到
  HTML 里同样可 grep，但 diff 不友好
- **禁止**：`<img src="*.png">` / `<img src="*.jpg">`——二进制图 git 不友好且
  源不可 grep

## 4. Autogen 数据块协议

本项目独有（codex 没有），用于解决 `current-state` class 的"数字漂移"问题。

### 4.1 基础模板

```html
<section class="autogen-block"
         data-autogen-id="s50-tier-metrics"
         data-source="artifacts/strangle50/training/2026-04-27/metrics.json"
         data-source-jsonpath="$.tier_breakdown"
         data-generated-at="2026-05-13T14:23:00+08:00"
         data-source-mtime="2026-05-12T22:10:00+08:00"
         data-stale-after-days="14"
         data-build-script="tools/build_autogen_blocks.py">
  <!-- BEGIN AUTOGEN: do not hand-edit; run build_autogen_blocks.py -->
  <table>
    <thead>
      <tr><th>Tier</th><th>N</th><th>Precision</th><th>Reach 80td</th></tr>
    </thead>
    <tbody>
      <tr><td>HIGH (3)</td><td>118</td><td>94.1%</td><td>96.0%</td></tr>
      <tr><td>MID (2)</td><td>98</td><td>86.7%</td><td>—</td></tr>
      <tr><td>LOW (1)</td><td>91</td><td>92.3%</td><td>—</td></tr>
    </tbody>
  </table>
  <!-- END AUTOGEN -->
</section>
```

### 4.2 必填属性

| Attribute | 含义 |
|---|---|
| `class="autogen-block"` | 标识 audit/build 入口 |
| `data-autogen-id` | 文件内唯一 id，便于 build script 定位 + 增量更新 |
| `data-source` | 真值源路径（相对 repo root），必须存在 |
| `data-source-jsonpath` | 可选；JSON 源时指定从哪个路径提取数据 |
| `data-generated-at` | ISO 8601 时间戳，build 时回写 |
| `data-source-mtime` | source 文件的 mtime，build 时回写；用于 staleness 检测 |
| `data-stale-after-days` | 距 `data-generated-at` 超过 N 天 → audit 报 stale |
| `data-build-script` | 哪个脚本生成的（一般是 `tools/build_autogen_blocks.py`）|

### 4.3 行为契约

| 场景 | build_autogen_blocks.py 行为 | audit_html_profile.py 行为 |
|---|---|---|
| Source 存在 + mtime 比 `data-source-mtime` 新 | 重新拉取数据 + 渲染 + 更新 mtime + generated-at | OK |
| Source 存在 + mtime 等于 `data-source-mtime` | no-op（已最新） | OK |
| Source 不存在 | **保留旧内容** + 加 `data-render-status="stale"` 属性 + 记 audit log | WARN: source missing |
| `data-generated-at` 距今超过 `data-stale-after-days` | 不主动 rebuild（mtime 是真值） | WARN: stale beyond threshold |
| `data-autogen-id` 重复 | error，build fail | FAIL: duplicate autogen-id |

### 4.4 红线

- **禁止**手动 Edit `<!-- BEGIN AUTOGEN -->` 与 `<!-- END AUTOGEN -->` 之间的内容
- **禁止** build script 在 source 缺失时 fabricate 数据
- **禁止**把 source 指向 secrets / `.env` / credentials；仅允许 `config/` / `artifacts/` /
  `knowledge/datasets/` / `contracts/`
- edit-write-guard 将增加规则阻断 autogen 块内部直接编辑（P-0054 Phase 4 实施）

### 4.5 何时不该用 autogen

- 叙事 / 推理 / 设计原理 → 手写
- 一次性 frozen 报告（experiment-record）→ 整篇手写，不用 autogen
- 截至某天的快照（如"2025 Q4 数据集 manifest"）→ frozen，不用 autogen
- 数据需要 LLM 解读才有意义 → 不在本协议范围

autogen 块只解 "**机器写、机器读、机器更新**" 的 cell-level 数字 + 配置参数。

## 5. 本地 vendored Mermaid + assets

### 5.1 文件位置

```
knowledge/assets/
├── knowledge.css                  # profile 样式（含 progressive enhancement）
├── knowledge.js                   # Mermaid bootstrap + stale block 视觉标记
├── _fixture.html                  # 本地浏览器渲染冒烟测试 fixture
└── vendor/
    └── mermaid/
        ├── mermaid.min.js         # pinned 11.x，~800KB
        └── VERSION.md             # source / version / license / sha256 / 升级记录
```

### 5.2 进 git 的理由

- 离线开发场景（air-gap 训练机）必需
- 版本锁定，避免 CDN 不可达 / supply-chain 风险
- 一次性 ~800KB 远低于 git LFS 阈值；可接受

### 5.3 升级流程

1. 从 https://github.com/mermaid-js/mermaid release 下载新版 min.js
2. 校验 sha256 hash
3. 更新 `vendor/mermaid/VERSION.md`（含旧→新版本号 / 校验和 / 升级原因）
4. 跑所有 pilot 文件本地浏览器验证渲染无 regression
5. commit 单独的 "chore(assets): upgrade mermaid X.Y.Z → A.B.C" 提交

## 6. 与相关 governance 文档的边界

| 邻近文档 | 边界 |
|---|---|
| `knowledge/governance/knowledge-carrier-classes.md`（P-0053）| 那是**分类层**（class 定义），本文是**载体层**（HTML profile）。class 在前，profile 跟随 |
| `contracts/knowledge_frontmatter_schema.md` v1.2.0 | schema 定义 MD frontmatter；HTML profile 用 `<meta name="kc:*">` 镜像同一组字段 |
| `knowledge/governance/data-flow.md` | 包含 Mermaid 图——首批迁 HTML 的候选（pilot 之外）|
| `knowledge/models/build_dashboard.py`（rules）| 那是 generated dashboard（汇总多个 entry），本 profile 是**单文件**载体。两者无冲突；dashboard 可链入 profile 文件 |

## 7. Pilot 范围（本 phase）

P-0054 仅迁 2 个 pilot 文件验证 profile 可行性，**不批量迁移**：

| 文件 | class | 验证目标 | 实施 phase | 作业 agent |
|---|---|---|---|---|
| `knowledge/domain/harness_defense.html` | reference | HTML profile + Mermaid 双层（含 hook 调用链流程图）| Phase 3 | core |
| `knowledge/models/s50_current.html` | current-state | HTML profile + autogen 数据块（数字层来自 config + artifacts）| Phase 5 | **rules**（owner=rules，core 提供模板 + 工具）|

Pilot 之外的批量迁移**留给独立 backfill proposal**，不属 P-0054 范围。

原 MD 文件 pilot 期间**保留**，加 deprecation banner 指向 .html，确保 grep
历史不断裂。

## 8. Audit 集成

`tools/audit_html_profile.py`（P-0054 Phase 6 实施）校验：

- 单一 `<article class="knowledge-record">` 顶层节点
- `data-carrier-class` 存在且 ∈ P-0053 枚举
- `<meta name="kc:*">` 元数据完整
- 无 CDN URL / 远程 script / form / iframe / inline fetch
- Mermaid 块同时含 `.diagram-render` + `<details class="diagram-source">`
- Autogen 块 attributes 完整、`data-generated-at` 未超 stale 阈值
- 必填 sections 按 carrier class 存在
- HTML 是 indented 不 minified

集成进 P0/P1 测试金字塔的契约层（`tests/contract/test_html_profile_compliance.py`）。

## 9. 演进与版本

本 profile v1.0.0 起效（P-0054 Phase 1）。后续修改：
- **Patch**：澄清 / typo / 加 worked example，无契约变更
- **Minor**：新增必填 section / 新增允许 carrier class / 加 autogen attribute
- **Major**：移除必填 section / 改变 meta tag 命名空间——必须走 proposal

audit 工具版本号跟随。当前 audit_html_profile.py v1.0.0 对应本文 v1.0.0。

---

**Status**: 本文随 P-0054 Phase 1 落地。Phase 2 准备本地 vendored Mermaid +
CSS/JS；Phase 3 pilot `harness_defense.html`；Phase 4 实施 build_autogen_blocks.py；
Phase 5 (rules agent) pilot `s50_current.html`；Phase 6 audit；Phase 7 sync。
