---
theme: universal
owner: core
---

# /wrap-up - 阶段总结

执行宪法第十四条阶段总结流程（STATE.md + Git + Notion + Skill Learning）。

## 1. 更新 STATE.md

- 读取当前 `STATE.md`（只含近 7 天条目，通常 < 200 行）
- 在 `## 1. Updates in This Session` 顶部新增本阶段条目
- 包括：改动摘要、涉及文件、关键决策、测试结果
- 格式与已有条目保持一致
- **Rotation**: 新增条目后运行以下命令将超过 7 天的条目归档到 `STATE_ARCHIVE.md`：
  ```bash
  python "$(git rev-parse --show-toplevel)/tools/rotate_state.py" --root "$(git rev-parse --show-toplevel)" --execute
  ```

## 2. Git 提交

- `git add` 本阶段所有改动文件（逐个列出，不用 `git add -A`）
- 使用 Conventional Commits 格式提交（见宪法第九条）
- 一个阶段对应一个提交，不拆散也不积压

## 2b. 知识库跨 agent 发布（若本阶段碰过 knowledge/）

> **Topology gate (P-0068)** — multi-agent step. If `.governance/config.json`
> has a single agent (`agents` length 1), print `[N/A — single-agent
> topology — skipped]` and skip this step (no other agents to publish to).
> Otherwise proceed.

检查本阶段的 git diff 是否包含 `knowledge/**` 路径：

```bash
git diff --name-only HEAD~1 HEAD -- knowledge/
```

- **有** knowledge 变更 → 强制调用 `/publish-knowledge` skill
  （push feature 分支；若 role=core，额外跨 clone collect 其他 agent 的
  net-new knowledge 到 master）
- **无** knowledge 变更 → 在检查清单标记"跳过（本阶段无 knowledge 变更）"

**为什么强制**：`sync_infra` 不路由 `knowledge/**`。若省略此步，master 的
统一 dashboard 看不到本 agent 本阶段写入，其他 agent 也看不到。2026-04-24
两次 dogfood 事故（EXP-2026-0010 + inspiration 库丢失）都是此步被跳过导致。

## 2c. Proposal 状态收尾（如本阶段触过 proposal）

```bash
git diff --name-only HEAD~1 HEAD -- proposals/
```

判断分支：
- **本阶段新增 proposal（A 文件）**：已是 `status: pending`（或 draft），无需转移；标记 "新增 N 条 pending"
- **commit message 含 "Implements: P-NNNN" 或 "Per proposal P-NNNN"**（v1.1.0 ID 格式，P-0001 Phase 2 起）：调
  `Skill(skill="proposal", args="complete P-NNNN")` 把对应 proposal 状态从 approved/in-progress
  转到 implemented，自动从 HEAD commit 抓 hash 写入；询问 user 是否立即归档到
  `proposals/_archive/<YYYY>/`
- **commit message 含 legacy "Implements: proposals/<X>.md"**：legacy id-less 引用，
  按文件路径定位 proposal；同上调 `Skill(skill="proposal", args="complete <X>")`；
  Phase 4 migration 后此分支退役
- **本阶段未触 proposal**：标记 "跳过（本阶段无 proposal 状态变更）"

Git diff 同时考虑 3 region：
- `shared_state/proposals/<agent>/` (in-flight，不在 repo git diff，但可由 `python tools/proposal_lib.py list` 验证)
- `proposals/_archive/<YYYY>/` (terminal archive，进 git)
- `proposals/*.md` 顶层 (legacy，进 git)

可选的快捷验证：

```bash
python tools/audit_proposals.py
```

确认本阶段写入的 frontmatter 合规（必填字段齐全、commit hash 可解析、
日期顺序正确）。

> 历史：proposal 状态机 + `/proposal` skill 在 2026-04-29 引入（见
> `proposals/proposal_state_machine_and_skill.md`）。之前 proposals/
> 是 flat 文件，已实现的与未实现的混在一起，session-context.py
> 列表持续累积成噪音。

---

## 3. 更新操作手册（knowledge/operations/）

检查本阶段是否有新增用户可操作能力（命令用法、配置项、服务启动等）：

- **如有**：编辑本项目的操作手册。手册路径由项目布局定义（P-0068）——多
  agent 项目用 `knowledge/operations/{agent}-manual.md`；自托管包项目（如
  governance-core，`knowledge/` 是 gitignored 安装产物）用 committed 的
  `docs/<agent>-manual.md`。
  - **core**：直接 Edit 本项目的 core 操作手册
  - **rules**：通过 `Skill(skill="learn")` 编辑 rules 操作手册
  - **trade**：通过 `Skill(skill="learn")` 编辑 trade 操作手册
  - **data**：通过 `Skill(skill="learn")` 编辑 data 操作手册
  - 内容：命令用法、参数说明、典型示例、配置位置、变更日期
- **如无**：在检查清单注明跳过原因（如"纯重构，无新操作能力"）

非 core agent 必须走 `/learn` skill 编辑（edit-write-guard.py L3 强制 entry
point；/learn 触发 dashboard rebuild，让操作手册的更新立即在统一 dashboard
上可见）。

禁止提示用户手动更新文档，必须自动执行。

> 历史：2026-04-28 之前本步骤推送到 Notion Page `32852783-...`。已迁移到本地
> `knowledge/operations/`，通过 dashboard 浏览，git 提供 audit trail，MCP 已退役。
> 见 `proposals/replace_notion_with_knowledge_operations.md`。

## 4. Skill Learning（Hermes-inspired）

在完成 STATE.md / Git / Notion 之后，执行 Skill 学习循环：

> **Capability gate (P-0068)** — Steps 4a–4c run on the `skills.discovery`
> machinery. If `skills.discovery` is not importable (the machinery is not
> yet packaged into governance-core — pending P-0069), print
> `[skill-extraction — capability pending P-0069 — skipped]` and skip Steps
> 4a–4c. **Step 4.0 below still runs** — lesson classification needs no
> machinery. Once P-0069 packages `skills.discovery`, the `python -m
> skills.discovery.*` commands below run with no PYTHONPATH (exact invocation
> finalized by P-0069).

### 4.0 先做分类决策（必做）

本阶段如果产生了任何"值得保留的教训"（design principle、workflow、user preference、decision rationale 等），**必须**先按 `.claude/skills/lesson-classification.md` 走一次路由判断：

- **Memory** — 用户/项目事实、慢速状态；被动召回够用
- **Skill guide** (`.claude/skills/<name>.md`) — 跨 agent 的设计原则或惯例；Registry L0 主动命中
- **Skill learned** (`.claude/skills/learned/<name>.md`) — 本 session 提取的工作流；继续 4a–4c
- **CLAUDE.md** — 不可违反的项目级规则；走提案
- **knowledge/** — 决策理由、实验结论、领域事实
- **discard** — bug fix 已被 diff/commit 捕获，不重复存

**反模式**：把设计原则塞进 feedback memory。钩子文本 100 字符不会在下次不同形态的问题上触发，等同于没存。判断关键：**"需要主动召回并在不同形态的未来工作中应用吗？触发模式能一句话描述吗？"** 是 → skill；否 → memory / 丢弃。

分类决定后再进入 4a–4c。若本阶段教训不属于"workflow"类（guide / CLAUDE.md / knowledge / memory / discard），4a–4c 的自动提取应跳过并在检查清单标明去向。

### 4a. 自动提取判断

```bash
python -m skills.discovery.tracker --should-extract
```

- 如果输出 `[YES]`：本阶段工作足够复杂，应提取为可复用 skill
  - 回顾本阶段 task list 和关键步骤
  - 运行 `/extract-skill` 将工作流提取到 `.claude/skills/learned/`（本 agent 自己的目录）
  - 在检查清单标记 `[x] Skill 已提取`
- 如果输出 `[NO]`：复杂度不足，跳过提取
  - 在检查清单标记 `跳过（复杂度不足）`

### 4b. 自动精炼判断

如果本阶段使用了 learned skill（通过 Registry L1 加载过），检查是否需要精炼：
```bash
python -m skills.discovery.extractor --auto-refine "<skill-name>"
```

- 对每个本阶段使用过的 learned skill 运行 auto-refine
- 如果输出 `[OK]`：skill 已根据实际执行步骤自动更新
- 如果输出 `[SKIP]`：无偏差，skill 已是最新

### 4c. Registry 更新验证

确认所有 skill 变更被 registry 正确发现（会同时扫描本 agent 的 learned/ 与 core 的 module/guide）：
```bash
python -m skills.discovery.registry --format table
```

## 5. 基础设施同步（仅 core agent）

> **Topology gate (P-0068)** — multi-agent step. If `.governance/config.json`
> has a single agent (`agents` length 1), print `[N/A — single-agent
> topology — skipped]` and skip this step — there are no other clones to
> sync to. (A self-hosted single-agent repo reflects package-source changes
> via `governance-core upgrade`, a separate mechanism — see core-manual.)
> Otherwise proceed.

如果本阶段修改了共享基础设施文件，自动同步到全体 agent clone。

**权威源（唯一）：`tools/sync_infra.py` 的 `ALWAYS_COPY_FILES` + `SKILL_DIRS` + 中心化 hook 列表**。本 skill 不复列具体文件清单——drift 风险已被前次事故证伪（2026-04-27 此 trigger list 漏列 `edit-write-guard.py` / `build_knowledge_dashboard.py` / `contracts/**` 等导致 sync 误判跳过）。

检查方式：

```bash
# 列出本阶段修改的所有文件
git diff --name-only HEAD~1 HEAD

# 提取 sync_infra 路由的所有路径（ALWAYS_COPY_FILES + SKILL_DIRS）
python -c "
import sys; sys.path.insert(0, 'tools')
import sync_infra as s
for p in s.ALWAYS_COPY_FILES: print(p)
for d in s.SKILL_DIRS: print(d + '/**')
"
```

如果两者有交集 → 跑 `python tools/sync_infra.py --execute`，无论 git diff 是否触及 wrap-up.md / extract-skill.md 等"明显"trigger。

如果完全无交集：在检查清单标记"跳过（无基础设施变更）"。

**两类同步语义**：
- **Centralized hooks**（settings.local.json 绝对路径指向 core）：修改即时生效，无需 sync。这类 hook 在 sync_infra 内部以 `CENTRAL_HOOKS` 等结构维护。
- **Per-clone copies**（每 clone 必须有本地副本，因 hook 用 `_REPO_ROOT` 解析自身 repo）：必须 sync 才生效。这类含 `.claude/hooks/edit-write-guard.py`、`.claude/hooks/scope-guard.py`，以及所有 `tools/`、`contracts/`、`.claude/commands/`、`.claude/agents/`、`.claude/skills/` 文件。

凡是不确定属于哪一类，以 `tools/sync_infra.py --execute` 的 dry-run 输出为准（先跑一次看会动哪些文件，再决定是否真同步）。

## 5b. /sync-repos 触发判断（fast-path）

> **Topology gate (P-0068)** — multi-agent step. If `.governance/config.json`
> has a single agent (`agents` length 1), print `[N/A — single-agent
> topology — skipped]` and skip this step (no other clones to merge).
> Otherwise proceed.

`/sync-repos` 把 master 最新内容跨 4 个 clone merge 一遍——开销大（每 clone
stash + fetch + merge + 冲突解 + 推 feature 远程 ≈ 总 5-10s + ~3KB skill body
重载）。**仅在以下任一条件成立时调用**：

1. Step 5 实际跑了 `tools/sync_infra.py --execute`（即 git diff 与 sync 路由
   有交集，per-clone copies 已变）
2. 本 commit 改了 `contracts/` / `agent_rules/` / `agents/` / 任何 hook 源文件
3. 上游 origin/master 距任一 clone 落后 ≥ 10 commits 或 ≥ 3 天
   （session-context.py drift 阈值，session 启动 banner 会显式提示）

**否则 skip**——理由：纯 doc / STATE / `knowledge/operations/` 的小改 push
到 master 后，其他 clone 没有"必须立即看到"的硬约束。它们各自下次 wrap-up
时会通过自己 feature 分支的 stash + fetch + merge 序列自然拉到。

跳过时检查清单标记："跳过（仅 doc/STATE 改动，无 infra/contracts/hook 变更）"。

## 6. 输出检查清单

完成后必须输出：

```
阶段总结检查:
- [x] STATE.md 已更新
- [x] Git 已提交 (commit: xxxxxxx)
- [x] 知识库已发布 / 跳过（原因: 本阶段无 knowledge/ 变更）
- [x] Proposal 状态已收尾 / 跳过（原因: 本阶段无 proposal 触动）
- [x] 操作手册已更新 / 跳过（原因: xxx）
- [x] 教训已分类（去向: memory / skill-guide / skill-learned / CLAUDE.md / knowledge / discard）
- [x] Skill 已提取 / 跳过（原因: xxx）
- [x] Skill 已精炼 / 跳过（原因: xxx）
- [x] Infra 已同步 / 跳过（原因: xxx）
```

未输出此清单 = 阶段总结未完成 = 禁止继续下一任务。
