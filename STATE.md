# STATE — governance-core

Session-bridge log. `/wrap-up` Step 1 prepends a dated entry under
"Updates in This Session"; `tools/rotate_state.py` archives entries older
than 7 days to `STATE_ARCHIVE.md`; `session-context.py` surfaces recent
entries at SessionStart.

This file is committed (authored governance record). Adopted by P-0068
Phase 3c — single-agent governance-core still needs a session-state bridge,
so the STATE.md capability is provided by the package (the installer seeds
an initial copy; `rotate_state.py` ships in `tools/`).

## 1. Updates in This Session

<!-- Newest entry on top. Format:
### YYYY-MM-DD — <short title>
- 改动摘要 / 涉及文件 / 关键决策 / 测试结果
-->

### 2026-06-16 — P-0103 Phase 1+2（A discover + D measure）close learned-skill loop（未发布）

- **#100 根因**（已 live 印证）：`session-context._emit_skill_injection` 自
  prefix_cost C3（2026-05-07 批准）起只发 counts-only（本 session banner 即
  `0 learned + 16 guides discovered`），agent 看不到 skill 名 → 5 clone 0/~50
  learned skill 被用；`record_surfaced` 存在但不在 live path。
- **A（discover）**：新 `registry.emit_bounded_injection(registry)` —— 读
  consumer 自著的 `knowledge/skills/_tiers.json`（universal tier）+ 新
  `_scenario_clusters.json`，发 **bounded** `name+desc`（universal ≤10）+ 紧凑
  `cluster→members` MAP（body 懒加载），调 `record_surfaced`；无 index 返 None。
  `_emit_skill_injection` 先试它、空则**回退 counts-only**（hub 0-skill 即此路）。
- **D（measure）**：`record_surfaced` 现已在 live path（随 A）；`--funnel` CLI
  早已存在 → D 实质随 A 完成。修 `_get_tracker` 绑 registry 的 `_root`（surfaced
  落到被注入项目，default 行为不变、project_root 时正确 + 测试可隔离）。
- **桥接设计修正**（用户认可）：gc **不 ship** `_scenario_clusters.json`（无
  `knowledge/skills/` copy category，会 clobber 消费者自著）；只 ship **schema
  文档 + reader**，json 消费者自著、gitignored，hub 回退 counts-only。同
  candidate-pipeline「消费者自著数据、hub 只 ship 机制」同构。
- **涉及**：新 `governance_core/knowledge_governance/skill-scenario-clusters.md`
  （schema 契约）+ `discovery/registry.py`（reader + tracker 绑定）+
  `hooks/session-context.py`（改接 + try/except 回退）+ `runtime_import_audit.py`
  （登记 session-context 为 fail-open gc importer，过 Art 纪律审计）+ 新
  `tools/test_skill_injection_bounded.py`（6 例 fixture）。
- 验证：bounded 6/6 + pytest 55 + script 25/25（含 runtime-import 14/14 修复）；
  live hook 双路验证（hub→counts-only rc0；authored index→bounded 菜单 rc0）；
  upgrade manifest 152、doctor 略。**未 bump 版本**（release 在 Phase 5）。
- **剩余 P-0103**：Phase 3（B consult clause via /iterate-constitution，用户选宪法
  载体）、Phase 4（C extract-skill scenario 分类 + bijection gate）、Phase 5
  （dogfood + 发布 + 关 #100）。

### 2026-06-16 — P-0102 修 #97 移走 maintainer-only 测试 + #99 learn.md 载体感知时间戳 + 0.30.0

- **#97 消费者 manifest 下发 maintainer-only 测试**：审计 `governance_core/tools/
  test_*.py` 找到 **2** 个 import-时崩的（`sys.path.insert(maintainer)` + import
  maintainer 模块）：`test_curate_gate.py`（`import curate_gate`）+
  `test_candidate_intake.py`（`import candidate_intake`）。消费者无 `maintainer/`
  → test collection 崩。修法：`git mv` 两者到 `maintainer/`（与被测代码同处、
  `maintainer/` 本就不进 `COPY_CATEGORIES`/不打包）；`parent.parent` 对 tools/ 和
  maintainer/ 都解析到 repo root，**零逻辑改动**，仅改各自 docstring 运行路径行。
  `test_auth_guard` / `test_renewal` 只在注释/tmp_path fixture 提 maintainer、实际
  只 import `governance_core`（已分发），消费者安全、**不动**（避免误移）。
- **#99 learn.md 更新时间戳只认 MD**：Step 0 允许 HTML profile 载体（`kc:*` meta），
  但 Step 3/4 只 bump YAML `updated:` → HTML-profile 文档可不 bump `kc:updated`、
  陈旧时间戳被 dashboard/staleness 审计误读为 current。修法：Step 3 item 3 载体感知
  （MD→`updated:` / HTML→`kc:updated`，status 变同步 `kc:status`）；Step 4 加
  HTML-profile 的 `kc:*` 映射 note。kc:* 名核对 `knowledge-html-profile.md` 一致。
- **合并依据**：两者皆消费者报的治理卫生 bug、互不相关但小，按 P-0099 先例合并
  一个 proposal + 一次发布。
- 验证：script 25/25（2 relocated 从 maintainer/ 跑 14+25 例）+ pytest 49 green；
  upgrade prune **恰好** `tools/test_curate_gate` + `test_candidate_intake`、
  manifest 152→150；wheel 顶层仅 `governance_core*`、**排除**两 relocated 测试、
  无 `maintainer/` 泄漏；learn.md 载体文本入包；doctor exit 0。版本 0.29.0 →
  **0.30.0**。关 #97/#99。

### 2026-06-16 — P-0101 修 #98 hook stdin GBK fail-open（19 hook UTF-8 字节读取）+ 0.29.0

- **#98 根因**：所有读 stdin 的治理 hook 用 locale 文本模式（`json.load(sys.stdin)`
  / `json.loads(sys.stdin.read())`）。Windows GBK/cp936 下含中文（非 cp936）的
  payload 解码即 raise，被 `except` 吞掉 → hook **fail-open**（沉默放行）。消费者
  trade-agent `proposal_classify_fast_errors.jsonl` 记 313 条 "stdin parse failed"
  fail-open。最危的是 `proposal-classify-fast.py`（5 层 backstop gate）。
- **主修复**：19 个 hook 的 stdin 读取改为 locale 无关的
  `json.loads(sys.stdin.buffer.read().decode("utf-8"))`（buffer 绕过文本层，解码
  与 OS locale 无关）。narrow-except 的 4 个（constitution-reminder /
  constitutional-review / prompt-context-router / session-context）补
  `UnicodeDecodeError`；broad-except 的 13 个 + skill-usage-tracker（ValueError
  已涵盖）只改读取行。
- **关键判断**：多个 gate（command/scope/edit-write/data-source-guard）**本就
  `except Exception: sys.exit(0)` fail-open by design**；classify docstring 明示
  fail-open backstop（"绝不因自身 bug 锁死仓库"）。#98 真因不是 fail-open 分支
  存在，而是**合法中文 payload 被误路由进它**。故只修解码、**保留各 hook 既有
  fail 姿态**（不擅自翻 fail-closed —— 那是另一个有锁死风险的独立硬化决定，标为
  可选后续）。"no gate is loosened" 满足。
- **纵深防御**：installer `_write_settings_local_json` 原生写 `env.PYTHONUTF8="1"`
  （fresh 建 + merge-if-absent 不覆盖消费者既有 env），fresh 装即带缓解、不再仅靠
  preserve 旧 env。Art.4 用 `"env" in data` 而非 defaulted lookup（注释也避字面
  `.get(k,default)` 以免 constitutional-review 误命中）。
- **测试**：classify hook +2 回归（中文 payload→gate block exit 2；非法 utf-8→known
  fail-open exit 0），用 `PYTHONIOENCODING=ascii` **确定性**复现 —— hub 机器系统
  代码页是 UTF-8、`PYTHONUTF8=0` 复现不出 GBK fail-open（同 hub-cannot-dogfood
  类），ascii 文本模式对任何 >0x7f 字节必 raise、buffer 读绕过、跨平台稳定。新
  `test_installer_settings_env.py` 3 例（fresh 有 / merge 保留 / 不覆盖已有）。
- 验证：script 式 25/25（command-guard 等无回归）+ pytest 49 green；upgrade 后
  settings `env={PYTHONUTF8:1}`、classify 9/9；command-guard 中文 evasion→block(2)
  手验；wheel 顶层仅 `governance_core*`、含 19 hook 改动 + installer + 2 测试、
  无 `maintainer/` 泄漏。版本 0.28.0 → **0.29.0**。关 #98。

### 2026-06-15 — P-0100 收编 candidate #96 proposal_suggest（泛化 kernel）+ 0.28.0

- **curate #96**（trade-agent `mechanism` 候选）→ 包源，泛化 kernel 收编：
  - 新 `governance_core/tools/proposal_suggest.py`：`/proposal classify` 只读建议
    助手，三路纯关键词召回（① 类似 proposal、② 起草检查项、③ likely scope）。
    **机制逐字保留**，仅 **瘦身 `_DOMAIN_ALIASES`**：删 trade 域词（信号/回测/
    交易/下单/风控…）只留域中立结构别名（宪法/契约/钩子/工具/审计/测试）。
  - 新 `governance_core/tools/test_proposal_suggest.py`：12 例；③ alias 用例改用
    保留别名（工具→tools）维持覆盖，fixture 去 trade 词中性化。
  - 新 `governance_core/knowledge_governance/proposal-drafting-checklist.md`：补
    candidate **缺失的 ② 数据源 seed**（`source_paths` 漏带、但其集成测试断言其
    存在）。通用治理起草经验 seed（4 条，域中立），消费者自维护其条目。
  - `governance_core/commands/proposal.md` classify 节加只读指针。
- **关键判断**：candidate 唯一实质缺陷是 ② 数据源文件没随载荷上传 → 补**通用
  seed** 同时满足"测试要求文件在"+"消费者自维护内容"，矛盾消解（非放宽测试）。
  `pyproject` glob 已覆盖二新文件，无需改 package-data。③ 在单 agent hub 退化为
  `（无）`（Art.12，非缺陷，对多 clone 消费者仍 live）。
- **记账**：`registry.record_candidate` 记 promoted（**不**用 `candidate.py promote`
  —— 会拿原始 payload 覆盖泛化改动，沿用 P-0098 教训）。
- 验证：pytest 44 green；proposal_suggest 12/12；proposal_classify×3 + import-audit
  全绿；upgrade + doctor exit 0；烟测三节渲染（① live / ② 命中 seed / ③ 无）；
  wheel 顶层仅 `governance_core*`、含 3 新文件、无 `maintainer/` 泄漏。版本
  0.27.0 → **0.28.0**。关 #96。

### 2026-06-12 — P-0099 修 consumer bug #90 sweep 重复 uplink + #91 sync_infra 删 tracked hook + 0.27.0

- **#90 `candidate.py sweep` 重复 uplink**（即 #87/#89 的成因）：
  - **RC1** `cmd_sweep` 抽出纯函数 `_dedup_pending_by_digest`，uplink 循环前按
    digest 去重 `pending`（pre-scan ledger 快照下两个同 digest envelope 都过
    `is_uplinked` → 都 uplink → 重复 issue）。
  - **RC2** `collect.py collect_netnew_skills`：已存在同 digest envelope 时跳过
    新建（`skill_digest` vs 现存 `payload_digest`；延迟 import ledger 避循环）。
    改后 collect 对未变 skill 幂等，变更 skill（新 digest）仍 stage 为 update。
- **#91 `sync_infra._remove_local_copy` 删 git-tracked 集中化 hook**：加
  `_is_git_tracked`（`git ls-files --error-unmatch`，任何失败 fail-safe→False）；
  tracked 的本地副本改为 `[KEEP]` 保留（settings 已指向 core 绝对路径、永不执行），
  只删 untracked orphan（迁移本意）。settings 引用重写半边不动。
- 测试：`test_candidate_sweep` +6（2 RC1 纯函数 + 4 RC2 collect 幂等/edited）；
  新 `test_sync_infra_remove_local_copy.py` 4 例（tracked keep / orphan del /
  dry-run / 非 repo fail-safe）。
- 验证：pytest 32（28+4）green；24 个脚本式测试全绿（command-guard 42/42 等
  无回归）；upgrade + doctor exit 0；wheel 顶层仅 `governance_core*`、含改动、
  无 `maintainer/` 泄漏。版本 0.26.0 → **0.27.0**。关 #90/#91。

### 2026-06-12 — P-0098 收编 gc #89 skill competing-design-proposals-with-deferred-adr（去域化）+ 0.26.0

- **curate #89**（trade-agent 候选 skill）→ 包源
  `governance_core/skills/competing-design-proposals-with-deferred-adr.md`：
  - frontmatter 重塑 learned→guide（`theme: universal` / `type: guide`；
    name/description/tags 保留；updated 06-12），H1 标题化 + 加 provenance 注。
  - **de-trade-ify**：唯一域泄漏 Note 行（"不可比红线/单流基线回归 delta=0"）
    泛化为通用基线回归守卫；机制/workflow 逐字保留。
- **#87 duplicate**：与 #89 payload 逐字相同（仅 candidate id 日期后缀 0611 vs
  0612 不同）。关 #87 指向 #89，**不**进 rejected_registry —— 内容实为 promoted，
  否则会给 trade-agent 发错 reject 信号。
- **关键坑**：hand-genericize 后**不能**用 `candidate.py promote`（它对 skill kind
  会把**原始** payload 拷回覆盖我去域化后的文件）；改直接调
  `registry.record_candidate` 记 promoted（同一库函数，Art.8 同路径）。
- **清理**：删 `.governance/candidate-outbox/` 两个死快照（command-guard
  `# P-0065 Phase 4 drift probe` 探针残留 + auth-guard pre-P-0082 旧快照；
  gitignored，live 自治层已无漂移、无需 promote）。
- 验证：28 pytest green；discovery 收录新 guide；upgrade + doctor exit 0；
  wheel 顶层仅 `governance_core*`、含新 skill、无 `maintainer/` 泄漏。
  版本 0.25.0 → **0.26.0**。
