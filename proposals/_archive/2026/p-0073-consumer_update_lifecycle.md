---
id: P-0073
agent: core
status: implemented
created: 2026-05-19
approved_at: 2026-05-19
started_at: 2026-05-19
implemented_in: 4315632
implemented_at: 2026-05-19
owner: core
---

# Proposal P-0073: Consumer update lifecycle -- update-available notification + upgrade preview

## Trigger

P-0072 端到端演示后的讨论(2026-05-19)暴露消费者 **update 生命周期**的两个
缺口:

**A. 没有"更新可用"通知。** 消费者更新是两步 —— `pip install -U
governance-core`(拿新 wheel)+ `governance-core upgrade --project-root .`
(从新包重新物化自治层)。但**没有任何东西告诉 owner 有新版** —— 现有
SessionStart hook(`session-context` / `candidate-reminder`)都不查 PyPI;
`auth-guard` 拉的撤销源只带撤销项。结果:owner 可能永远想不起来 update,
hub 的改进永远到不了消费者。

**B. upgrade 无预览。** `upgrade` 是 copy-based:覆盖公共层(install-managed
文件)、保留 config、保留 owner 自己的 hook 组、从不碰业务层 —— 所以**没有
merge 冲突**。但 owner 升级前**看不见**会覆盖什么、哪些原地改过的公共层
文件会被 drift 捕获、版本跳了几个 minor。跨多个 minor 版本跳变时,新公共层
与业务层的旧假设可能 version-skew,而 owner 是闭眼覆盖。

用户(2026-05-19)指示立项修这两条。批准前的场景讨论(大版本跨度 + 原地
个性化公共层 `a→a2`、新增重叠机制 `x`,4 个版本后上游已是 `a8`)进一步
明确:Phase 2 的 `--dry-run` 必须对**每个 drift 文件输出真实 unified diff**
(owner 版 vs 上游版)—— 否则 owner 仍看不清 `a2`-vs-`a8` 究竟差在哪,
"预览"形同虚设。讨论进一步引出 Phase 3:文件内容 diff 仍需**语义**判断
(owner 新增的机制 `x` 是否与上游增量 `y` 冲突)—— 而发起 `upgrade` 的
agent 本身就是 LLM,故新增一个 `/upgrade` skill,指导 agent 读 dry-run
输出做语义冲突审查(advisory)。为 PROPOSAL_REQUIRED:新增 hook、改
`installer.py`/CLI、新增 skill、多 phase、引入网络读取。

## Scope

### In-Scope

1. **Phase 1 — update-available 通知 hook。** 新增 SessionStart hook,比对
   自治层记录的 `source_version`(`.governance/installed_files.json`)与
   PyPI 最新版(PyPI JSON API);有新版 → 启动 banner 提示并给出两步更新
   命令。TTL 缓存(temp dir,与撤销源同套路);PyPI 不可达 → 静默;hub
   角色 → 静默(GC 自身 editable 安装恒为最新,无 PyPI 更新概念)。注册进
   `hooks/hooks_manifest.json`(install/upgrade 自动 wiring)。
2. **Phase 2 — `governance-core upgrade --dry-run` 预览 + 逐文件 diff +
   版本跳变警示。** `installer.py` 加 dry-run 模式:跑完 install 集 / drift
   捕获 / prune 的**计算**但不写盘,报告将覆盖 / drift 捕获 / prune 的文件
   数与清单;**对每个 drift 文件输出真实 unified diff** —— owner 原地改过的
   当前内容(如 `a2`)对比即将覆盖的上游版本(如 `a8`),让 owner 看清自己
   的个性化与上游数个版本的演进究竟差在哪;附版本 delta(`source_version`
   → 包版本,跨几个 minor),跨 minor 时附"升级前查 `contracts/` breaking
   变更"提示;并枚举**本地新增文件**(autonomy 区域内不在 manifest 的文件,
   即 owner 加的 `x` 这类)作为"待与增量比对"清单。`cli.py` 加 `upgrade
   --dry-run` 标志。
3. **Phase 3 — `/upgrade` skill:agent 驱动的升级编排 + 语义冲突审查。**
   新增 command skill,把"升级"从裸 CLI 变成编排:跑 `upgrade --dry-run`
   → **指导 agent**(发起 upgrade 的 agent 本身即 LLM)读 dry-run 输出
   (增量上游变更带 diff + 本地新增文件清单)逐项做**语义冲突**判断(如
   owner 的 `x` 与上游 `y` 是否冲突)→ 把冲突点 / 版本跳变 / 覆盖面汇报
   owner → owner 确认后再跑真实 `upgrade`。语义审查是 **advisory**(尽力
   而为、只警示不阻断);`installer` 子进程**不**调任何模型,"LLM 能力"
   来自 agent 自身;agent 不在场的纯手工升级跳过此层,结构层不受影响。

### Out-of-Scope

- **不**自动 upgrade —— 通知只是让 owner 知道,升不升级是 owner 的决定;
  两步命令仍由 owner 主动执行。
- 语义冲突审查(Phase 3)是 **advisory,非 sound 检测器** —— 由 agent
  (LLM)读 dry-run 输出做尽力判断,会漏报会误报;它**只警示、不阻断**升级,
  owner 据此决定。`installer` 子进程**不**调任何模型(无 API key、无网络/
  计费依赖);"LLM 能力"来自发起 upgrade 的 agent 自身。agent 不在场的纯
  手工升级跳过语义层 —— 结构层(diff / drift / 版本警示)照常。
- **不**改 copy-based upgrade 模型、**不**做 3-way merge —— `--dry-run` 是
  预览(base/ours/theirs 三方里只逐文件展示 ours-vs-theirs 的 diff),不是
  合并引擎;`upgrade` 仍是覆盖公共层 / 不碰业务层。`a2` 如何揉进 `a8` 由
  owner 据 diff 人工决定(或把 `a2` 的 drift 候选 uplink,交 hub 调和)。

## Non-Goals

参见 Scope.Out-of-Scope。诚实边界:通知 hook 与 `--dry-run` 都是消费者本地
文件,owner 可以无视通知、删 hook。本提案不追求"强制升级" —— 升级本就该是
owner 的选择;目标是让"有更新可用"和"升级会改什么"从**不可见**变成**每次
session 启动可见 / 升级前可预览**,而非一个静默黑箱。与 P-0071/P-0072
Non-Goals 同源:enforcement 跑在本地,提供可见性而非强制。

## Guardrails

| Guard | 适用 | 关注点 |
|-------|------|--------|
| `edit-write-guard` | 全期 | 新 hook / `installer.py` / `cli.py` 是 install-managed —— 改 `governance_core/` 包源,不碰自治层副本(宪法第十一条) |
| 网络读取审查 | Phase 1 | update hook 查 PyPI JSON API 用 stdlib `urllib`、短超时、TTL 缓存、不新增依赖;不可达 fail-silent(SessionStart hook 绝不阻断启动) |
| `command-guard` | 全期 | `governance-core upgrade --dry-run` dogfood、构建调用前明示 |
| `boundary-guard` | 全期 | 在 governance-core 自身 self-hosted session 执行 —— 改包源 in-boundary |

## Phases

### Phase 1: update-available 通知 SessionStart hook

- Deliverables:
  - 新增 SessionStart hook(如 `update-reminder.py`):读
    `.governance/installed_files.json` 的 `source_version`,查 PyPI JSON
    API 取最新版,版本元组比较;有新版 → 启动 banner 报
    "governance-core X 可用(你在 Y)—— pip install -U governance-core &&
    governance-core upgrade --project-root ."。TTL 缓存于 temp dir;PyPI
    不可达 / 任何异常 → 静默 exit 0;hub(`consumer_id==governance-core`)
    → 静默。
  - 注册进 `hooks/hooks_manifest.json` → SessionStart。
  - gc 版本 bump;docs(`core-manual` §9 或新节:消费者更新流程)。
- Validation:构造"自治层 source_version 低于 PyPI 最新版"→ 验 hook 报提示;
  版本相等 → 静默;PyPI 不可达(mock / 坏 URL)→ 静默;hub → 静默。版本
  比较单测(0.3.0 < 0.4.0、相等、跨 minor)。
- Exit criteria:消费者每次 session 启动,若有新版即在 banner 看到 + 拿到
  确切两步命令;gc 自身静默。

### Phase 2: `upgrade --dry-run` 预览 + 逐文件 diff + 版本跳变警示

- Deliverables:
  - `installer.py` 加 dry-run 模式:计算 install 集 / `_capture_drift` /
    `_prune_stale` 但**不写盘**;报告将覆盖 / drift 捕获 / prune 的文件数与
    清单、`source_version`→包版本的 delta、跨几个 minor。
  - **逐 drift 文件 unified diff**:对每个被 `_capture_drift` 判定为本地
    改过的 install-managed 文件,输出其当前(个性化)内容与即将覆盖的上游
    版本之间的 unified diff(diffstat 摘要 + diff 正文,`difflib`);owner
    据此看清个性化与上游演进的差异,自行决定如何调和。
  - **本地新增文件枚举**:列出 autonomy 区域内不在 manifest 的文件(owner
    自行新增的 `x` 这类),作为 Phase 3 语义审查的输入。
  - `cli.py` `upgrade` 加 `--dry-run` 标志。
  - 跨 minor 版本时附"升级前查 `contracts/` breaking 变更"提示。
  - gc 版本 bump;docs。
- Validation:自托管 gc 跑 `governance-core upgrade --dry-run` —— 验报告
  准确(覆盖/drift/prune 集与真实 upgrade 一致)、不写盘(`git status`
  不变);探针文件 —— 原地改一个公共层文件 → 验 dry-run 既报它会被 drift
  捕获,也输出该文件当前内容 vs 上游版本的 unified diff;diff 正确性单测
  (`difflib` 对已知两版输出预期 diff)。
- Exit criteria:`upgrade --dry-run` 让 owner 升级前看清覆盖面、**每个被改过
  文件的具体 diff**、版本跳变;真实 `upgrade` 行为不变。

### Phase 3: `/upgrade` skill — agent 驱动的升级编排 + 语义冲突审查

- Deliverables:
  - 新增 `governance_core/commands/upgrade.md` command skill —— 编排
    "`governance-core upgrade --dry-run` → agent 读输出 → 语义冲突审查 →
    汇报 owner → owner 确认 → 真实 `upgrade`"。
  - skill 明确指导 agent:对 dry-run 列出的本地新增文件 + 原地 drift 文件,
    逐项与增量上游变更做**语义冲突**判断,产出 advisory 警示(冲突点 +
    理由),**不阻断**;owner 确认门置于真实 `upgrade` 之前。
  - Phase 1 的 update-reminder hook 提示语改为指向 `/upgrade`。
  - gc 版本 bump;docs(`core-manual` 消费者更新流程一节)。
- Validation:`/upgrade` skill 被 registry 发现;自托管 gc 走 `/upgrade` ——
  验编排顺序(dry-run 先于真实 upgrade、owner 确认门在中间);构造一个本地
  新增文件 + 一个相关上游增量,验 skill 引导 agent 产出语义冲突 advisory;
  无重叠时干净通过。语义审查质量属 agent 判断,不做单测(与其它 skill 一致
  —— skill 是对 agent 的指令,非可单测代码)。
- Exit criteria:`/upgrade` 把升级变成"预览 → 语义审查 → 确认 → 应用";
  语义审查作为 advisory 层,agent 在场即生效、不在场结构层照常。

## Approval Criteria

User 批准前应能确认:

1. Phase 1 通知 hook 与 `candidate-reminder`(P-0072)同套路:SessionStart、
   TTL 缓存、不可达静默、hub 静默、绝不阻断 session 启动。
2. 通知只告知、不自动升级;两步命令仍由 owner 主动执行。
3. `upgrade --dry-run` 是纯预览(不写盘),**对每个 drift 文件输出真实
   unified diff**(owner 版 vs 上游版);真实 `upgrade` 的 copy-based 覆盖
   模型不变;业务层 / config / owner 自己的 hook 组一如既往不受影响。
4. 诚实边界:`--dry-run` 给出文件**内容** diff、不做 3-way merge;Phase 3
   的语义审查是 **advisory**(agent 尽力判断、会漏报误报、只警示不阻断);
   `installer` 不调模型,LLM 能力来自 agent 自身;不强制升级、拦不住本地删
   hook —— 均写入 Non-Goals。
5. Phase 3 的"LLM 语义审查"是一个 **skill**(指导 agent),不是给 installer
   外挂模型;纯手工升级优雅降级(跳过语义层,结构层照常)。
6. 3 phase,各自独立可交付、可单独 revert。

## Validation Plan

- Phase 1:版本比较单测;hook 四态(有新版报 / 相等静默 / PyPI 不可达静默 /
  hub 静默)—— 用临时 repo + 子进程驱动 hook,PyPI 查询可注入坏 URL 验静默。
- Phase 2:自托管 gc `upgrade --dry-run` 验报告与真实 upgrade 一致、不写盘
  (`git status` 不变);探针文件 —— 原地改一个公共层文件 → 验 dry-run 既
  报它会被 drift 捕获、也输出当前 vs 上游的 unified diff;`difflib` diff
  正确性单测。
- Phase 3:`/upgrade` skill 被 registry 发现;dogfood 走一遍验编排顺序与
  owner 确认门;构造本地新增文件 + 相关上游增量验语义 advisory 产出。
- 全程:`build` 验包隔离;`upgrade` / `doctor` exit 0。

## Rollback / Recovery

- **Phase 1**:新 hook 源 revert + `hooks_manifest.json` 移除条目 →
  `upgrade` 自动解除 wiring。
- **Phase 2**:`installer.py` dry-run 分支 + `cli.py` 标志 revert → 回到无
  预览的 `upgrade`。
- **Phase 3**:删 `commands/upgrade.md` skill + revert hook 提示语 → 升级
  回到裸 `governance-core upgrade`(无语义审查编排)。
- 每 phase 独立 commit,可逐 phase revert;最坏回到本提案前(无通知、无预览)。

## Risks

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| PyPI 查询拖慢 session 启动 | 中 | 中 | TTL 缓存(每数小时至多一查)、短超时、不可达立即静默 |
| dry-run 报告与真实 upgrade 不一致 | 中 | 中 | dry-run 走与真实 upgrade **同一**计算路径,只在写盘处分叉(宪法第八条:测试/生产同路径);Phase 2 显式验证两者覆盖集一致 |
| owner 无视通知 / 删 hook | 中 | 低 | 无法也不该技术强制(升级是 owner 选择);hook 持续可见性是设计上限(Non-Goals) |
| 版本元组比较对非 X.Y.Z 串出错 | 低 | 低 | 发布版本恒为干净 X.Y.Z;解析失败 → 静默不报,不误导 |
| 语义审查漏报真冲突 / 误报假冲突 | 中 | 中 | 定位为 **advisory** 非 gate —— 只警示、owner 终判;结构层(diff / 版本警示)独立有效,不依赖语义层正确 |

## State Log

- 2026-05-19: draft created by core agent (P-0073)
- 2026-05-19: draft → pending (submit for review: consumer update lifecycle)
- 2026-05-19: pending → approved (user approval: 批准 P-0073 (3-phase, amended))
- 2026-05-19: approved → in-progress (Phase 1 started)
- 2026-05-19: in-progress → implemented
