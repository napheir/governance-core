---
title: Knowledge HTML Profile (P-0054)
status: active
created: 2026-05-13
updated: 2026-06-24
owner: core
carrier_class: reference
tags: [governance, knowledge, html-profile, mermaid, autogen, p-0054]
related:
  - knowledge/governance/knowledge-carrier-classes.md
  - contracts/knowledge_frontmatter_schema.md
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
| `experiment-record` | **禁止** | frozen 报告由实验协议强制冻结；不应改载体 |

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
      <p class="summary">面向业务读者的一段式 TL;DR（业务结论；非 MD 逐句镜像，见 §2.5）。</p>
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

### 2.2.1 可选元数据（P-0077 follow-up）

以下 `kc:*` 标签为**可选**，与 .md frontmatter 字段一一对应。Agent 视需要添加；
缺省即"未配置"，不报错：

| 可选 meta | 等价 .md frontmatter | 取值 | 行为 |
|---|---|---|---|
| `kc:briefing` | `briefing: pinned` / `briefing: serendipity` | `pinned` / `serendipity` | dashboard briefing panel surfacing；`pinned` 置顶 |
| `kc:related` | `related: [...]` | 逗号分隔路径列表 | 反向索引 + dashboard "related" 链接（v1.3.0 之后启用，先 reserve） |
| `kc:supersedes` | `supersedes: <path>` | 单一路径 | 标记本文取代了哪份历史 entry（dashboard 显示 supersedes 链） |
| `kc:superseded-by` | `superseded_by: <path>` | 单一路径 | 标记本文已被取代（dashboard 显示 deprecation 链） |

例（把一份 current-state 文档 pin 到 dashboard briefing 顶部）：

```html
<meta name="kc:briefing" content="pinned">
```

放在与 7 个必填 meta 同一 `<head>` 区，顺序不强制。

dashboard 消费侧（`tools/build_knowledge_dashboard.py:_extract_html_frontmatter`）
已在 P-0077 Phase 1 接入 briefing 字段；缺省时 entry 不进 pinned bucket
（与 .md 缺省同语义）。

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

### 2.5 信息构建原则（业务优先）

§2.1–§2.4 规定 HTML 的**结构**；本节规定 HTML 的**叙事语域**——写什么、用谁的语言写。
这是 P-0085 (2026-05-29) 补上的"信息构建层"，此前 profile 只管形式不管语域。

#### 2.5.1 MD 与 HTML 职能分工

| 载体 | 读者 | 职能 | 组织原则 |
|---|---|---|---|
| `.md` | agent / git / grep | 权威文本，diff-friendly | 字段、路径、枚举齐全；逐条可检索 |
| `.html` | 人 | 业务理解 | 业务叙事在前，机器细节渐进式披露 |

**HTML ≠ MD 的逐段镜像**。允许为服务阅读重组信息层级；同一份知识在两种载体里可以有
不同的组织顺序与详略。（这撤销了 §2.1 早期模板"mirroring MD"的隐含指引。）

#### 2.5.2 四条规则

1. **主叙事用业务语言**。每个概念 / stage / 步骤先回答业务问题：做什么业务动作？检查
   什么业务条件？输入产出是什么业务对象？
2. **机器细节下沉到 `<details>`**。字段名、函数签名、`reason_code` 枚举、config key、
   文件路径属于"详细说明"，默认折叠，不进主阅读流。
3. **表格列优先业务语义**。概览表的列名用业务说法（动作 / 输入对象 / 产出 / 拒绝原因
   的人话）；代码入口、字段枚举列移入折叠面板。
4. **可 grep ≠ 在视觉主线**。§2.3"叙事必须在 HTML 源里就能 grep 到"仍成立——折叠不
   等于删除，`<details>` 内容仍在 HTML 源里。业务主线与机器细节的区分是**视觉层级**，
   不是有无。

#### 2.5.3 正例 / 反例（governance-core upgrade pipeline）

| | 写法 |
|---|---|
| ❌ 反例 | 标题"代码事实"；首列 `installer.py::_render_assets`；核心动作"对 manifest 中每个 path 做 `os.replace()` 原子写；目标已存在且 `sha256` 与 baseline 不符则写入 `.governance/candidate-outbox/`" |
| ✅ 正例 | 标题"逐 Stage 升级动作"；核心动作"把最新治理资产安全铺到消费者仓库：逐个文件原子覆盖安装；遇到消费者本地改过的文件（内容与 baseline 不符）转存到待回流区、留待 hub 策展，绝不静默覆盖"；函数名 / `os.replace` / sha 比对收在该 stage 的 `<details>` |

#### 2.5.4 适用边界

本原则针对"**业务流程的 current-state / runbook**"类（读者关心业务结果，代码是实现
手段）。**纯技术 reference**（如 `harness_defense.html` 讲 hook 调用链）其"业务"本身
就是机器机制，字段 / 路径即主题——此时机器细节即业务细节，无需强行下沉。

判断准则：**读者是来理解业务结果，还是来理解机器机制本身？** 前者下沉代码，后者代码
即主线。

#### 2.5.5 Audit 立场

§2.5 是语域 / 框架原则，机器无法可靠判定"是否业务优先"。因此 **§2.5 不进 P0/P1
机器契约**，由 reviewer / `/code-review` 把关（见 §8）。`audit_html_profile.py` 只校
验结构（§2.1–§2.4 / §3 / §4），不判 voice。

#### 2.5.6 应用范围（whole-document，不止 cited example）

§2.5 适用于一份 HTML 的**每个 section**——表格、列表、散文、`<details>` 的
`<summary>`（折叠时仍可见，属主阅读流），不止某一张被点名的表。**worked example
（如 §2.5.3 的 upgrade pipeline 顶表）只是示范原则，不是应用边界。**

- **作者**：重写时通读全文，逐 section 自问"这段是业务语言还是 code-first？"——
  含 `<details>` 的 summary 行（应业务化，如"Stage 0 — 拉取最新包源、比对本地改动"
  而非"installer: rglob + sha diff"）。
- **reviewer**：把关 §2.5 时**通读整份文档逐 section 核对**，不能只看示例段落就放行。
- **反模式**（实证）：proposal 把"应用 §2.5"窄化成"改某一张表"，作者照做、其余
  section 仍 code-first——principle 名义生效、实际只落在 cited example 上。

提案 / 任务里写"应用 §2.5"时，scope 必须明确 **"全文每个 section"**，并把 worked
example 标注为"示范，非穷举"。

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

### 3.3.1 Strict mode 常见 pitfalls（P-0077 follow-up）

`securityLevel: "strict"` 下 Mermaid 比常用 demo 更严格。2026-05-26
首次 HTML pilot 实测踩到 2 类雷：

| ❌ 错误写法 | ✅ 正确写法 | 原因 |
|---|---|---|
| `A[Stage 0<br/>collect<br/>dedup]` | `A["Stage 0\ncollect\ndedup"]` 或 `A[Stage 0 collect dedup]` | strict 禁止 raw HTML in labels（`<br/>` 被剥 + 触发 syntax error） |
| `ART[artifacts/audit/&lbrace;ts&rbrace;/]` | `ART["artifacts/audit/{ts}/"]`（双引号包） | 裸 `{` 在 mermaid 是 rhombus 起始符；用双引号字面化整段 label |
| `B[some > comparison]` | `B["some > comparison"]` | `>`（未转义或 `&gt;` decode 后）破坏 arrow 解析 |
| `C[<b>bold</b> text]` | `C["**bold** text"]` 或纯文本 | strict 禁 HTML；mermaid 支持 markdown-like 加粗（需双引号） |

**通用规则**：含**任何 ASCII 标点**（`{` `}` `<` `>` `|` `;`）的 label 一律用双引号
包裹（`A["..."]`），不用 mermaid bare label 语法。这种习惯对 strict / loose
模式都安全，是 mermaid v10+/v11+ 通用最佳实践。

**多行 label**：`\n` 在双引号 label 中代表换行（不是 `<br/>`）：
```
A["line 1\nline 2\nline 3"]
```

**故障表现**：错误的 mermaid 源在 dashboard modal / file:// 直开时显示
"Syntax error in text mermaid version XX" + 炸弹图标。源 `<details>` 仍可
点开看原文（§3.2 fallback），方便定位。

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
         data-autogen-id="governance-audit-summary"
         data-source="artifacts/audit/2026-05-13/summary.json"
         data-source-jsonpath="$.checks"
         data-generated-at="2026-05-13T14:23:00+08:00"
         data-source-mtime="2026-05-12T22:10:00+08:00"
         data-stale-after-days="14"
         data-build-script="tools/build_autogen_blocks.py">
  <!-- BEGIN AUTOGEN: do not hand-edit; run build_autogen_blocks.py -->
  <table>
    <thead>
      <tr><th>Audit</th><th>Targets</th><th>Pass</th><th>Warn</th></tr>
    </thead>
    <tbody>
      <tr><td>proposals</td><td>20</td><td>100%</td><td>0</td></tr>
      <tr><td>hooks</td><td>21</td><td>100%</td><td>0</td></tr>
      <tr><td>clauses</td><td>17</td><td>94.1%</td><td>1</td></tr>
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
| `contracts/knowledge_frontmatter_schema.md` v1.2.0 | schema 定义 MD frontmatter；HTML profile 用 `<meta name="kc:*">` 镜像同一组**元数据**字段，但**正文组织独立于 MD**（载体职能不同，见 §2.5） |
| 某 consumer 的 generated dashboard 脚本（汇总多个 entry）| 那是 generated dashboard，本 profile 是**单文件**载体。两者无冲突；dashboard 可链入 profile 文件 |

## 7. Pilot 范围（本 phase）

P-0054 仅迁 2 个 pilot 文件验证 profile 可行性，**不批量迁移**：

| 文件 | class | 验证目标 | 实施 phase | 作业 agent |
|---|---|---|---|---|
| `knowledge/governance/harness_defense.html` | reference | HTML profile + Mermaid 双层（含 hook 调用链流程图）| Phase 3 | core |
| `knowledge/<domain>/<name>_current.html` | current-state | HTML profile + autogen 数据块（数字层来自 config + artifacts）| Phase 5 | 消费者域 agent（owner=该域 agent，core 提供模板 + 工具）|

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

**§2.5 不在机器审计范围**（P-0085）：业务优先 / 机器细节下沉是**语域原则**，机器无法
可靠判定"是否业务优先"。`audit_html_profile.py` 只校验**结构**（§2.1–§2.4 / §3 / §4），
**不判 voice/framing**。§2.5 由 reviewer / `/code-review` 这一 human-review layer 把关。
不为 §2.5 假装机器强制——避免 audit 给出"通过"的假信号。

## 9. 演进与版本

本 profile v1.0.0 起效（P-0054 Phase 1）。当前 **v1.1.1**（P-0086，2026-05-30：
de-trade 既有示例残留，Patch）。后续修改：
- **Patch**：澄清 / typo / 加 worked example，无契约变更
- **Minor**：新增必填 section / 新增允许 carrier class / 加 autogen attribute /
  新增 normative 原则节（如 §2.5）
- **Major**：移除必填 section / 改变 meta tag 命名空间——必须走 proposal

audit 工具版本号只跟随**结构**契约。当前 `audit_html_profile.py` v1.0.0 对应本文
§2.1–§2.4 / §3 / §4 结构规则；§2.5 是 human-review layer，de-trade 只改示例措辞，
两者都不动结构，故 audit 工具不随本文 v1.1.x bump（见 §8）。

### 版本历史

- **v1.1.1**（2026-05-30，P-0086）：de-trade 既有示例残留——§2.2.1 caption、§3.3.1
  strict-mode Mermaid 例、§4.1 autogen 整例、§7 pilot 行 + Status footer 里的消费者
  域示例 genericize 为 gc 自身域（候选 collect/audit pipeline、governance-audit-summary
  等中性例子）。P-0078 cluster 遗留，机制 / 契约 / 结构零改、audit 工具不 bump。
- **v1.1.0**（2026-05-29，P-0085，promote 通用层候选 #18 / trade-agent）：新增 §2.5
  信息构建原则（业务优先，含 §2.5.6 whole-document 应用范围）；修正 §2.1 模板
  "mirroring MD"措辞；§6 补正文组织独立说明。worked example 已 de-trade 化为
  governance-core upgrade pipeline。
- **v1.0.0**（2026-05-13，P-0054 Phase 1）：初始 profile。

---

**Status**: 本文随 P-0054 Phase 1 落地。Phase 2 准备本地 vendored Mermaid +
CSS/JS；Phase 3 pilot `harness_defense.html`；Phase 4 实施 build_autogen_blocks.py；
Phase 5 消费者域 agent pilot current-state 文档；Phase 6 audit；Phase 7 sync。

