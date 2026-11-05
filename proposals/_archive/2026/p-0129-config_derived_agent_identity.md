---
id: P-0129
agent: core
status: implemented
created: 2026-11-05
approved_at: 2026-11-05
started_at: 2026-11-05
implemented_in: e5e3dfb
implemented_at: 2026-11-05
owner: core
---

# Proposal P-0129: Config-derived agent identity + multi-clone install fixes (deva-vani report)

## Trigger

deva-vani（第二个多 clone 消费者，拓扑 core / platform / experience / content）初始化时，其 core agent
发来问题报告 `artifacts/deva-vani/2026-11-05-issues-from-deva-vani.md`（gitignored），列出 governance-core
0.45.1 的 8 个问题（初版 6 个，后补 2 个），其中 1 个是安全问题。owner 要求上游给出长期方案，替代 deva-vani 本地临时补丁
（其本地提案 P-0001，非本仓库 id）。

本仓库逐条核实全部属实，并新发现 2 个同族问题（F7、F8），共 F1–F10。改动涉及 hook 源、installer、跨 agent 隔离语义，
属安全敏感、多 phase 的治理变更 → PROPOSAL_REQUIRED。

## Current State (read, not assumed)

**F1【安全】角色身份写死上游角色，未知分支一律当 core**
- `governance_core/hooks/_guard_common.py:58-65` `ROLE_PREFIX_MAP` 只含 trade/models/data/simu/rules/research；
  `detect_role()`（`:68-93`）对未知分支、git 失败都 `return "core"`。
- 消费方：`edit-write-guard.py:632` 拿到 `core` 后在 `:695-696` 直接 `sys.exit(0)`，L1-L4（跨仓库、allow list、
  knowledge 入口、datasets 入口）全部跳过；`scope-guard.py:128-130` 同样早退；`data-source-guard.py:259`。
- 同族重复实现 4 处，各自写死角色表：`session-context.py:41-60`、`merge-audit.py:38-45,56-70`、
  `tools/proposal_lib.py:102-130`（`detect_agent`，决定提案写进 `shared_state/proposals/<agent>/` 哪个目录）、
  `tools/regen_constitution.py:56`（读 `.role`，再退到目录名）。
- `scope-guard.py:80-81` 调 `_detect_role_shared()` 不传 `repo_root`，按 **cwd** 的分支判定，而不是 hook 所在 clone。
- 按分支判定还有一个旁路：业务 clone 里 `git checkout master` 即升格为 core。
- 全仓没有任何角色识别测试（`git grep detect_role governance_core/tools/test_*.py` 为空）。
- deva-vani 实测 `detect_role('../agent-platform') -> core`。

**F2 第二次 install 删除项目自有的混合条款**
- `installer.py:131-139` `MIXED_CLAUSES` 7 条；`_render_clauses`（`:288-314`）首次渲染时 `append` 进 `written`
  → 被登记进 `installed_files.json`；之后已存在则 `continue`、不再出现在新安装集合。
- `_prune_stale`（`:466-523`）把"旧清单有、新安装集合没有"的路径 `unlink()`；`STALE_PRUNE_EXEMPT`（`:114-125`）不含它们。
- 实证：deva-vani 四个 clone 的 `.governance/clauses/` 都只剩 11 个文件，缺的正是这 7 条
  （本会话的 bootstrap 路线 install 后再 `expand`，等于第二次 install）。hub 自身未中招：其
  `installed_files.json` 不含这 7 条（hub 的这些文件早于清单机制存在）。

**F3 多 clone 初始化时会话边界死锁**
- `tools/sync_infra.py:167-173` 把 `.claude/settings.json`（声明 `projectRoot: "../"`）列入 `ALWAYS_COPY_FILES`，
  假定 core 已有；但 installer 与 mab 都不生成它（`git grep projectRoot governance_core/installer.py` 为空）。
- 缺它时 session-boundary-guard 的边界只到 clone 本身，提案要写的 `../shared_state/` 在边界外；要补这个文件
  又被 classify 判 PROPOSAL_REQUIRED → 死锁，deva-vani 只能用 `CLAUDE_BOUNDARY_OVERRIDE=1` 重启解开。
- **与 F1 的耦合**：在 F1 未修时声明 `projectRoot: "../"`，业务 agent（被当 core）即可写整个项目目录。

**F4 新项目宪法上下文为空**
- mab 模板 `CLAUDE.md` 写"通用条款以 `.governance/clauses/` 为准"（指针式），而 gc 的
  `tools/regen_constitution.py:171-196` 把 `CLAUDE.md` 视为 `constitution/total.md + agent.md` 的生成物；
  新项目的 `total.md`（mab 模板，内容 "Populated by `governance-core install` from clauses/"——gc 实际并不填充）
  与 `agent.md` 都是 stub → 启动即 `[STALE]`，照提示 regen 会把模板 Art.A/B 占位盖掉，且生成结果不含任何条款。

**F5 `.role` 未进 `.gitignore`**
- `regen_constitution.py:56-70` 文档称 `.role` 是 gitignored 的 per-clone 文件；mab 渲染的 `.gitignore`
  （`deva-vani/agent-platform/.gitignore`）没有该项；installer 不管理 `.gitignore`。

**F6 session-context 把 STATE 模板注释当条目**
- `session-context.py:62-87` 用 `^### ` 切条目；`installer.py:569-572` 种下的 STATE 模板注释里正有
  `### YYYY-MM-DD -- <short title>`。hub 自身 SessionStart 也复现（"Recent state: ### YYYY-MM-DD — ..."）。
- 对照：`tools/rotate_state.py:29` 用 `^### (\d{4}-\d{2}-\d{2})`，不受影响。

**F7（本仓库新发现）scope-guard 跨仓库拦截在嵌套布局下失效**
- `_guard_common.py:23-46` 用 `<install_root 目录名>/<clone_dir>` 做子串模式；`own_repo_pattern`（`:112-126`）却用
  `<clone 父目录名>/<clone 目录名>`。deva-vani 的 `install_root` 是 `workshop-claude`、clone 在
  `workshop-claude/deva-vani/agent-*`，模式 `workshop-claude/agent-platform` 永远不出现在真实路径里
  → `scope-guard.py:135` 的 Bash L1 跨仓库拦截从不触发。edit-write-guard 的 L1（`:713`）用路径前缀，不受影响。
- 根因：`install_root` 语义两义（gc 视为 clone 的父目录；mab 视为项目目录的父目录）。

**F8（本仓库新发现）非 core agent 可改自己的 guard**
- `edit-write-guard.py:727` 对 `.claude/` 下任何路径一律放行，包括 `.claude/hooks/*.py` 与
  `.claude/settings*.json`；deva-vani 的 hook 经 `${CLAUDE_PROJECT_DIR}/.claude/hooks/...` 接线（每 clone 跑自己的副本），
  所以业务 agent 一次 Edit 即可改掉或摘除自己的 guard。

**F9（deva-vani 补充）提交前 scope 门禁不存在**
- 包源 `governance_core/agent_rules/` 只有 `shared.*`，installer 不生成任何 `<agent>.allow.txt`
  （`git grep allow.txt governance_core/installer.py` 为空）。
- `tools/check_scope.py:51-55` 缺 allow 文件即 `[FATAL]`，对 core 也一样（`--agent core` 同样需要 `core.allow.txt`，
  与 guard 里"core 不受 allow list 约束"不一致）；非 staged 模式另需 `.baseline_commit`（`:113-117`），installer 也不生成。
- 包里没有 pre-commit 模板，installer 不写 `.git/hooks/pre-commit`（`git grep pre-commit governance_core/installer.py` 为空）；
  `check_constitution_change.py:5` 与 edit-write-guard 的提示都假定 pre-commit 存在。第十二条的提交前防线对所有消费者都只在纸面上。
- 现状下非 core agent 的 Edit/Write 在没有 allow.txt 时是 deny-all（`edit-write-guard.py:78-102`），所以 F1 修好后，
  deva-vani 的业务 agent 在补齐 allow.txt 前写不了任何业务文件。

**F10（deva-vani 补充）消费者 `.gitignore` 缺运行时条目**
- hub `.gitignore` 有 `/.claude/cache/`、`/.claude/skills/learned/.usage.json`、`/audit/`、`/.governance/installed_files.json`、
  `/.governance/candidate-outbox/`；installer 不管理 `.gitignore`，mab 模板也没有这些项。另有 `direction-guard.py:32`
  写的 `.claude/hooks/.direction_check_ts`。

## Scope

- `governance_core/hooks/_guard_common.py`：新增 `resolve_agent()` + `load_topology()`；删 `ROLE_PREFIX_MAP` / 分支判定；
  跨仓库模式改为由真实 clone 路径推导；`detect_role()` 保留为薄包装（返回 agent 名）。
- `governance_core/hooks/{edit-write-guard,scope-guard,data-source-guard,session-context,merge-audit}.py`：改用 `resolve_agent()`；
  core 判定改为 `== core_agent_name`；scope-guard 传 `_REPO_ROOT`；edit-write-guard `.claude/` 放行收窄（F8）；
  session-context 条目解析对齐 `rotate_state._ENTRY_RE`（F6）。
- `governance_core/tools/{proposal_lib,regen_constitution}.py`：`detect_agent` / `detect_role` 改为加载 hook 目录的
  `_guard_common.resolve_agent`；`.role` 退役（F5）。
- `governance_core/installer.py`：混合条款不进清单 + 旧清单迁移（F2）；多 clone 拓扑下幂等写 `.claude/settings.json`
  的 `projectRoot`（F3）；`total.md` 缺失时种子化并 regen `CLAUDE.md`（F4）；`doctor` 增加身份可解析检查。
- `governance_core/installer.py`（续）：首次 install 为每个非 core agent 种子化 `agent_rules/<agent>.allow.txt`（F9）；
  安装 `.git/hooks/pre-commit`（F9）；幂等维护 `.gitignore` 的受管运行时块（F10）。
- `governance_core/tools/check_scope.py`：`core_agent_name` 直接 `[OK]`；缺 allow 文件给出可操作提示（F9）。
- `governance_core/templates/constitution_total.md`、`governance_core/templates/pre-commit`（新，非 .py → `pyproject.toml` package-data）。
- 新测试：`governance_core/tools/test_agent_identity.py`、`test_installer_mixed_clauses.py`、
  `test_installer_topology_anchor.py`、`test_session_context_state.py`、`test_installer_constitution_seed.py`、
  `test_installer_commit_gate.py`、`test_installer_gitignore_block.py`。
- 文档：`docs/core-manual.md`（身份解析、`.role` 退役、`projectRoot` 生成）；hook docstring 中的 `feature/trade-*` 示例去业务化。
- 版本：见 Phases（建议 0.46.0 + 0.47.0 两次发布）。

## Design & Contract

### Interfaces, I/O & Realization

- `_guard_common.load_topology(repo_root: str) -> dict`
  - INPUT：`<repo_root>/.governance/config.json` 的 `agents[].{name, clone_dir}`、`core_agent_name`。
  - OUTPUT：`{"agents": [...], "core": <core_agent_name>}`；文件缺失 / 不可解析 / 缺字段 → 抛 `TopologyError`
    （显式成员判断，不用 `.get(k, default)`，Art.4）。仅用 stdlib，自包含（hook 不得 import `governance_core`，
    见 runtime-import-discipline）。
- `_guard_common.resolve_agent(repo_root: str) -> str`
  - 规则（按序）：① `agents` 只有 1 个 → 该 agent（hub 与单 agent 消费者）；② `basename(repo_root)` 大小写不敏感匹配
    `agents[].clone_dir` → 该 agent 的 `name`；③ 无匹配 → 抛 `TopologyError`。
  - **不再读 git 分支**：身份 = "哪个 clone 的 hook 在执行"，与检出哪个分支无关（关闭 `git checkout master` 升格旁路）；
    不调 git 也就没有"git 故障时放行"的理由。
  - 分支只作一致性提示：session-context 在 clone 当前分支 ≠ 该 agent 配置的 `branch` 时打 `[WARN]`，不改变身份。
- **失败语义（改 fail-open 为 fail-closed）**：guard 捕获 `TopologyError` → 对写操作 `block()`，诊断写明
  "身份无法解析：<原因>；运行 `governance-core doctor`"；`~/.claude/` 写入照旧豁免。非写操作 / 只读 hook
  （session-context、merge-audit）只 `[WARN]`、不阻断。
- **调用方传参**：guard 一律传自身 `_REPO_ROOT`（hook 文件所在 clone）；scope-guard 修正为同样传参；
  集中引用的 session-context 传会话 root（`CLAUDE_PROJECT_DIR`，缺失则 cwd 的 git toplevel）。
- **tools 复用同一实现**：`proposal_lib.detect_agent()` / `regen_constitution.detect_role()` 通过 `importlib` 按路径加载
  `<REPO_ROOT>/.claude/hooks/_guard_common.py` 的 `resolve_agent`；只维护一份实现。
- **跨仓库模式（F7）**：`_guard_common.sibling_clone_paths(repo_root) -> list[str]` = `dirname(repo_root)` 下每个
  `agents[].clone_dir`（排除自身）的规范化绝对路径（小写、`/`）。scope-guard L1 改为匹配这些绝对路径前缀
  及其 POSIX 盘符形式（`/c/...`），不再依赖 `install_root` 目录名。
- **F8 收窄**：非 core 对 `.claude/hooks/**`、`.claude/settings.json`、`.claude/settings.local.json` 的 Edit/Write → block；
  `.claude/` 其余（skills/learned、agent memory 等）照旧放行。
- **F2 installer**：`_render_clauses` 返回值拆成 `(managed, seeded)`；混合条款首次渲染归 `seeded`，**不进**
  `installed_files.json`（从诞生起即 business-owned）。`_prune_stale` 对 `.governance/clauses/<MIXED_CLAUSES>` 跳过并
  `[prune] released to business ownership`（一次性迁移：已登记的消费者升级后自然从清单脱落，与 P-0075 同模式）。
  执行者：`governance-core install` / `upgrade` CLI。
- **F3 installer**：`_ensure_boundary_anchor(project_root, config)`：当 `len(agents) > 1` 且 `shared_state_root` 的父目录 ==
  `project_root` 的父目录时，幂等确保 `.claude/settings.json` 含 `"projectRoot": "../"`（保留其他键；与
  `_configure_gitattributes` 同模式，不进清单）。单 agent / 非标准布局 → 不写。执行者：installer；mab `expand` 无需再处理。
- **F4 installer**：`constitution/total.md` **不存在**时，从 `governance_core/templates/constitution_total.md` 渲染
  （仪式词、项目名、agent 列表替换；每条通用条款一节"精简陈述 + `.governance/clauses/art_*.md` 指针"，
  末尾"项目条款"占位），随后调 `regen_constitution` 生成 `CLAUDE.md`。已存在则不动（session-context 的 STALE 检查照旧提示）。
- **F9 installer + check_scope**：
  - 首次 install 时，对每个非 core agent，若 `agent_rules/<agent>.allow.txt` 不存在，写一份只含格式说明注释、无规则的种子
    （语义仍是 deny-all，与"文件不存在"一致；seed-once、不进清单、归项目所有）。core 不种子化。
  - `check_scope.py`：`--agent` == `core_agent_name` → `[OK]`（与 guard 一致）；非 core 缺 allow 文件 → exit 1 并提示
    "创建 `agent_rules/<agent>.allow.txt`"。
  - `governance_core/templates/pre-commit`（python 脚本）：`resolve_agent` 取身份 → `check_scope.py --agent <a> --staged-only`
    → `check_constitution_change.py`；任一非 0 即拒绝提交。installer 写入 `.git/hooks/pre-commit`（per-clone、不进 git）：
    不存在则写入；已存在且带本包标记行则更新；已存在且非本包生成 → 不覆盖，doctor `[WARN]`。
- **F10 installer**：`.gitignore` 里维护一个带起止标记的受管块（`# >>> governance-core runtime >>>` … `# <<< ... <<<`），
  只含运行时产物：`/.claude/cache/`、`/.claude/skills/learned/.usage.json`、`/.claude/hooks/.direction_check_ts`、`/audit/`、
  `/.governance/installed_files.json`、`/.governance/candidate-outbox/`。幂等（块内容按包版本整体替换，块外不动）。
  已被 git 跟踪的运行时文件不自动 `git rm --cached`；doctor `[WARN]` 列出并给出命令。
- **doctor**：新增检查"本 clone 身份可解析"（`resolve_agent(project_root)` 不抛）+ 多 clone 时 `projectRoot` 锚存在 +
  非 core agent 的 allow list 为空时 `[WARN]` + pre-commit 是否为本包版本。

### Field Dictionary

| field | type | meaning | producer | consumer | constraints / allowed values |
|-------|------|---------|----------|----------|------------------------------|
| `agents[].name` | str | agent 身份 | owner（install `--config-overrides`）| `resolve_agent` | 唯一；N/A contracts/ —— config schema 现无契约文件，由 `installer.DEFAULT_CONFIG` 定义（见 Open Questions Q4）|
| `agents[].clone_dir` | str | clone 目录名，身份锚 | owner / mab | `resolve_agent`、`sibling_clone_paths` | 唯一；大小写不敏感比较；同上 |
| `agents[].branch` | str | 该 agent 的工作分支 | owner / mab | session-context 一致性提示 | 不再参与身份判定 |
| `core_agent_name` | str | 拥有治理权限的 agent | owner | 所有 guard 的 core 判定 | 必须 ∈ `agents[].name` |
| `projectRoot` | str | 会话边界锚（`.claude/settings.json`）| installer（F3）| `derive_session_boundary.py` | 固定 `"../"`；N/A contracts/ —— session-boundary-guard 的既有约定 |
| `installed_files.json` `files[]` | list | install-managed 成员与基线 | installer | `_capture_drift`、`_prune_stale` | 不再包含 `MIXED_CLAUSES`；N/A contracts/ —— P-0065 Phase 2 内部格式，schema 不变 |
| `agent_rules/<agent>.allow.txt` | text | 非 core agent 的可写路径前缀 | installer 种子 → 项目 core 维护 | edit-write-guard L2、`check_scope.py` | 每行一个前缀，`#` 注释；格式沿用现有 `_load_allow_rules`，N/A contracts/ —— 现无契约文件 |
| `.gitignore` 受管块 | text | 运行时产物忽略规则 | installer | git | 仅改起止标记之间；N/A contracts/ —— 安装产物约定 |

### Flow

```
config.json(agents, core_agent_name)
   -> _guard_common.load_topology(repo_root)        [TopologyError -> fail-closed block on writes]
   -> resolve_agent(repo_root = hook's own clone)   -> agent name
   -> guards: agent == core_agent_name ? bypass L1-L4 : allow-list / cross-repo / .claude self-protect
   -> tools: proposal_lib -> shared_state/proposals/<agent>/ ; regen_constitution -> constitution/agent.md variant

install/upgrade:
   render clauses -> (managed -> installed_files.json) + (seeded MIXED -> not recorded)
   prune: old manifest - new managed - MIXED_CLAUSES - STALE_PRUNE_EXEMPT
   multi-clone -> ensure .claude/settings.json projectRoot "../"
   total.md absent -> seed template -> regen CLAUDE.md
   non-core agent without allow.txt -> seed (deny-all, commented)
   .git/hooks/pre-commit -> resolve_agent -> check_scope --staged-only -> check_constitution_change
   .gitignore -> replace managed runtime block
```

## Non-Goals

- **mab（multi-agent-template 仓库）侧修改**，另开 mab 会话处理，本提案只记录交接：
  `new` 不带 `--auth-code`（已知）；模板 `CLAUDE.md` / `constitution/total.md` 停止提供与 gc regen 模型冲突的版本
  （由 F4 的 gc 种子接管）；`install_root` 语义与 gc 对齐（F7 的 gc 修复不再依赖它，但 config 仍应一致）。
- **授权码进 git**：`.governance/config.json`（含 `authorization.auth_code`）当前是 committed 文件，消费者推到公开远端即泄露。
  需要把凭据拆到 gitignored 文件，涉及 P-0065 授权门与 hub 自身 Art.2，单独提案。
- **Bash 层的 guard 自改防护**：业务 agent 用 `cp` / `sed -i` 等 shell 写 `.claude/hooks/` 仍取决于 command-guard 的 deny 规则；
  本提案只关闭 Edit/Write 这条直接路径（F8）。
- 为 deva-vani 编写其业务 agent 的 `agent_rules/*.allow.txt`（消费者自有，由其 core 负责）。

## Open Questions

- Q1 发布切分：A+B+E（安全 + 数据丢失 + 小修）先发 0.46.0，C+D+F（边界锚、宪法种子、提交门禁）再发 0.47.0；还是一次发？
  **倾向分两次**：安全修复不等模板设计。
- Q2 F4 对"已存在的 stub total.md"是否也种子化？**倾向不碰**（只在缺失时种子化）：stub 识别靠内容特征不可靠，且 deva-vani
  已把项目条款写进自己的 `total.md`；doctor 对"total.md 不含任何 `.governance/clauses/` 指针"给 `[WARN]`。
- Q3 `.role` 退役还是保留为覆盖手段？**倾向退役**：身份唯一来源是 config + clone 目录；再留一个可被 agent 自己改写的文件
  等于多一个旁路。遗留 `.role` 文件无害（不再被读）。
- Q4 是否借此为 `.governance/config.json` 立契约 `contracts/governance_config_schema.md`？**倾向 defer**：本提案只依赖
  已有字段，立契约单独做。
- Q5 `.claude/settings.local.json` 进不进 F10 的受管忽略块？它由 installer 按 clone 重新生成、sync_infra 按 clone 改写，
  按 Claude Code 惯例 `*.local.json` 不共享。**倾向进**；代价是 clone 之间不再经 git 同步它（本来也不该靠 git 同步）。

## Alternatives & Rationale

- **身份来源**
  - (a) 保留分支判定，只把前缀表改为从 config `agents[].branch` 推导（deva-vani 补丁的后半）。可修 F1 的硬编码，
    但保留 `git checkout master` 升格旁路，且 git 故障仍需兜底策略。
  - (b) `.role` 文件。可被 agent 自己 Edit（`.role` 在 repo 根），且 F5 显示它连 gitignore 都没落实。
  - (c) **clone 目录名 → config `agents[].clone_dir`（选用）**：目录名不随分支变，agent 无法在会话内改名自己的 clone；
    config 已是 `_load_cross_repo_patterns` 的数据源，单一来源。代价：clone 目录被改名需同步 config（doctor 检出）。
- **未知身份的兜底**：fail-open（现状，"不认识就当 core"）把配置错误放大成全权限；fail-closed 最坏是"写操作被拦 + 明确诊断"，
  且新方案不依赖 git，误拦面只剩"config 缺失 / clone 未登记"——这本身就是 doctor 应报的坏安装。选 fail-closed。
- **混合条款（F2）**：deva-vani 方案 A（不进清单）vs 方案 B（prune 跳过但仍登记）。B 让项目自有文件持续被 drift 捕获并 uplink，
  选 A，并加一次性迁移覆盖已登记的消费者。
- **F3 由谁生成**：mab `expand`（deva-vani 建议）vs gc installer。放 installer：所有消费者（含不用 mab 的）走同一路径（Art.8），
  mab 自动受益。
- **tools 复用 hook 实现**：放 `governance_core/` 模块让 hook import 会违反 runtime-import-discipline（fail-closed gate 须自包含）；
  在 tools 里复制一份会再造重复实现。选"tools 按路径加载 hook 的 `_guard_common`"，并由 token grep gate 防回潮。

## Guardrails

- edit-write-guard / scope-guard / data-source-guard：本提案直接修改它们；每个 phase 后 `governance-core upgrade --project-root .`
  重装，在 hub 自身 dogfood（hub 为单 agent → 规则 ①，身份 = core，行为不变）。
- session-boundary-guard：不改（user-global 副本不受 upgrade 影响，见记忆 session-boundary-guard-enforced-from-user-global）。
- command-guard：commit message 含被拒短语时用 `-F`。
- 多 clone 行为（F1/F3/F7/F8）hub 无法 dogfood（单 agent），以单元测试 + deva-vani 实测验收。

## Phases

### Phase 0: Governance bootstrap

- N/A — 不改宪法（`constitution/` / `CLAUDE.md`）；条款文本仅 `art_12` 可能补一句"身份由 clone 目录 + config 决定"，属包源条款编辑，随 Phase A 提交。

### Phase A: Config-derived identity + guard hardening（F1、F7、F8）

- Deliverables：`_guard_common.load_topology / resolve_agent / sibling_clone_paths`；5 个 hook + 2 个 tool 改用之；scope-guard 传 `_REPO_ROOT`；
  F8 收窄；docstring 去业务化；doctor 身份检查；`test_agent_identity.py`。
- Validation：deva-vani 形状 fixture（4 agent，嵌套布局）：每个 clone 解析为自身 agent；业务 clone 检出 master 仍是业务身份；
  未登记 clone / config 缺失 → 写操作 block；hub 单 agent → core；scope-guard 对兄弟 clone 绝对路径（含 `/c/...` 形式）block；
  非 core Edit `.claude/hooks/edit-write-guard.py` → block。
- Exit criteria：Approval Criteria 1–4 通过。

### Phase B: Mixed clauses ownership（F2）

- Deliverables：`_render_clauses` 拆 `managed / seeded`；`_prune_stale` 迁移跳过；`test_installer_mixed_clauses.py`。
- Validation：空目录连续 install 两次 → 7 条 `MIXED_CLAUSES` 都在、均不在清单；用"旧清单登记了 7 条"的 fixture upgrade → 文件保留；
  已删除的 7 条在下次 install 被重新种子化。
- Exit criteria：Approval Criteria 5 通过。

### Phase E: Small fixes（F5、F6、F10）

- Deliverables：session-context 条目解析改用 `^### \d{4}-\d{2}-\d{2}`（与 `rotate_state._ENTRY_RE` 一致）；`.role` 退役
  （`regen_constitution` 不再读；`docs/core-manual.md:106` 更新）；`.gitignore` 受管运行时块 + doctor 已跟踪运行时文件 WARN；
  `test_session_context_state.py`、`test_installer_gitignore_block.py`。
- Validation：只有模板注释的 STATE.md → `(no recent entries)`；hub 实际 SessionStart 不再列出模板行；
  `.gitignore` 连续 install 两次只有一个受管块、块外内容逐字节不变。
- Exit criteria：Approval Criteria 6、9 通过。→ **发布 0.46.0**（需人工确认，core-A3）。

### Phase C: Multi-clone boundary anchor（F3，依赖 Phase A 已发布）

- Deliverables：`installer._ensure_boundary_anchor`；doctor 锚检查；`test_installer_topology_anchor.py`；core-manual 更新。
- Validation：多 clone fixture → settings.json 含 `projectRoot: "../"`，已有键保留，重复 install 幂等；单 agent / 非标准布局 → 不写。
- Exit criteria：Approval Criteria 7 通过。

### Phase D: Constitution seed（F4）

- Deliverables：`governance_core/templates/constitution_total.md` + package-data；installer 种子化 + regen；doctor 指针 WARN。
- Validation：新项目 install 后 `regen_constitution.py --check` → `[OK]`；`CLAUDE.md` 含每条通用条款的指针；已有 total.md 不被改动；
  wheel 含模板文件。
- Exit criteria：Approval Criteria 8 通过。

### Phase F: Commit gate（F9）

- Deliverables：installer 种子化非 core `allow.txt`；`check_scope.py` core 直通 + 缺文件提示；`templates/pre-commit` + installer 安装；
  doctor 的 allow 为空 / pre-commit 版本检查；`test_installer_commit_gate.py`。
- Validation：多 clone fixture 下业务 agent 提交越界文件 → pre-commit 拒绝；core 提交任意文件 → 通过；修改宪法源不经 regen → 拒绝；
  已有非本包 pre-commit → 不覆盖、doctor WARN。
- Exit criteria：Approval Criteria 10 通过。→ **发布 0.47.0**（需人工确认）。

## Approval Criteria

> Each item pairs a plain-language acceptance with ONE discriminating check token
> (`cmd: <exit 0 = pass>` / `agent-rubric: <ref>` / `human-verify: <sentence>`; see
> contracts/proposal_gate_schema.md). An item with no check token is prose, not an
> acceptance signal.

- [ ] Every Field Dictionary entry names its governing `contracts/` file (or is N/A) — human-verify: each field row cites a contracts/ file or an explicit N/A reason
- [ ] Every user-facing capability / mutation has a named realizer — human-verify: installer / hooks / doctor named for each change; mab items deferred in Non-Goals
- [ ] All Open Questions are resolved or explicitly deferred — human-verify: owner rules on Q1–Q4
- [ ] 1. 身份解析单测全过（deva-vani 形状、master 旁路、未登记 fail-closed、hub 单 agent）— cmd: python -m pytest tools/test_agent_identity.py -q
- [ ] 2. 包源里不再有写死的上游角色分支 — cmd: bash -c "! git grep -nE 'feature/(trade|models|simu|rules|research)' -- governance_core ':!governance_core/tools/test_*' ':!governance_core/tools/migrate_proposals_to_shared_state.py'"
- [ ] 3. hub 重装后 doctor 通过、行为不变 — cmd: governance-core doctor --project-root .
- [ ] 4. deva-vani 业务 clone 实测：越权 Edit、兄弟 clone 的 Bash 写、改自身 guard 均被拦 — human-verify: deva-vani core 在 agent-platform 会话中复现 3 个场景均 BLOCKED 并回报
- [ ] 5. 连续 install 两次混合条款全在 — cmd: python -m pytest tools/test_installer_mixed_clauses.py -q
- [ ] 6. STATE 模板注释不再被当作条目 — cmd: python -m pytest tools/test_session_context_state.py -q
- [ ] 7. 多 clone 安装生成幂等的 projectRoot 锚 — cmd: python -m pytest tools/test_installer_topology_anchor.py -q
- [ ] 8. 新项目 install 后宪法不 STALE 且含条款指针 — cmd: python -m pytest tools/test_installer_constitution_seed.py -q
- [ ] 9. `.gitignore` 受管块幂等、块外不动 — cmd: python -m pytest tools/test_installer_gitignore_block.py -q
- [ ] 10. pre-commit 对业务 agent 越界提交拒绝、对 core 放行 — cmd: python -m pytest tools/test_installer_commit_gate.py -q

## Validation Plan

- 每个 phase：改包源 → `governance-core upgrade --project-root .` → 跑新增测试 + 全量 `tools/test_*.py`（pytest 风格 + script 风格分别跑）。
- 发布前：`rm -r build` → `python -m build --wheel` → 断言 wheel 只含 `governance_core*`、含新模板、不含 `maintainer/`。
- 发布后：通知 deva-vani core（写 `artifacts/deva-vani/` + 会话消息），由其 `/upgrade` 四个 clone 并完成 Approval Criteria 4 的实测。

## Rollback / Recovery

- Phase A：回退到 0.45.1 恢复分支判定（即 fail-open 现状）；若 fail-closed 误拦，消费者可临时 `CLAUDE_BOUNDARY_OVERRIDE` 无效——
  正确恢复是修 config 的 `clone_dir` 或 `pip install governance-core==0.45.1 && governance-core upgrade`。
- Phase B：迁移只"少删"，回退无数据风险；被误删的条款可从 outbox drift candidate 或 git 历史恢复。
- Phase C：删除 `.claude/settings.json` 的 `projectRoot` 键即回到 clone 级边界。
- Phase D：只在 total.md 缺失时写入，回退 = 删除种子文件后重新 regen。

## Risks

- **fail-closed 误拦现有消费者**（中 / 高）：任一消费者的 clone 目录名与 config `clone_dir` 不一致，升级后写操作被拦。
  缓解：doctor 在 upgrade 末尾运行并给出精确修复提示；release notes 显式说明；已知多 clone 消费者只有 deva-vani（已核对一致）。
- **测试 fixture 需带 config**（低）：现有 hook 测试若在无 config 的临时目录运行会因 fail-closed 失败；随 Phase A 一并修 fixture。
- **tools 按路径加载 hook 模块**（低）：hook 被删 / 未安装时 tools 失败；doctor 已检查 hook 存在。
- **F3 在 A 未发布时单独上线**（高）：会把业务 agent 的写边界扩到整个项目。缓解：C 明确依赖 A，且排在下一次发布。
- **A 上线后业务 agent 暂时什么都写不了**（确定发生 / 中）：身份识别正确后，没有 allow.txt 的业务 agent 是 deny-all。
  这是正确行为，但 deva-vani 须在 `/upgrade` 到 0.46.0 **之前**由其 core 写好 `agent_rules/{platform,experience,content}.allow.txt`。
  缓解：发布通知里写明；doctor 对空 allow list `[WARN]`。
- **pre-commit 覆盖消费者已有的 hook**（低）：只覆盖带本包标记的文件，其余只 WARN。

## State Log

- 2026-11-05: draft created by core agent (P-0129)
- 2026-11-05: draft → pending (submit for review)
- 2026-11-05: pending → approved (owner: 批准 (2026-11-05). Open Questions resolved by stated defaults: Q1 two releases (A+B+E -> 0.46.0; C+D+F -> 0.47.0); Q2 seed total.md only when absent; Q3 retire .role; Q4 defer config contract; Q5 ignore settings.local.json)
- 2026-11-05: approved → in-progress
- 2026-11-05: in-progress → implemented (acceptance: deva-vani on 0.48.4 (agent-platform session) -- item 1 out-of-scope Write BLOCKED (edit-write-guard stdin probe exit 2; in-session the classify gate fired first), item 2 Bash write to sibling clone BLOCKED (scope-guard), item 3 edit own guard BLOCKED (guard self-protection), item 4 out-of-scope commit rejected (pre-commit, 0.48.1). Commits: f2c881e dd83b1d a188f3f 9b88ea5 (0.46.0); 86eef83 dfc8fe2 c7a6522 (0.47.0); fixes dc49b0b (0.48.1 merge/staged gate), 8921f45 (0.48.2 validators), e5e3dfb (0.48.3 pre-merge-commit gate). As-built deviations: core clone excluded from F7 sibling patterns (business clones legitimately reference core; Edit/Write into core still blocked by path prefix); tracked runtime files reported by doctor as a note, not a warning; seed templates live in default_config/; check_constitution_change.py deliberately not wired into pre-commit. Follow-ups outside scope: merge-import source attribution (P-0131, done), edit-write-guard shared_state/ allows other agents' proposal dirs (reported by deva-vani, open).)
