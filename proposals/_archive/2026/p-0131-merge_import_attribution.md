---
id: P-0131
agent: core
status: implemented
created: 2026-11-05
approved_at: 2026-11-05
started_at: 2026-11-05
implemented_in: 76fff4c
implemented_at: 2026-11-05
owner: core
---

# Proposal P-0131: Attribute merge imports to their source commits in the commit gate

## Trigger

实施 0.48.3（自动 merge 提交门禁）时发现：提交门禁对 merge 提交的放行条件只看"暂存内容是否与 MERGE_HEAD 相同"，不看
MERGE_HEAD 来自哪里。业务 agent 只要 fetch 并 merge **另一个业务 agent 的分支**，对方分支里的越界改动就会作为"merge 导入"
整体放行；scope-guard 也不限制 `git merge` / `git fetch`。owner 在 0.48.3 发布后要求起草本提案。

改的是提交门禁的放行规则（scope 规则、安全相关），影响所有多 clone 消费者的 merge 流程 → PROPOSAL_REQUIRED。
属 P-0129 F9（提交门禁）的后续；P-0129 仍 in-progress，但其已批准范围不含"按来源归属"，故单开。

## Current State (read, not assumed)

**放行规则不看来源**
- `governance_core/tools/check_scope.py:279-290`：`if violations and in_merge()` 时，凡 `same_as_merge_head(f) or
  same_as_master(f, args.staged_only)` 的越界文件都从 violations 中剔除，并打印 "[INFO] Merge detected: N scope-external
  file(s) identical to the merged-in commit (allowed)"。
- `check_scope.py:101-115` `same_as_merge_head()`：`git diff --cached --quiet MERGE_HEAD -- <path>`，只比内容。
- 合并来源无约束：`governance_core/hooks/scope-guard.py` 中 grep `merge|checkout|pull|fetch` 无匹配（Bash 层不拦 merge）。
- 结果：业务 clone 执行 `git fetch origin feature/content && git merge --no-commit origin/feature/content && git commit`，
  content 的越界改动（相对 platform 的 allow list）全部被当作 merge 导入放行。

**core 分支写死为 `master`，config 里的分支字段未被使用**
- `check_scope.py:65-84` `same_as_master()`：比较对象写死为本地 `master`（`git diff --cached --quiet master` /
  `master..HEAD`）。业务 clone 走 `/sync-repos` 时 merge 的是 `origin/master`，本地 `master` 往往陈旧
  （`governance_core/commands/sync-repos.md` Step 2：`git fetch origin master` + `git merge --no-ff --no-commit origin/master`）。
- 0.48.3 的 pre-merge-commit 路径（`check_scope.py:293-306`）同样只认本地 `master`：本地 master 陈旧时，sync 的自动 merge
  一律 `[DEFER]`。
- config 已有这两个字段：hub `.governance/config.json:8` `"core_branches": ["master"]`、`:19` `"upstream_branch": "origin/master"`；
  deva-vani `agent-core/.governance/config.json:8` `"core_branches": ["master", "main"]`、`:35` `"upstream_branch": "origin/master"`。
  installer 默认值 `governance_core/installer.py:154,160` 写入每个安装。
- 两个字段的唯一读取方是 `governance_core/config.py:100` `core_branches=tuple(raw["core_branches"])`（必填）与
  `:103` `upstream_branch=raw.get("upstream_branch", "origin/master")` —— 后者是 Art.4 禁止的 `.get(k, default)`。
  `GovernanceConfig.upstream_branch` 无任何调用方（grep `upstream_branch` 只命中 config.py / installer.py / 模板）。
- 门禁不能 import governance_core（pre-commit 用 PATH 上的 python 运行，该解释器未必装了包）：`check_scope.py:36-53`
  按路径加载 `_guard_common.py`，config 由 `_guard_common.load_topology()` 直接读 JSON。

**git 能提供的归属信息（本仓库实测，git 2.52.0）**
- merge 提交运行 pre-commit 时 MERGE_HEAD 已存在（0.48.1 起的前提）；自动 merge 的 pre-merge-commit 运行时 MERGE_HEAD 尚未写入
  （`artifacts/p0129/probe_pre_merge_commit.py`，0.48.3 已据此设计 DEFER）。
- `git log --format=... --name-only --diff-merges=dense-combined <MERGE_HEAD> ^HEAD ^<core refs>` 同时列出：普通提交改的文件，
  以及 merge 提交中**与所有父提交都不同**的文件（冲突解决结果、夹带改动）；`--no-merges` 列不出后者
  （`artifacts/p0129/dense_probe` 实测：merge 提交列出 a.txt（冲突解决）与 b.txt（夹带））。

**现有测试**
- `governance_core/tools/test_installer_commit_gate.py`：`_merge_fixture`（`--no-commit` 合并本地 master）、
  `_auto_merge_fixture`（0.48.3，合并 `core-next` 分支）—— 都没有"合并另一个业务 agent 的分支"或"本地 master 陈旧、
  合并 upstream"的用例。

## Scope

- `governance_core/tools/check_scope.py`：从 config 推导 core 引用；用"按来源提交归属"替换 merge 导入的整体豁免；
  `same_as_master` 改为与 core 引用比较；去掉剩余的 `"core"` 字面量（`:260`、`load_rules` 的 deny 跳过）改用 topology 的 core 名。
- `governance_core/config.py`：`upstream_branch` 改为可选字段（成员测试，缺失为 `None`），去掉 `.get` 默认值。
- `governance_core/tools/test_installer_commit_gate.py`：新增用例（见 Validation Plan）。
- 文档：`governance_core/commands/sync-repos.md`、`docs/core-manual.md`（seeded files / commit gate 段）、
  `governance_core/skills/verify-guard-fires-in-its-target-context.md`（归属规则一句）。
- 版本号 `pyproject.toml` / `governance_core/__init__.py`。

## Design & Contract

### Interfaces, I/O & Realization

所有判定都由 `tools/check_scope.py` 完成，经 installer 写入的 git hook stub 调用（pre-commit：`--staged-only`；
pre-merge-commit：`--merge-commit`）。没有新的 CLI 参数、hook 或文件。

- `load_core_refs(repo_root: Path) -> list[str]`（新，check_scope.py）
  - INPUT：`<repo_root>/.governance/config.json` 的 `core_branches`（必填，非空 `list[str]`）与 `upstream_branch`（可选，`str`）。
  - OUTPUT：按优先级排列、且在本 clone 中 `git rev-parse -q --verify <ref>^{commit}` 能解析的引用名：
    `upstream_branch` 在前，其后依次为 `core_branches`。解析不到的跳过。
  - 缺 `core_branches` / 类型不对 → `[FATAL]` exit 1（与 `config.py:100` 必填一致；不设默认，Art.4）。
- `same_as_core(path: str, staged: bool, core_ref: str | None) -> bool`（替换 `same_as_master`）
  - 与**一个**权威 core 引用（`load_core_refs()` 的第一个）比较：staged 模式比暂存区，否则比 HEAD。
  - `core_ref` 为 `None`（一个都解析不到）→ `False`（不放行）。
- `foreign_import_commits(core_refs: list[str]) -> dict[str, list[str]]`（新）
  - 仅在 `in_merge()` 为真时调用。执行
    `git log --format=%h %s --name-only --diff-merges=dense-combined MERGE_HEAD ^HEAD ^<ref1> ^<ref2> ...`。
  - OUTPUT：`{path: ["<short-hash> <subject>", ...]}` —— 本次 merge 带进来、且**不在 core 历史中**的提交（含 merge 提交的
    冲突解决 / 夹带改动）触及的每个文件。
- merge 过滤规则（改，`main()` 中 `:279-290` 一段）：越界文件 f 仅当满足以下之一才放行：
  1. `same_as_core(f, staged=True)`（与权威 core 引用一致）；或
  2. `same_as_merge_head(f)` **且** f 不在 `foreign_import_commits()` 的键中（导入内容只来自 core 历史）。
  否则保留为违规，原因记为 `IMPORTED_OUT_OF_SCOPE (<short-hash> <subject>)`（来自非 core 提交）或原来的 `OUT_OF_SCOPE`。
- pre-merge-commit 路径（改，`:293-306`）：`same_as_master(f, True)` → `same_as_core(f, True, core_ref)`。其余不变
  （仍无 MERGE_HEAD，无法做提交归属，仍 DEFER 到 pre-commit）。
- 报错提示：出现 `IMPORTED_OUT_OF_SCOPE` 时打印"这些改动来自不属于 core 历史的提交；跨 agent 的改动应经 master 合入。
  若它们其实已在 core 分支上，先 `git fetch` 更新 `<upstream_branch>` 再重试"。

### Field Dictionary

| field | type | meaning | producer | consumer | constraints / allowed values |
|-------|------|---------|----------|----------|------------------------------|
| `core_branches` | list[str] | core agent 的分支名（本地引用） | installer 写入 `.governance/config.json` | `check_scope.load_core_refs`、`config.py` | 必填、非空；N/A contracts — config schema 记录在 `governance_core/installer.py:22-36` 模块 docstring，`contracts/` 中没有 config 契约（既有状况） |
| `upstream_branch` | str | core 分支在远端的跟踪引用（如 `origin/master`） | installer 写入 config | `check_scope.load_core_refs`、`config.py` | 可选；缺失 = 不用远端引用；同上，N/A contracts（installer docstring） |
| `IMPORTED_OUT_OF_SCOPE` | str（stdout 违规原因） | 越界文件由非 core 历史的导入提交带入 | `check_scope.py` | 人 / agent 阅读 pre-commit 输出 | 不持久化、不跨 agent 存储；N/A contracts |

### Flow

```
git commit (merge, MERGE_HEAD present)
  -> .git/hooks/pre-commit stub -> check_scope.py --staged-only
     -> resolve agent (config) ; core -> PASS
     -> staged files vs allow/deny -> violations
     -> in_merge():
          core_refs = load_core_refs()                      (config core_branches + upstream_branch)
          foreign   = foreign_import_commits(core_refs)     (git log --diff-merges=dense-combined MERGE_HEAD ^HEAD ^core_refs)
          keep f if not (same_as_core(f) or (same_as_merge_head(f) and f not in foreign))
     -> violations ? FAIL (exit 1, names importing commits) : PASS

git merge (conflict-free, auto-commit)
  -> .git/hooks/pre-merge-commit stub -> check_scope.py --merge-commit
     -> violations not same_as_core -> DEFER (exit 1, merge left staged) -> git commit -> path above
```

## Non-Goals

- **防篡改**：本地 `master`、`refs/remotes/<upstream>` 都是业务 agent 能改动的引用（`git branch -f`、`git update-ref`、
  改 remote）。门禁是防误操作的护栏，不是对抗恶意 agent 的安全边界；这一点今天已如此（`same_as_master` 用的就是本地
  `master`），本提案不改变。Bash 层拦截改引用的命令另行评估。
- **Bash 层禁止 merge 其他 agent 的分支**（scope-guard）：判定放在提交门禁一处；不在命令串上猜分支归属。
- **快进 merge**：不产生提交、不运行任何 hook；只把分支移到已在别处经过门禁的提交上。本提案不处理。
- **pre-merge-commit 中做提交归属**：该 hook 运行时没有 MERGE_HEAD，无法确定导入来源（0.48.3 已实测），继续 DEFER。
- **session-context 的 drift 提示写死 `origin/master`**（`governance_core/hooks/session-context.py:221,244`）：同族问题，
  但属提示信息、不影响判定，留作后续。
- **config 契约化**（把 config schema 放进 `contracts/`）：既有缺口，不在本提案。

## Open Questions

- **陈旧 core 引用导致误拦**：业务 agent `git pull` 自己的远程分支时，如果那个分支合入过比本 clone 的 `upstream_branch`
  更新的 master，那些 core 提交在本地不属于"core 历史" → 被判 `IMPORTED_OUT_OF_SCOPE`。
  倾向：接受（fail-closed），报错提示先 `git fetch`；不在门禁里自动 fetch（hook 不应发起网络请求）。
- **权威 core 引用的优先级**：内容比较用 `upstream_branch` 优先、其次 `core_branches[0..]`。业务 clone 不在 core 分支上
  提交，远端引用通常最新；core clone 本来就直接放行。倾向：按此实现。
- **既有违规历史**：业务分支上若有 0.47.0 之前（门禁不存在时）提交的越界改动，之后从远端 pull 自己的分支时会被翻出来。
  倾向：接受，报错里点名提交，由 core 处理；不加豁免名单。

## Alternatives & Rationale

1. **（选定）按来源提交归属**：只对"本次 merge 带进来、且不在 core 历史中的提交"所触及的越界文件取消豁免。
   来自 master 的同步、pull 自己的分支（其中的 master 合并已在 core 历史里）照常通过；合并其他业务 agent 的分支时，
   对方的越界提交被点名拒绝。merge 提交的冲突解决 / 夹带改动也能归属（`--diff-merges=dense-combined`）。代价：每次 merge
   提交多一次 `git log`。
2. **只认 core 祖先**：MERGE_HEAD 必须是某个 core 引用的祖先，否则 merge 导入不享受豁免。实现更简单（一次
   `git merge-base --is-ancestor`），但 pull 自己的远程分支时，只要对方含有本 clone 内容不一致的 core 文件就会误拦；
   且给不出"哪个提交带来的"这一信息。
3. **Bash 层拦截**：scope-guard 拦 `git merge <非 core 分支>`。要从命令串推断分支归属（别名、`git pull`、`FETCH_HEAD`），
   绕法多，判定也分散到两处。不选。

## Guardrails

- edit-write-guard / constitutional-review：只改 `governance_core/` 包源；不引入 `.get(k, default)`，并移除 config.py 中已有的一处；
  check_scope 的门禁输出沿用文件现有的 CLI `print` 风格（命令输出，不是日志）。
- command-guard：测试通过 `git -C` 与临时目录完成，不 `cd` 进嵌套仓库。
- session-boundary-guard：所有改动在本仓库内；deva-vani 的实测由对方会话完成。
- 发布需人工确认（core-A3）。

## Phases

### Phase A: config-derived core refs

- Deliverables:
  - `check_scope.load_core_refs()`；`same_as_master` → `same_as_core`（staged / HEAD 两种比较、pre-merge-commit 路径一并改）。
  - 去掉 `check_scope.py` 中剩余的 `"core"` / `"master"` 字面量，改用 topology core 名与 core 引用。
  - `config.py`：`upstream_branch: str | None`，成员测试，无默认值。
- Validation: 新测试 —— 本地 `master` 陈旧、`upstream_branch` 指向较新的 core 提交时，自动 merge 不再 DEFER、`--no-commit`
  路径通过；源码中不再出现写死的 `master` 引用（测试读取源码断言）；`upstream_branch` 缺失时 `config.load()` 返回 `None`。
- Exit criteria: 全量测试通过；新测试在 0.48.3 上 FAIL（反向校准）。

### Phase B: attribute merge imports to source commits

- Deliverables:
  - `foreign_import_commits()`；merge 过滤改为上面的两条放行规则；违规原因 `IMPORTED_OUT_OF_SCOPE (<hash> <subject>)` 与修复提示。
- Validation: 新测试 —— (1) 合并另一个业务 agent 的分支、其中有越界提交 → 拒绝并点名该提交；(2) 对方分支的 merge 提交在冲突解决
  中夹带越界改动 → 拒绝；(3) 合并 core 历史（upstream）→ 通过；(4) pull 自己的远程分支（含已在 core 历史中的 master 合并）→ 通过；
  (5) core clone 合并任何分支 → 通过。
- Exit criteria: (1)(2) 在 0.48.3 上 FAIL、(3)(4)(5) 两版都 PASS（防过度拦截）；全量测试 + 脚本风格测试通过。

### Phase C: docs + release

- Deliverables: `/sync-repos` 说明（跨 agent 改动经 master；被拒时先 `git fetch`）、core-manual、skill 一句；版本号。
- Validation: wheel 内容检查；hub `governance-core upgrade` + `doctor` exit 0。
- Exit criteria: owner 确认后发布；deva-vani 在新版本上做一次真实 `/sync-repos`，门禁通过。

## Approval Criteria

- [ ] Every Field Dictionary entry names its governing `contracts/` file (or is N/A) — human-verify: each field row cites a contracts/ file or states N/A with the reason
- [ ] Every user-facing capability / mutation has a named realizer — human-verify: every decision is made by tools/check_scope.py via the installed pre-commit / pre-merge-commit stubs
- [ ] All Open Questions are resolved or explicitly deferred — human-verify: the approver accepted or overrode each leaning
- [ ] A merge of another business agent's branch carrying an out-of-scope commit (or an out-of-scope edit inside a merge resolution) is rejected and names the commit — cmd: python -m pytest tools/test_installer_commit_gate.py -q -k foreign_agent_branch
- [ ] Merges from core history (upstream ref ahead of a stale local master), own-branch pulls, and core-clone merges still pass — cmd: python -m pytest tools/test_installer_commit_gate.py -q -k merge
- [ ] check_scope.py no longer hard-codes the core branch or core agent name, and config.py has no upstream_branch default — cmd: python -m pytest tools/ -q -k hardcoded_core_refs
- [ ] New tests discriminate: the rejection cases fail on 0.48.3 and the pass cases pass on both — human-verify: calibration result recorded in State Log
- [ ] Full suite passes — cmd: python -m pytest tools/ -q
- [ ] Real consumer merge passes on the release — human-verify: deva-vani reports a /sync-repos merge on the new release passing the gate

## Validation Plan

- 用例全部经真实 `installer.install()` 安装的 hook 运行（只 stub 授权码校验），fixture 使用 deva-vani 的 nested 4-clone 形态与
  真实 `core_branches` / `upstream_branch` 值（`upstream_branch` 用一个本地分支名模拟远端跟踪引用，或在 fixture 中建 bare remote）。
- 反向校准：把新测试拷到 `artifacts/`，`git stash -u` 后对 0.48.3 代码运行，记录 FAIL / PASS 分布。
- `python -m pytest tools/ -q`（从仓库根目录，dogfood 自治层）+ 脚本风格测试逐个运行。
- 发布后请 deva-vani 做一次真实 `/sync-repos`，并（可选）在一个业务 clone 里试合并另一个业务 agent 的分支，确认被拒。

## Rollback / Recovery

- 单个 commit 内完成；`git revert` 即回到 0.48.3 行为（整体豁免）。消费者降级 `pip install governance-core==0.48.3` 后
  `governance-core upgrade`。
- 若门禁误拦正常 merge：`git merge --abort`；core agent 可在该 clone 用 `--no-verify` 完成（core 不受 scope-guard 的
  `--no-verify` 拦截），并报告给 hub。

## Risks

- **陈旧引用误拦**（中概率、低影响）：见 Open Questions；报错给出 `git fetch` 提示。
- **大 merge 的性能**（低）：多一次 `git log --name-only`，对 `HEAD..MERGE_HEAD` 范围线性。sync 的范围通常是几十个提交。
- **dense-combined 的边界**（低）：只列出与所有父提交都不同的文件；若冲突解决恰好取了某一侧，则该文件归属于那一侧的普通提交，
  仍会被正确归属。需要 git ≥ 2.31（`--diff-merges`）；更老的 git 回退到 `--cc`（同义，更早支持）—— 实现时以 `--cc` 为准或做版本探测。
- **既有越界历史被翻出**（低概率、中影响）：见 Open Questions。

## State Log

- 2026-11-05: draft created by core agent (P-0131)
- 2026-11-05: draft → pending (submit for review)
- 2026-11-05: pending → approved (owner: 批准 P-0131)
- 2026-11-05: approved → in-progress (implementation started)
- 2026-11-05: in-progress → implemented (as-built: hardcoded-ref + config tests in new tools/test_core_refs_config.py (not test_installer_commit_gate.py); --cc used instead of --diff-merges=dense-combined (same output, older git); 0.48.3 auto-merge fixture reworked so core-next is core history (origin/master -> newer core-tip). Calibration vs 0.48.4: 5 FAIL (upstream-ahead auto-merge, 2 foreign-branch, 2 hardcoded), 6 pass cases PASS on both. Full pytest 357 passed, script-style 28 passed. Not yet released (0.48.5 pending owner).)
