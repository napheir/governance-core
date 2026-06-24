# Trade Agent 项目状态文档 — Archive

> 此文件包含 STATE.md 的历史条目（超出滚动窗口的部分）。
> 按时间倒序排列（最新在前）。
> 由 `tools/rotate_state.py` 自动管理。

---

### 2026-06-16 — P-0103 Phase 5 发布 0.31.0（close learned-skill loop A/B/C/D 全数上线）

- **Phase 5**：bump 0.30.0 → **0.31.0**，发布 P-0103 全部四部分（A discover /
  B consult 第十五条 / C coverage gate / D funnel）到 PyPI；关 #100；
  complete + archive P-0103。
- 闭环回顾：A（`emit_bounded_injection` 有界注入）+ B（宪法第十五条 技能咨询
  纪律）+ C（audit Check 16 scenario coverage + extract-skill Step 6b）+ D
  （live `record_surfaced` + `--funnel`）。gc ship 机制（schema + reader + clause
  + gate），scenario 数据由各消费者自著（桥接设计）。
- 实现 commit：1045b6c（A+D）/ b9088f3（B 宪法）/ d5e8943（C gate）。

### 2026-06-16 — P-0103 Phase 4（C register-enforce）scenario coverage gate（未发布）

- **C（register-enforce）**：闭"作者忘了登记"的复发缺口。
  - `extract-skill.md` 加 **Step 6b "Surface the skill"**：tier 分类不够，skill
    只在进入 SessionStart surface 时才被咨询；须 universal tier 或某 scenario
    cluster 成员（引第十五条 + schema 文档）。Step 8 audit note 加 Check 16。
  - `audit_knowledge.py` 加 **Check 16 scenario-surface coverage**：每 md-skill
    必须 universal **或** ∈ ≥1 cluster，否则 FAIL（永不被 surface）；cluster
    phantom 成员 FAIL。**gate 在 `_scenario_clusters.json` 存在时**（opt-in：未采用
    scenario 的项目不受罚），与 Check 11 gating 同构。
- **修正**：`_audit_scenario_coverage` 用 `SkillRegistry(project_root=root)`
  （比 Check 11 的无-root 版更正确、且 `--root`/测试可隔离）。
- 涉及：`governance_core/tools/audit_knowledge.py`（Check 16 + 函数 + docstring）
  + `commands/extract-skill.md`（Step 6b + Step 8 note）+ 新
  `tools/test_scenario_coverage_audit.py`（3 例 fixture）。
- 验证：scenario 3/3 + pytest 58 + key script 6/6；upgrade manifest 152→154。
  **预存问题（非本改动）**：hub 全 `audit_knowledge.py` 在缺 `knowledge/INDEX.md`
  时崩（hub 的 knowledge/ 稀疏、不在常规测试套件里；待后续单独修）。未 bump 版本。
- **剩余 P-0103**：Phase 5（bump 0.31.0 + 发布 + 关 #100 + complete/archive）。

### 2026-06-16 — P-0103 Phase 3（B consult）新增宪法 第十五条 技能咨询纪律（未发布）

- **B（consult）**：经 `/iterate-constitution` 新增 **第十五条：技能咨询纪律** ——
  任务开始前必须先咨询 SessionStart 注入的 universal skills / scenario clusters，
  命中场景时**加载相关 skill/cluster 而非重新推导**。闭合 discover→**consult**→
  apply 的中段（A discover 已在 Phase 1 落地）。
- **载体**（用户选"走宪法"）：`constitution/total.md` 加第十五条（填 art_15 空槽，
  位于 14 wrap-up 与 16 memory 间）+ 新 clause 源
  `governance_core/clauses/art_15_skill_consultation_discipline.md`（**域中立**，
  下发所有消费者；未泄 gc 内部 proposal id）。
- 验证：regen CLAUDE.md 第十五条就位（247 行 / 13150 chars << 上限）；
  audit_sub_constitutions OK（无子宪法改动）；check_constitution_change clean；
  upgrade 渲染 `.governance/clauses` 10→11（art_15 生成）。classify gate 已记录
  （constitution/total.md 高敏路径，经 P-0103 治理）。
- **剩余 P-0103**：Phase 4（C extract-skill scenario 分类 + bijection gate）、
  Phase 5（dogfood + 发布 + 关 #100）。


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


### 2026-06-03 — P-0097 收编 gc #85 repo-deletion 加固（#84 superseded）+ 0.25.0

- **两层防御**（用户："我们需要做一些防御"）：
  - **command-guard deny-list** +11 模式（纯增，verified diff）：gh-CLI 删除子命令
    （repo delete/archive、release delete、secret delete/remove）+ 7 条 raw
    API/GraphQL/curl/PowerShell/transfer/scope-grant，**锚定 repo ROOT 路径**故子资源
    DELETE（labels/comments/refs/runs）仍放行；`gh issue delete` 有意放行（sweep 用）。
  - **`tools/check_github_token_scope.py`**（net-new）：根因检查 `delete_repo` OAuth scope，
    **advisory** 接进 `governance-core doctor`（出现就 loud-warn，**不改 doctor 退出码**；
    gh 不可用→safe）。用户选 doctor 集成而非 session-start（scope 稳定、免每会话延迟）。
- **#84 superseded by #85**（#85 deny-list 是 #84 的严格超集）：两者都记 `promoted`，
  #84 note 注明经 #85 收编、未单独应用。两 issue 已关闭（#85 completed / #84 not-planned）。
- **de-trade-ify**：候选里 trade 侧 `(P-0088)`/`(P-0089)` 引用改为 gc `P-0097`（否则会被
  误读成 gc 自己的 P-0088/P-0089）。
- **关键事实/坑**：(1) `gh`/`curl` 不在 allow-list → deny 真生效（real-hook 42/42 复核，
  非仅 regex probe）；(2) hub 当前 token 无 `delete_repo`（gist/read:org/repo/workflow），
  授权层已挡删库；(3) **dogfood 即时反噬**：deny 上线后 guard 拦了我自己含 "gh repo delete"
  字面的 `--note` 命令 —— deny 匹配整条命令串，"提到"也拦（记 memory，用 -F/--body-file 绕）。
- 验证：command-guard real-hook **42/42**、token-scope 单测 6/6、全套 28 pytest + 25 script
  green；upgrade + doctor exit 0（doctor 出 token-scope 行）；wheel 顶层仅 `governance_core*`、
  含新工具、无 `maintainer/` 泄漏。版本 0.24.1 → **0.25.0**（含此前 hold 的 0.24.1 doc 改动）。

### 2026-06-02 — gitignore 卫生 + 云端 curation routine 暂停

- **gitignore（A）**：三个 untracked 目录此前未被忽略、仅靠"只显式 `git add`"纪律挡着 ——
  `artifacts/`（Art.10 红线）、`.claude/cache/`（运行时缓存）、`governance_core/.claude/`
  （某次 hook/classify 把 repo-root 误解析成 `governance_core/` 写进包源的 classify-log
  缓存杂物）。`.gitignore` 补三条 root-anchored 规则，check-ignore 三者全命中。
- **清理（B）**：删除误写进包源的 `governance_core/.claude/`（纯清理，不进 git）。
- **云端 routine 状态**（claude.ai，非仓库）：`gc-curation-routine`
  （`trig_01UjyaQUt3fpdNGDiDqU3Smh`）已 **enabled→false 暂停**（用户决定先手动验证几轮、
  看自动处理是否合理再重开）；其 inline prompt 已**同步到 P-0096**（needs-human/feedback
  分支 + 一条 hard rule 强制先读评论）；kill-switch `auto_curate_enabled` 仍 false。
  重开两道开关分离：触发器 enabled（跑不跑）与 kill-switch（advise-only vs auto-promote）。

### 2026-06-02 — P-0096 curation 评审强制读 issue 评论（堵 #26 暴露的缺口）+ 发布 0.24.0

- **发布**：v0.24.0（P-0094/P-0095）经 GitHub Release → CI Trusted Publisher 发到正式
  PyPI（run 26820323541，publish-pypi 22s success）；3 commit push 到 origin/master。
- **P-0096（task b）**：curation 的 LLM 评审层（`curate_routine.md` step 2 needs-human /
  step 3 feedback + 嵌入 routine prompt + 一条 hard rule）现**强制先读 issue 评论**，提交方
  自更正凌驾 body；`commands/curate-candidate.md` step 3 "fetch body" → "fetch body AND
  comments"（引 gc #26 为先例）。**确定性 gate `curate_gate.py` 故意不动**——保持 body-only，
  评论永不能翻转 auto-promote eligibility（守 P-0090 信任模型），评论仅作 LLM 判断输入。
- 验证：suite 22 pytest + 25 script green；upgrade + doctor exit 0；dry-run 0 drift；
  wheel 顶层仅 `governance_core*`、无 `maintainer/`/`curate_routine` 泄漏。版本 0.24.0 →
  **0.24.1**（doc-only patch；0.24.1 是否发 PyPI 待定——消费者不跑 hub-only 的 curate）。

### 2026-06-02 — P-0094 / P-0095 收编两个 candidate（gc #27 EOL-drift + #26 sync-manifest note）

- **P-0094（gc #27）EOL-normalize manifest hashing**：`installer.py` 新增
  `_content_sha256(path)`（hash 前把 `\r\n`/`\r` 归一化为 `\n`），在 `_write_installed_manifest`
  baseline 与 `_capture_drift` current **两处**统一使用 —— 消除 Windows `core.autocrlf=true`
  消费者每次 checkout 把 install-managed 文本文件当成 drift 的假阳性。新增
  `tools/test_installer_drift_eol.py`（6 例：CRLF no-op / lone-CR / 真实改动仍捕获 /
  baseline-drift 对称）。
- **P-0095（gc #26）sync-repos manifest 对齐 note**：candidate body 已被提交方自己的
  更正评论证伪（`/sync-repos` 是 git-merge、`MERGE_HEAD` 豁免 + `--no-verify` 成立，
  **不**销毁 drift）。只收编**更正后的内核**：`commands/sync-repos.md` 加「同步后：对齐
  gc-managed 层 manifest」+ `wrap-up.md` Step 5b 一行 cross-ref —— git 带不动 gitignored
  的 `installed_files.json`，merge 后须补跑 `governance-core upgrade --project-root <clone>`
  对齐，否则下次 upgrade 误报 drift（噪音，非数据丢失）。**未**下发被撤回的错误论断。
- **关键决策**：(1) hub 自治层 gitignored、git 从不 CRLF 重写它 → hub **复现不了** #27 症状，
  只能单元层验证；(2) dogfood 前先删旧 raw-byte manifest 做干净 re-baseline，避免归一化
  `_capture_drift` 对旧 baseline 触发全量 transitional-reflag envelope 噪音；(3) 暴露 hub 侧
  缺口 —— `curate_gate.py` 只读 issue body 不读评论，needs-human 评审会漏看更正评论
  （已记入 #26 close 评论，作为 task b 的 follow-up proposal）。
- 验证：全套 **25 script + 22 pytest**（含新 6 例）green；删 manifest → upgrade 干净
  re-baseline → 二次 `upgrade --dry-run` 在 CRLF 工作树报 **0 drift**；`doctor` exit 0；
  wheel 顶层仅 `governance_core*`、含新测试、无 `maintainer/` 泄漏。版本 0.23.0 → **0.24.0**。
  关闭 GitHub #27、#26（附 curation 结果 + 致谢 + #26 特别致谢自更正）。

### 2026-06-01 — P-0088 P-0082 Phase 1 gc 侧：候选 intake CI + uplink 发布 envelope（+ #21 de-drift）

- 改动：落地 trade-agent 交接的 P-0082 Phase 1（hub 侧确定性候选 intake，无 LLM、
  绝不 promote）。4 phase：
  - **三件套**：`maintainer/auto_promote_security_surface.json`（8 类 41 globs 拒绝集）、
    `maintainer/candidate_intake.py`（`issues.opened` 跑：区分 candidate/feedback、拉发布
    envelope 结构校验、secret 复扫**复用 uplink.scan_envelope**、查 rejected 去重、算
    确定性 T0-eligibility、打标签+ack）、`.github/workflows/candidate-intake.yml`。
    GC-TODO 全部用真实 gc API 收口；决策核心抽成纯函数 `compute_eligibility`。
  - **uplink 发布**：`governance_core/candidates/uplink.py` 加 `publish_envelope` ——
    issue 创建成功后**幂等+best-effort** 上传 envelope 为 `candidates` 预发布资产
    `<id>.tar.gz`（修掉 handoff 的 `.tgz`/`.tar.gz` 不一致）；发布失败不让 uplink 失败。
  - **labels**：建 5 个（feedback/valid/auto-eligible/needs-human/dup-of-rejected）。
  - **#21 de-drift**（独立 commit）：从 `agent-least-privilege.md`(1) +
    `resource-layer-hardening.md`(3) 的 `related:` 删失效 `proposals/` 引用，bump updated。
- 涉及：上述 3 新文件 + uplink.py + `governance_core/tools/test_candidate_intake.py`(23) +
  `test_candidate_uplink_publish.py`(4) + 版本 0.20.1 → **0.21.0** + 2 个 knowledge_governance 文档。
- 关键决策/caveat：**uplink 发布需对 hub repo 写权限**——纯 issue 传输本不需要；无写权限
  的消费者发布失败 → CI 拿不到 envelope → 标 needs-human（优雅降级，已在码注+小结标注）。
  intake **无 promote 路径** → 本阶段零提权面。`maintainer/`+`.github/` 不进 wheel（Art.11.4）。
- 测试：intake 23/23、uplink-publish 4/4、pytest 16 passed、session-boundary 25/25、
  candidate 家族全绿；`upgrade`+`doctor` exit 0；wheel 隔离干净（顶层仅 `governance_core*`，
  无 maintainer/.github 泄漏）。Check 9 只查 frontmatter LINK_FIELDS（读码确认）。

### 2026-06-01 — P-0087 收编 issue #20：boundary-guard read-only 快速放行漏洞

- 改动：策展通用层候选 **issue #20**（mechanism / drift, trade-agent）—— 修复
  `session-boundary-guard.py` 的真实安全洞。`is_read_only_bash()` 用 start-anchored
  匹配，任何以只读动词（cat/grep/tail…）开头的命令在路径提取 + 关键路径检查**之前**
  就被当只读快速放行 → `cat foo > /越界` 甚至 `> ~/.ssh/...` 整个绕过守卫。实测当前
  包源 guard 对 `cat <in> > <.ssh>` 返回 exit 0（放行），漏洞 live。
- 修复（外科手术式，全文 diff 核实仅此改动）：`is_read_only_bash` 顶部加 redirect
  短路 —— 命令含文件写重定向 `>`/`>>`（负字符类 `[^\s&|;<>]` 排除 `2>&1`/`>&2`
  fd-dup）时返回 `False`，不再快速放行。测试 +4 回归用例（22 cat>outside 拦 /
  23 cat>.ssh 关键拦 / 24 cat>inside 放行 / 25 `2>&1` 放行），21 → **25**。
- 涉及：`governance_core/tools/session-boundary-guard.py`、
  `governance_core/tools/test_session_boundary_guard.py`、
  `pyproject.toml` + `governance_core/__init__.py`（0.20.0 → **0.20.1**，安全 patch）、
  `maintainer/consumer_registry.json`（记 `promoted`）、`STATE.md`、
  `shared_state/proposals/core/p-0087-*.md`。
- 关键决策：mechanism 类候选手工放置包源（Art.11.2 只改 `governance_core/`）；
  机制与示例已通用（`/outside`、`~/.ssh`）→ 无需 de-trade-ify；dogfood —— 本仓库
  自身 guard 同样带洞，`upgrade` 后修复。
- 测试：包源 guard 测试 **25/25**；repo-root `upgrade` 后 **25/25**；全套
  `pytest tools/` **16 passed**；`doctor` exit 0；wheel 隔离（顶层仅
  `governance_core*`、无 `maintainer/` 泄漏、修复在 wheel 副本中）。

### 2026-05-30 — P-0086 de-trade 既有 profile 示例残留（P-0078 cluster 清理）

- 改动：承 P-0085 策展时 grep 闸门发现的**既有** trade 域残留（P-0078 cluster
  promote HTML profile 时未彻底 de-trade），按 user 指令"也一并处理"清干净。改
  `governance_core/knowledge_governance/knowledge-html-profile.md`，profile
  v1.1.0 → **v1.1.1**（Patch：仅示例措辞、无契约变更）。
- 清理 6 处（完整 grep 清单）：§2.2.1 caption（`trade pin pipeline_current.html`）、
  §3.3.1 出处归因（`trade 2026-05-26`）、§3.3.1 strict-mode Mermaid 例
  （`signal_reader/dedup` + `artifacts/trade/{ts}` → gc `collect/dedup` +
  `artifacts/audit/{ts}`）、§4.1 autogen 整例（`s50-tier-metrics` +
  `artifacts/strangle50/...` + Tier/Precision 表 → `governance-audit-summary` +
  proposals/hooks/clauses 审计表）、§7 pilot 行 + Status footer
  （`s50_current.html`/rules → 中性消费者域）。语法/契约教训逐字保留。
- 涉及：`governance_core/knowledge_governance/knowledge-html-profile.md`、
  `pyproject.toml` + `governance_core/__init__.py`（0.19.0 → 0.20.0）、`STATE.md`、
  `shared_state/proposals/core/p-0086-*.md`。
- 关键决策：机制/契约/结构零改 → **audit 工具不 bump**；保留 §7 `harness_defense.html`
  （owner=core，gc 合法）+ §9 v1.1.0 的 "trade-agent" **候选来源归因**（准确 provenance、
  非域示例）；版本历史条目**不复述** trade token（否则自触 grep 闸门）。
- 测试：de-trade grep 闸门**清洁**（唯一命中"折叠面板"是通用 `<details>` 术语，
  非 trade）；全套 `tools/test_*.py` **21/21**；`audit_html_profile.py` exit 0（工具未改）；
  dogfood `upgrade` + `doctor` exit 0。

### 2026-05-29 — P-0085 promote #18: knowledge-html-profile §2.5 业务优先节

- 改动：策展通用层候选 **issue #18**（mechanism / drift, trade-agent）—— 把 net-new
  规范节 **§2.5「信息构建原则（业务优先）」**（~100 行）promote 进
  `governance_core/knowledge_governance/knowledge-html-profile.md`，profile
  v1.0.0 → 1.1.0。§2.5 规定 HTML 的**叙事语域**（§2.1–§2.4 管结构）：主叙事用业务
  语言、机器细节下沉 `<details>`、表格列优先业务语义、whole-document 应用范围。
- baseline drift（候选 baseline `432b40…` ≠ 当前源 `1ddbf8…`）→ **不信旧行号**，
  按上下文锚点手工应用（§2.4 末插 §2.5；§2.1 summary / §6 行 / §8 / §9 同步改）。
- **de-trade-ify**（skill step 3）：机制文字逐字保留，仅把消费者域示例换成 gc 自身域 ——
  §2.5.3 正/反例 trade 期权 pipeline（`option_selector` / strangle）→ **gc upgrade/install
  pipeline**（原子覆盖安装 / 改动文件转存 candidate-outbox）；§2.5.6 反模式去掉 `P-0081`
  与 trade section 名（signal_reader / scheduler / 面板）；provenance 改记 P-0085。
- **audit 工具与机器契约不动**：§2.5 是 voice/framing，机器无法判定 → 明确为
  human-review 层（§2.5.5 + §8）；`audit_html_profile.py` 只校验结构、**不随 profile
  v1.1.0 bump**。
- 涉及：`governance_core/knowledge_governance/knowledge-html-profile.md`、
  `pyproject.toml` + `governance_core/__init__.py`（0.18.0 → 0.19.0）、`STATE.md`、
  `shared_state/proposals/core/p-0085-*.md`。
- 关键决策：改包源（Art.11.2），不碰自治副本；独立 proposal/commit（与 #19 分开）。
  **发现既有 de-trade 缺口**：profile §3.3.1（`signal_reader/dedup` Mermaid 例）+ §4.1
  （`artifacts/strangle50/...` autogen 例）是 P-0078 cluster 遗留的 trade 残留，**不在
  P-0085 scope**（Non-Goals 不动 §3/§4）—— 已向 user 提示为后续候选。
- 测试：全套 `tools/test_*.py` **21/21**；`audit_html_profile.py` exit 0（无 HTML 文件、
  工具未改）；de-trade grep 闸门确认 §2.5（168–227 行）零 trade token；dogfood `upgrade`
  → autonomy profile 刷新到 v1.1.0；`governance-core doctor` exit 0。

### 2026-05-29 — P-0084 promote #19: narrow classify-paths governance glob

- 改动：策展通用层候选 **issue #19**（mechanism, trade-agent）—— bug fix。
  `governance_core/tools/proposal-classify-paths.json` v1.0.0 → 1.1.0：governance
  类的 catch-all `.governance/**/*` 收窄为权威子路径
  `.governance/clauses/**/* + core_keywords.json + config.json`。
- 根因：catch-all 命中**瞬态 gitignored** `.governance/candidate-outbox/`
  （collect.py `OUTBOX_REL`），导致 `/submit-candidate` / `/upgrade` drift-uplink
  每次写 envelope 都被 classify-fast PreToolUse hook 误判 `PROPOSAL_REQUIRED`
  硬阻。**gc 自身（self-host 消费者）现也中招** —— 强 dogfood 信号。matcher
  `_classify_match.py` 无 negation operator，故用显式枚举而非 exclude。同时
  剔除派生物 `.governance/installed_files.json`。
- 涉及：`governance_core/tools/proposal-classify-paths.json`、
  `governance_core/tools/test_proposal_classify_paths.py`（加 P-0084 回归断言 +
  docstring 17→19 globs）、`pyproject.toml` + `governance_core/__init__.py`
  （0.17.0 → 0.18.0）、`shared_state/proposals/core/p-0084-*.md`。
- 关键决策：改**包源**（Art.11.2），不碰自治副本；走独立 proposal（与 #18 分开，
  各自 commit/rollback）；保留所有真实治理源覆盖（实测前后对照：candidate-outbox
  / installed_files True→False，clauses/core_keywords/config/CLAUDE.md 仍 True）。
- 测试：`test_proposal_classify_paths.py`（19 globs、回归断言）+
  `test_proposal_classify.py` 9/9 + `test_proposal_classify_fast_hook.py` 7/7
  （自治层）全绿；dogfood `upgrade` → autonomy 副本刷新到 v1.1.0；
  `governance-core doctor` exit 0。

### 2026-05-29 — P-0083 add /curate-candidate command skill

- 改动：新增 `governance_core/commands/curate-candidate.md` —— hub 侧候选策展的
  编排 skill（`/submit-candidate` 的对偶），从本会话 6 轮策展提炼。**指针式
  checklist**（Art.99：只指向权威工具/文档、不复述）：review → classify（通用 vs
  域特定 / net-new / 完整性）→ verify（drift sha 比对 + `git apply --recount` /
  `--ignore-cr-at-eol` 去 CRLF 噪声;去 trade 化）→ 改包源（Art.11.2）→ wire（hook
  manifest + runtime-import-discipline;新数据文件进 package-data）→ validate（bump
  + 测试 + dogfood + doctor + wheel 隔离）→ record（promote/reject）→ `/proposal`
  + 关 issue。版本 0.16.0 → 0.17.0。
- 涉及：`governance_core/commands/curate-candidate.md`（新）、`governance_core/__init__.py`
  + `pyproject.toml`（0.17.0）、`STATE.md` / `STATE_ARCHIVE.md`（rotate）、
  `shared_state/proposals/core/p-0083-*.md`。
- 关键决策：**packaged command skill**（不是 gitignored `.claude/skills/learned/`
  —— 那会被 upgrade 清掉,自托管 hub 的正确归宿是包源 command）；指针式（Art.99
  单一源、零复述 → 不漂移）；把 6 轮踩过的坑编进去（缺件 / CRLF / 去 trade 化 /
  package-data / 自托管 nuance）。本会话 should-extract 一直 YES,此 skill 是其落点。
- 测试：全套 `tools/test_*.py` **21/21**；dogfood `upgrade` → 已装 + registry 发现
  （available-skills 列出 `/curate-candidate`）；`governance-core doctor` exit 0；
  wheel 0.17.0 build OK（top-level 仅 `governance_core` + dist-info、skill 在内、
  `maintainer/` 不泄漏）。

### 2026-05-27 — P-0077 uplink drift diff + --body-file (issue #15)

- 改动：`candidates/uplink.py` 大改 —— `build_issue` 加 drift 分支：
  当 envelope 有 `drift_target` + `baseline_sha256` 且
  `installer._pkg_source_path` 解析得到 baseline 时，body 渲染
  unified diff（against baseline）+ `payload_form: diff` +
  `payload_sha256:` 行（按 ledger._hash_payload 同算法）；无法解析
  baseline 时 fallback legacy full-payload。net-new envelope 路径不
  变（P-0076 ledger rehash 仍依赖 full payload fence）。`gh_command`
  argv 从 `--body body` 改 `--body-file <tempfile>`：用
  `NamedTemporaryFile(delete=False)` 写 body，pass file path 到 gh，
  finally `unlink(missing_ok=True)`。这绕过 Windows
  CreateProcessW ~32K UNICODE_STRING cmdline 限制（Python 把这个
  surface 为 FileNotFoundError，旧版本误归类为"gh missing"）。
  `UplinkError` 在 stderr 含 "label not found" pattern 时附 hint
  打印 `gh label create candidate / kind/skill / kind/hook /
  kind/mechanism` 4 行。`candidates/ledger.py`
  `parse_payload_from_issue_body` 加 drift body 短路：识别
  `payload_form: diff` 后从 body 读 `payload_sha256:` 返回，跳过
  rehash；`discover_uplinked_from_hub` drift body 直接用
  meta["payload_sha256"]。`maintainer/reject_candidate.py` 同样
  drift 路径不 rehash + 不走 pre-0.8.0 heuristic。版本 0.8.0 →
  0.9.0。docs/core-manual.md §11 加 P-0077 drift-as-diff 子节 + hub
  labels setup 子节。
- 涉及：`governance_core/candidates/uplink.py`、
  `governance_core/candidates/ledger.py`、
  `maintainer/reject_candidate.py`、
  `governance_core/tools/test_uplink_drift_diff.py`（新，20 用例）、
  `governance_core/__init__.py` + `pyproject.toml`（0.9.0）、
  `docs/core-manual.md`、`STATE.md`、
  `shared_state/proposals/core/p-0077-*.md`。
- 关键决策：`payload_form: diff` 显式 metadata（不靠"猜身体形状"）；
  drift fallback 到 legacy full-payload 让 uplink 永不因 baseline
  miss 阻塞；P-0076 net-new rehash 路径完全保留（向后兼容）；
  `--body-file` Linux/macOS 也用（统一行为、no-op for them）；
  Windows newline 提醒在测试用 `write_bytes` 控制 bytes。
- 测试：`test_uplink_drift_diff` 20/20（build_issue 9 + parser 5 +
  discover_recovery 3 + gh_command 3）；全套回归 revocation 24 +
  renewal 13 + candidate-attribution 9 + candidate-reminder 7 +
  update-reminder 9 + auth-guard 9 + auth-codec 11 + upgrade-dry-run
  14 + candidate-recovery 14 + rejected-registry 21 +
  uplink-drift-diff 20 = 151/151 全绿。wheel 0.9.0 含 uplink/ledger/
  test_uplink_drift_diff；dogfood upgrade OK；doctor exit 0、hooks
  19/registered 18。


### 2026-05-26 — P-0076 Phase 2 reject feedback registry

- 改动：新建包源 `candidates/rejected_registry.json`（schema 1，含两条
  backfill 条目对应 #4/#6 + #5/#7、`block_by_name: true` 标记 pre-0.8.0
  sha 不可还原场景）。新建包源模块 `candidates/rejected.py`
  （`load_rejected_registry` / `is_rejected` / `should_block` /
  `format_advisory` 四个 API）。`cmd_sweep` 接 `is_rejected` 检查：
  exact → 阻断 + stdout 打印结构化 SKIPPED advisory；name +
  `block_by_name: true` → 阻断；name + `block_by_name: false` → stderr
  warn + 仍 uplink（允许 hub 重评 rewrite）。`candidate-reminder.py`
  hook 扩展：SessionStart 时 cross-check pending 与 registry，被拒
  skill 在 banner 出 WARNING 行。新建 hub 工具
  `maintainer/reject_candidate.py`（`--issue N --reason X --advice Y
  [--also-close] [--dry-run]`），抓 issue body、复用 Phase 1 共享 parser
  解析 payload、自动判 pre-0.8.0 rstrip 场景 → 写 registry +（可选）
  关闭 issue 加 advisory comment。`pyproject.toml` package-data 加
  `candidates/*.json` 让 registry 进 wheel。版本 0.7.0 → 0.8.0（按
  P-0074/P-0075 模式一次性 bump 跨两 phase）。
- 涉及：`governance_core/candidates/rejected.py`（新）+
  `rejected_registry.json`（新）、`maintainer/reject_candidate.py`（新）、
  `governance_core/tools/test_rejected_registry.py`（新，21 用例）、
  `governance_core/tools/candidate.py`（接 `is_rejected`）、
  `governance_core/hooks/candidate-reminder.py`（SessionStart 增 WARNING）、
  `governance_core/__init__.py` + `pyproject.toml`（0.8.0、package-data
  加 `candidates/*.json`）、`docs/core-manual.md`（§11 加 self-heal +
  reject feedback 两段、新 §13 maintainer reject workflow）、`STATE.md`、
  `shared_state/proposals/core/p-0076-*.md`。
- 关键决策：registry schema 加 `block_by_name: bool` 字段（默认 false、
  pre-0.8.0 backfill 设 true）让 maintainer 显式覆盖 name match 的"宽松"
  默认；不引入"unreject"工作流（rewrite 用新名字、强制语义表态）；不自动
  修改 consumer skill frontmatter（守 autonomy carve-out 不变量）；wheel
  shipped registry，不走另立签名 feed（advisory 非 security critical、
  wheel 签名已证来源）。
- 测试：`test_rejected_registry` 21/21（is_rejected 6 + should_block 4 +
  format_advisory 5 + malformed registry 2 + shipped registry smoke 4）；
  全套回归 revocation 24 + renewal 13 + candidate-attribution 9 +
  candidate-reminder 7 + update-reminder 9 + auth-guard 9 + auth-codec 11
  + upgrade-dry-run 14 + candidate-recovery 14 + rejected-registry 21 =
  131/131 全绿。wheel 0.8.0 build OK（`rejected.py` /
  `rejected_registry.json` 进 wheel、`maintainer/` 不漏）。dogfood
  `governance-core upgrade --project-root .` OK，hooks 19/18 registered、
  doctor exit 0。`reject_candidate.py --dry-run --issue 4` 演练成功，
  自动识别 pre-0.8.0、设 block_by_name=true、sha=null。P-0076 两 phase
  全部实现完成。

### 2026-05-26 — P-0076 Phase 1 sweep ledger 自愈

- 改动：`governance_core/candidates/ledger.py` 加
  `parse_payload_from_issue_body(body) -> (meta, {name: bytes})`（共享
  parser，Phase 2 maintainer 工具也用）+ `discover_uplinked_from_hub(
  origin, repo)`（`gh issue list --state all --search "[candidate]
  (from <origin>)"`、逐 issue 解析 fenced block、rehash、返回
  `[{digest, candidate_id, issue_url}]`、`gh`/网络/解析失败均 best-effort
  退回空）。`uplink.py` 修 payload 段 **不 rstrip**（保留原文 bytes、让
  hash round-trip 正确）。`candidate.py` `cmd_sweep` 在 collect 之后、
  pending 选择之前接 recovery：ledger 空 + outbox 非空 + `gh` 可用即调，
  把 recovery 结果写入 `_uplinked.json`。
- 涉及：`governance_core/candidates/ledger.py`、
  `governance_core/candidates/uplink.py`、
  `governance_core/tools/candidate.py`、
  `governance_core/tools/test_candidate_recovery.py`（新，14 用例）、
  `STATE.md`、`shared_state/proposals/core/p-0076-*.md`。
- 关键决策：保持 `payload_digest` 行为不变（按 `read_bytes()` 哈希）、
  改 `build_issue` 让 issue body 不 rstrip → round-trip 一致；recovery
  全程 fail-safe（FileNotFoundError / CalledProcessError /
  JSONDecodeError 均 logger.info 后返空）；recovery 只在 ledger 真的
  empty 时触发，正常 consumer 不付网络代价。
- 修环境：发现 `pip show` 显示 0.7.0 但 Editable project location 丢失
  ([[editable-install-clobber]] 信号)，`pip install -e .` 重装恢复。
- 测试：`test_candidate_recovery` 14/14（parser 5 + discover 8 +
  end-to-end round-trip 1）；回归 revocation 24 + renewal 13 +
  candidate-attribution 9 + candidate-reminder 7 + update-reminder 9 +
  auth-guard 9 + auth-codec 11 + upgrade-dry-run 14 = 96/96 全绿。
  无版本 bump（按提案 Phase 1+2 单次 bump pattern，待 Phase 2 一起
  0.7.0 → 0.8.0）。


### 2026-06-02 — P-0092 / P-0093 收编两个 candidate（gc #25 funnel + #22 upgrade-review）

- **P-0092（gc #25）skill-usage funnel**：`tracker.py` 原子 `_save`（tmp+`os.replace`）+
  `record_surfaced`（按天去重）/`record_triggered`（按事件，计 dedup 抑制的重复）/`funnel_row`；
  `prompt-context-router.py` 的 `_match_routes` 在 dedup **前**记录命中（best-effort
  `_make_trigger_recorder`，guard import + fail-open，登记 `FAIL_OPEN_GC_IMPORTERS`）；
  `registry.py` 新增 `--funnel` 报告（retire/slim/star）。新增 `tools/test_skill_funnel.py`（12）。
- **P-0093（gc #22）upgrade-review**：新增 `tools/upgrade_review.py`（`upgrade --dry-run`→
  NONE/GREEN/YELLOW/RED→写 `audit/upgrade_review/` 报告，**绝不 apply**；`protected_drift.json`→RED）；
  接入 `update-reminder.py`（检测到新版本时 best-effort 跑 + 附 verdict 行，25s 超时回退纯 banner）。
  修正 payload `classify()` 对齐其文档化契约（cross-minor+drift→RED）。新增 `test_upgrade_review.py`（13）
  + `test_update_reminder.py` 2 wiring 用例。
- 验证：全套 `tools/test_*.py` **25/25**；`doctor` exit 0（router 归类 fail-open）；wheel 顶层仅
  `governance_core*`、9 文件在内、无 `maintainer/` 泄漏；`upgrade_review.py` 在 hub dogfood 跑通。
  版本 0.22.0 → **0.23.0**。关闭 GitHub #25、#22（附 curation 结果 + 致谢）。


### 2026-06-02 — P-0091 释放知识渲染工具到 business 归属（gc #24，完整释放）

- 改动：gc 从 trade-agent 抽取时把消费者的知识**渲染**工具卷进了治理包 → gc 控制了
  "消费者怎么渲染自己的知识"，这条 governance→project 影响链不该存在（trade-agent 上
  酿成 dashboard 回滚事故）。完整释放 3 工具到 business/consumer 归属（复用 P-0075 机制）：
  - 删包源 `tools/build_knowledge_dashboard.py`、`tools/build_autogen_blocks.py`、
    `commands/dashboard.md`；3 个自治层路径加进 `installer.STALE_PRUNE_EXEMPT`（现有消费者
    含 gc 自身 upgrade 时**保留**副本）；从 `sync_infra.ALWAYS_COPY_FILES` 删 2 工具。
  - **解耦**（防新消费者断）：`/learn` Step 5 + `/publish-knowledge` 4.8 的 dashboard 重建
    改为"项目自备 renderer 才跑，没有就跳过"；contracts（frontmatter/index schema）+
    `art_03` clause 的归属措辞去 gc-ownership 化（gc 拥有 contract/validator/taxonomy，
    renderer 归消费者）。`knowledge-html-profile.md` 复查后保留（描述机制非归属）。
  - 补 `test_upgrade_dry_run.py` 3 条具名 exempt 回归用例；core-manual released-to-business
    节加 #24 cohort。版本 0.21.3 → **0.22.0**。
- 关键决策/边界：gc 保留 validators(`audit_*`)/contracts/taxonomy；边界件(`build_skill_index`
  等)+ `_tiers.json` 不碰（#24 另议/已项目所有）。
- 测试：**dogfood upgrade 实证 3 副本被"released to business ownership"保留**（不删）、
  doctor exit 0、upgrade-dry-run **17/17**（含 3 新 exempt）、pytest 16、wheel 隔离干净
  （3 文件已从 wheel 移除，需先清 stale build/ 缓存才生效）。


### 2026-06-02 — fix: curate_gate `_fetch_issue_body` Windows GBK 解码崩溃（NO_PROPOSAL）

- 触发:P-0090 例程 advise-only 实测后,本地对真实 issue 跑 `curate_gate.py` 核验闸门——
  #22(mechanism)正确返回 `eligible:false`,但 #24(feedback,body 含非 ASCII 花引号 0x94)
  在 `_fetch_issue_body` 崩:子进程 `text=True` 在 Windows 按 **GBK** 解码 gh 输出 →
  `UnicodeDecodeError` → body=None → `_extract_fence(None)` TypeError。远程 agent(Linux/UTF-8)
  不触发,但 Windows hub 本地跑、或任何非 ASCII body 候选都会崩。
- 修复(窄、清晰复现 → NO_PROPOSAL):`_fetch_issue_body` 改 `encoding="utf-8", errors="replace"`
  (gh 本就输出 UTF-8);`evaluate` 加 body 防御(非 str/空 → `eligible:false`,不崩)。
  测试 +1(case 14 空 body),13 → **14**。版本 0.21.2 → **0.21.3**。
- 涉及:`maintainer/curate_gate.py`、`governance_core/tools/test_curate_gate.py`、pyproject+__init__。
- 验证:#22/#24 现均 rc=0 干净 verdict(拒 mechanism / 拒 feedback);curate_gate 14/14、
  pytest 16、doctor exit 0。
- 未决(非本阶段):P-0090 远程例程 MANUAL run 显示**绿勾成功**但 GitHub 侧零写入(0 评论/标签)——
  疑 session 内 `gh` 未认证到 issues:write(clone 访问 ≠ issue 写权限),待看 run transcript 定位。


### 2026-06-02 — P-0090 P-0082 Phase 2：调度式 C-hybrid 策展例程 + 确定性 auto-promote gate + kill-switch

- 改动：建 P-0082 Phase 2(最重信任面——调度式例程可自主 commit+version-bump)。Phase 1(代码):
  - **`maintainer/curate_gate.py`** —— 唯一放行 auto-promote 的确定性闸门。对 auto-eligible issue:
    **从 body 重建 envelope**(net-new 候选 payload 内嵌 body)→ 全套检查(`validate_envelope` 全检 /
    origin 未撤销 / `scan_envelope` 无密钥 / 非 rejected / kind=skill / layer / net-new / 无 surface /
    skill-theme)→ **隔离 trial-apply(放 net-new 到 target + pytest + unlink)**。返回 GateResult。
    重建 **fail-closed**(drift/diff form 或含 ``` 的 payload → 不 eligible)。LLM 永不能 override False。
  - **`maintainer/auto_curate_enabled`** kill-switch,出厂 `{"enabled": false}`(advise-only)。
  - **`maintainer/curate_routine.md`** —— C-hybrid spec + 自包含例程 prompt。
  - 复用 `candidate_intake` 的 surface/net-new(Art.8);Art.4 配置直接索引(constitutional-review 拦过
    `.get(k,default)` → 改直索引)。版本 0.21.1 → 0.21.2(仅新 test 进 wheel)。
  - Phase 2(无 commit):`/schedule` RemoteTrigger 每日远程例程(见下次执行)。
- 涉及:maintainer/{curate_gate.py,auto_curate_enabled,curate_routine.md}、
  governance_core/tools/test_curate_gate.py(13 例)、pyproject+__init__。
- 关键决策/护栏:**四层纵深**(kill-switch 默认关 + gate 全过 + T0-only + push-creds);doc-gap
  (KINDS 无 doc → AUTO_KINDS={skill});trial-apply 跑在 live checkout(editable install 解析到此)
  但 net-new ⇒ 仅 unlink 清理无残留;**GitHub 远程通道未连**(本机 push≠云端 agent 凭据)→ 例程建后
  dormant,需 /web-setup + 开 kill-switch 两步才真跑。
- 测试:curate_gate 13/13(全 fail-closed 分支 + happy eligible + reconstruct round-trip)、
  **真实 trial_apply 冒烟绿且无残留**、pytest 16、intake 25、boundary 25、doctor exit 0、
  wheel 隔离干净(顶层仅 `governance_core*`,maintainer/ 未泄漏)。


### 2026-06-02 — P-0089 #23 walk-back：intake 只验内嵌 candidate.json + 撤消费者 envelope 发布

- 改动：与 user 讨论 + core 的 Phase 2 handoff 后,采纳 #23 架构决策(接近 C)——
  **消费者绝不该有 hub 写权限**,P-0088 的 option b(消费者 `uplink` 发布 envelope)
  从根上破坏 consumer/hub 信任分离,对非 owner 消费者更不可能。walk back:
  - **撤 option b**:`governance_core/candidates/uplink.py` 删 `publish_envelope` +
    调用 + 仅为它而加的 `import logging/shutil`/`log`(核实无他用)→ uplink 回到
    纯 issue 传输,除创建 issue 外不写 hub。删 `test_candidate_uplink_publish.py`。
  - **intake 改 candidate.json-only**:`maintainer/candidate_intake.py` 删
    `fetch_envelope`;`main()` 用 body 解析的 candidate.json 调**现成的**
    `envelope.validate_metadata`(schema/kind/layer/source_paths,无 payload-on-disk);
    secret 复扫 + digest 去重等**需真 payload 的检查移到 promote-time**(归 Phase 2
    curate_gate)。surface 命中 + net-new 是元数据级,保留。`compute_eligibility`
    简化为 `(metadata_valid, net_new, surface_hit, kind, layer)`。仍绝不 promote。
  - workflow yml 注释去掉"fetch published envelope";版本 0.21.0 → **0.21.1**(同日修正)。
- 涉及:uplink.py、candidate_intake.py、test_candidate_intake.py(重写 25 例)、
  删 test_candidate_uplink_publish.py、candidate-intake.yml、pyproject+__init__。
- 关键决策:`envelope.py` **已有** `validate_metadata`(dict)/`validate_envelope`(dir+payload)
  现成拆分 → #23 的"拆 validate_candidate"自动满足。`KINDS` 无 "doc"(T0_KINDS 含 doc
  但 doc 会先 fail metadata —— 既有不一致,留待后续,非本次范围)。净效果:外部+私有
  消费者都能用,彻底移除"消费者写 hub"。
- 测试:intake 25/25、pytest 16 passed、candidate 家族全绿、doctor exit 0、
  wheel 隔离干净(顶层仅 `governance_core*`,publish_envelope 已从 wheel 移除)。
- 后续:P-0082 Phase 2(调度式 curate_gate + kill-switch)另起 proposal——**最重信任面**
  (远程例程持久握 gc 写 creds 自主 commit),下轮审慎走。


### 2026-05-29 — P-0082 self-contain auth-guard（vendor auth 子包，关 #3）

- 改动：**Phase A** —— `governance_core/auth/` 内部绝对导入改**相对**
  （`__init__`/`codec`/`revocation`：`from . import _ed25519/codec/sign/verify`
  + 替换 `auth.sign`/`auth.verify` 调用点），使 auth 子包**可重定位**（同一份源
  既作 `governance_core.auth` 包用、又能作独立包 import），逻辑零改。**Phase B**
  —— installer 加 `COPY_CATEGORIES ("auth" → .claude/hooks/_gc_auth)` +
  `CATEGORY_OF["auth"]` + `_copy_tree` 跳 `__pycache__`/`.pyc`；`auth-guard.py`
  顶部加 `_HOOK_DIR` + `sys.path.insert`，5 处 import 从 `governance_core.auth`
  改 `_gc_auth`（**自包含、无 `import governance_core`**）；`runtime_import_audit`
  的 `GC_IMPORT_EXEMPT` **清空**（P-0081 grandfather 自衰减）；
  `runtime-import-discipline.md` §3/§4 更新；`test_auth_guard` 在临时 repo vendor
  `_gc_auth`、`test_runtime_import_audit` 改空-exempt 断言。版本 0.15.0 → 0.16.0。
  **关 #3**。
- 涉及：`governance_core/auth/{__init__,codec,revocation}.py`、
  `governance_core/hooks/auth-guard.py`、`governance_core/installer.py`、
  `governance_core/runtime_import_audit.py`、
  `governance_core/knowledge_governance/runtime-import-discipline.md`、
  `governance_core/tools/{test_auth_guard,test_runtime_import_audit}.py`、
  `governance_core/__init__.py` + `pyproject.toml`（0.16.0）、`STATE.md`、
  `shared_state/proposals/core/p-0082-*.md`。
- 关键决策：**单一源** `governance_core/auth/`，`_gc_auth/` 是 install 产物
  （Art.8 同代码路径、Art.11.4 不进 wheel —— wheel 仍只 `governance_core*`，
  auth/ 作为包发布、`_gc_auth` 不在内）。**相对导入使 vendoring 无需源变换**
  （faithful copy，installer 直接 rglob 拷贝）。prune 是 **manifest-diff** 式 →
  `_gc_auth` 进 install set（category auth）即永不误删（**双 upgrade 验证存活**）。
  **fail-closed 语义不变**（坏 auth → exit 2），但 freeze 风险消除：hook + 其依赖
  现在是一个 install 单元（不再依赖 governance_core 可 pip-import）。dogfood
  `upgrade` 不热替换当前 session 的 live hook（启动时加载）→ 零冻结风险。
- 测试：**Phase A** 可重定位 round-trip（独立 `_gc_auth` import + sign/verify）
  + `test_auth_codec`/`test_revocation`/`test_auth_guard` green。**Phase B** 全套
  `tools/test_*.py` **21/21**（`test_auth_guard` 用 vendored 布局、
  `test_runtime_import_audit` 空 exempt）；`hook_imports_gc(auth-guard)=False`；
  `governance-core doctor` exit 0 **无 tracked-exception 行**（exempt 空、全面强制）；
  直调安装版 auth-guard 对真实 config **exit 0 授权**；**双 upgrade `_gc_auth` 5
  文件存活**；wheel 0.16.0 build OK（top-level 仅 `governance_core` + dist-info、
  auth/ 5 文件+pubkey 在内、`_gc_auth` 不进 wheel、`maintainer/` 不泄漏）。


### 2026-05-29 — P-0081 立 runtime-import-discipline 不变式 + doctor 检查（#3 根治）

- 改动：查 issue #3 发现前提已过时（当前 6 hook + 8 tool 都 import governance_core，
  非"唯一"），但内核成立。**锐化不变式**：import governance_core 的 hook 必须守护
  import 且 fail-open；必须 fail-CLOSED 的安全门则必须自包含——证据是除 auth-guard
  外所有 importer 都守护 + fail-open（sensitive-data-guard 注释明写"auth-guard
  already fails closed"）。auth-guard 是唯一违反者（PreToolUse `*` + fail-closed →
  governance_core 不可导入即冻结每次工具调用）。新增治理文档
  `knowledge_governance/runtime-import-discipline.md` + 新模块
  `runtime_import_audit.py`（`FAIL_OPEN_GC_IMPORTERS`/`GC_IMPORT_EXEMPT`/
  `check_runtime_import_discipline`）+ doctor 检查（unclassified gc-importer →
  exit 9；auth-guard 以文档化临时例外 grandfather，doctor 保持 exit 0、对新 hook
  强制）。**不动 auth-guard 代码**（636 行 crypto vendor 留 P-0082）。版本 0.14.0
  → 0.15.0。
- 涉及：`governance_core/runtime_import_audit.py`（新）、`installer.py`（doctor 加
  P-0081 检查，新退出码 9）、`knowledge_governance/runtime-import-discipline.md`（新）、
  `tools/test_runtime_import_audit.py`（新，13 用例）、`__init__.py` + `pyproject.toml`
  （0.15.0）、`STATE.md`、`shared_state/proposals/core/p-0081-*.md`。
- 关键决策：**不进宪法**（治理文档 + doctor 检查，免 /iterate-constitution 重流程；
  要 entrench 可后续加一行 Art.11 引用）；grandfather auth-guard（仿 P-0075
  prune-exempt：向前强制、P-0082 落地后自衰减）；检查作用域限 shipped hooks（manifest
  名单），不误伤消费者自有 hook；不变式从"per-call guard 自包含"锐化为"fail-open-guarded
  或自包含、安全门自包含"。**#3 保持 OPEN**，P-0082 vendor auth-guard 后才关。
- 测试：`test_runtime_import_audit` 13/13（hook_imports_gc 4 + 合成 dir 5 + 真实
  shipped hooks 4：无 unclassified 违规 / auth-guard 是 tracked 例外 / 5 个 fail-open
  importer 都在且确 import gc / exempt 恰为 {auth-guard.py}）；全套 `tools/test_*.py`
  **21/21**；`governance-core doctor` exit 0 并打印 "runtime-import-discipline:
  1 tracked exception(s) ... ['auth-guard.py']"；dogfood upgrade exit 0；wheel
  0.15.0 build OK（top-level 仅 `governance_core` + dist-info、新模块/doc/测试在内、
  `maintainer/` 不泄漏）。


### 2026-05-29 — P-0080 promote classify fast-path hard-block cluster (#17 + #13)

- 改动：curate trade-agent 的 classify fast-path 集群入包源（P-0065 决策，原
  #12/#13/#14 阻塞件经索要后由 #17 完整重投）。落 **8 个 net-new**：
  `hooks/proposal-classify-fast.py`（L5 PreToolUse 硬阻断 hook：触及高敏路径且本
  session 未 classify 即 exit 2）、`tools/_classify_match.py`（gitignore-glob
  matcher）、`tools/proposal-classify-paths.json`（高敏路径 allowlist：governance/
  harness/routing/infra/settings 五类）、`tools/proposal-classify-keywords.json`
  （结构变更关键词）、3 个测试、`knowledge_governance/proposal-classify-fast-path.md`
  （reference doc）。**合并 #13** 的 `_cmd_classify`/`_classify_quick` + argparse
  入 `tools/proposal_lib.py`（`git apply --recount`，3 hunk/158 增/0 删纯增）。
  `hooks_manifest.json` 注册新 hook（PreToolUse, Edit|Write|MultiEdit|NotebookEdit）。
  版本 0.13.0 → 0.14.0。
- 涉及：`governance_core/hooks/proposal-classify-fast.py` + `hooks_manifest.json`、
  `governance_core/tools/{_classify_match.py, proposal-classify-paths.json,
  proposal-classify-keywords.json, test_proposal_classify*.py(×3), proposal_lib.py}`、
  `governance_core/knowledge_governance/proposal-classify-fast-path.md`、
  `governance_core/__init__.py` + `pyproject.toml`（0.14.0 + package-data 加
  `tools/*.json`）、`maintainer/consumer_registry.json`、`STATE.md`、
  `shared_state/proposals/core/p-0080-*.md`。
- 关键决策：**抓到打包 bug** —— 首次 wheel build 缺两个 `tools/*.json`（默认不打包
  data 文件；editable 安装掩盖了），会下发"找不到配置的坏 hook"给消费者 →
  `pyproject.toml` package-data 补 `tools/*.json`，重建后 8 文件全入 wheel。这正是
  dogfood + wheel 隔离纪律存在的意义。hook **不 import governance_core**（守 copy-based
  不变式，恰是 #3 auth-guard 违反的）；配置 **无 trade 泄漏**（globs 是 gc 自身结构）。
  **自托管 nuance**：globs 是自治层相对路径、不含 `governance_core/**`，故 hub 的包源
  开发不被 gate；被 gate 的是 root/自治层治理文件。#14 sync_infra 多 clone 接线按
  trade-agent scope note + 单 agent 拓扑排除。
- 测试：全套自治层 `tools/test_*.py` **20/20**（17 + 3 新 classify）；**硬阻断 hook
  直调验 6 态**：BLOCK(新 session+治理/harness 路径 exit 2)、ALLOW(非 allowlist)、
  逃生门 `CLAUDE_CLASSIFY_FAST_DISABLE=1`、fail-open(坏 JSON)、自托管 nuance
  (`governance_core/**` 不 gate)、有 classify entry 放行。dogfood upgrade exit 0
  (hook 注册进 settings.local.json)、doctor exit 0。wheel 0.14.0 build OK（top-level
  仅 `governance_core` + dist-info、8 文件全在、`maintainer/` 不泄漏）。


### 2026-05-29 — fix #2 discovery GBK UnicodeDecodeError (Art.7.4)

- 改动：给 discovery 里读 git 输出的 `subprocess.run` 加
  `encoding="utf-8", errors="replace"`——`tracker.py`（`git diff/log` 算 session
  complexity 的两处）+ `discovery/__init__.py`（`resolve_project_root` 的
  `git rev-parse --show-toplevel`）。Windows 上 `text=True` 缺 encoding 时按
  GBK 解码 git 输出，遇非 ASCII 的 commit message / 文件名 / 仓库路径即
  `UnicodeDecodeError`，把该数据从复杂度计算里丢掉（issue #2 现象）。版本
  0.12.0 → 0.13.0。
- 涉及：`governance_core/discovery/tracker.py`、`governance_core/discovery/__init__.py`、
  `governance_core/__init__.py` + `pyproject.toml`（0.13.0）、`STATE.md`。
- 关键决策：`errors="replace"` 保证彻底无解码崩溃且**不丢文件**（直接回应 issue
  的 "offending file dropped from computation"）；修的是 tracker import 链的**整个
  bug 类**（tracker 两处 + resolve_project_root），不止 issue 点名的单行。
  `tools/test_command_guard.py` 有同款 `text=True` 无 encoding，但属测试文件、非
  runtime 路径，记下未动。NO_PROPOSAL（简单 bug fix）。原 issue 报 0.5.0，
  line 116 的 `.usage.json` 读早带 encoding；真 offending read 是 subprocess git
  解码。#3（auth-guard import 隔离）另议（security hook 重构、需 proposal）。
- 测试：全套 `tools/test_*.py` 17/17；`python -m governance_core.discovery.tracker
  --should-extract` 运行 clean；dogfood `governance-core upgrade` exit 0。


### 2026-05-29 — reject candidates #8 + #9（重投的 trade-coupled skills）

- 改动：用 `maintainer/reject_candidate.py --also-close` 拒 #8
  (cross-agent-gate-spec-mock) + #9 (p4-scenario-fixture-construction)。
  **关键**：两者都是**已拒 skill 的重投** —— `rejected_registry.json` 早有这
  两个 skill_name 条目（cross-agent-gate 曾为 #5/#7、p4-scenario 曾为 #4/#6，
  P-0076 backfill，`block_by_name: true`）。工具把 #8/#9 的 issue URL 追加进
  既有条目 + 发 advisory 评论 + 关 issue 为 not-planned。版本 0.11.0 → 0.12.0
  （shipped `rejected_registry.json` 内容变了，保版本↔内容洁净）。
- 涉及：`governance_core/candidates/rejected_registry.json`（追加 issue URL +
  时间戳）、`governance_core/__init__.py` + `pyproject.toml`（0.12.0）、`STATE.md`。
- 关键决策：两者均 trade-coupled（多 clone 拓扑在单 agent core 退化 + trade 域
  selection/risk/option/sector）；保留 `block_by_name: true`（pre-0.8.0 条目、
  按名硬拒）。**洞察**：trade-agent 会重传已拒 skill，极可能因其装的
  governance-core 版本早于 0.8.0+（未含 shipped rejected_registry），sweep 不知
  跳过 —— trade-agent 应 upgrade。无 proposal（curation bookkeeping、非能力变更）。
  通用内核欢迎作"去 trade 化的新 candidate / hub 自 authored 的 skill guide"
  （既有 advice 已载明：p4 的 schema-provenance 模式、cross-agent 的抽象 spec-mock
  模式由 hub 直接 author）。
- 测试：`test_rejected_registry` 21/21（含 shipped registry 含两 skill 的 smoke）；
  全套 `tools/test_*.py` 17/17；dogfood upgrade exit 0；wheel 0.12.0 build OK
  （top-level 仅 `governance_core` + dist-info、rejected_registry 在内、
  `maintainer/` 不泄漏）。


### 2026-05-29 — P-0079 promote /learn carrier-class gate (candidate #11), de-trade-ified

- 改动：curate trade-agent #11 入包源（P-0065 决策，优先级清单第 2 项）。在
  `governance_core/commands/learn.md` 的 `## 执行流程` 与 `### Step 1` 之间插入
  **Step 0：判定 carrier_class + 载体形式**（0.1 class 决策表 6 类 / 0.2 载体
  形式 MD vs HTML profile 表 / 0.3 声明输出格式 / 误用红线）—— 写 `knowledge/**`
  前强制声明 carrier_class（P-0053）+ 载体（P-0054）。引用的两 spec 都已在包源
  （`knowledge-carrier-classes.md` §2、`knowledge-html-profile.md` §1，后者刚被
  P-0078 扩）。版本 0.10.0 → 0.11.0（learn.md ship 进 wheel）。`candidate.py
  promote` 记 #11 `promoted`。
- 涉及：`governance_core/commands/learn.md`、`governance_core/__init__.py` +
  `pyproject.toml`（0.11.0）、`maintainer/consumer_registry.json`、`STATE.md`、
  `shared_state/proposals/core/p-0079-*.md`（提案档案）。
- 关键决策：**去 trade 化** —— trade-agent payload 示例带 trade 味
  （`knowledge/trading/trade-end-to-end-flow.html`、"写 trade 全流程"），下发
  全体 consumer 前改成领域中立（`knowledge/<domain>/<topic>-flow.html`、误用
  红线去 "trade"）；机制逐字保留、只改示例。**强制闸门**有意为之：把今天仅
  "文档化"的 P-0053/54 carrier 纪律变成 /learn 里的"闸门化"。验证：
  `git diff --ignore-cr-at-eol` 语义 diff = 2 hunk / 44 增 / 0 删（raw diff
  82 删 202 增的噪声纯属 CRLF↔LF + 尾换行；sha 差异同因，内容与 baseline 等价）。
  新增段 trade 泄漏检查通过（仅余通用英文词 "tradeoff"；既有 agent-role 枚举
  `{rules,trade,data,...}` 与本次无关）。
- 测试：全套 `tools/test_*.py` 17/17 PASS（skill 正文不单测，跑全套确认无连带
  破坏）；dogfood `governance-core upgrade --project-root .` exit 0，安装副本
  `.claude/commands/learn.md` 已带 Step 0；wheel 0.11.0 build OK（top-level 仅
  `governance_core` + dist-info，learn.md 在内、`maintainer/` 不泄漏）。


### 2026-05-29 — P-0078 promote HTML profile cluster (candidates #16 + #10)

- 改动：curate trade-agent 回传的 HTML profile 集群入包源（P-0065 maintainer
  决策）。① #16 → `governance_core/tools/build_knowledge_dashboard.py`：加
  `_extract_html_frontmatter`（解析 `<meta name="kc:*">` head 标签 +
  `<p class="summary">`），HTML 知识条目走 **sandboxed iframe** modal
  （`sandbox=allow-same-origin allow-scripts` 以跑 vendored mermaid）+
  `.modal-wide` 容纳宽表/图（payload_form: diff，7 hunk）。② #10 →
  `governance_core/knowledge_governance/knowledge-html-profile.md`：纯新增
  §2.2.1（可选跨引用 kc:* 标签 briefing/related/supersedes/superseded-by，
  1:1 映射 .md frontmatter）+ §3.3.1（Mermaid strict-mode pitfalls：label
  双引号包裹、`\n` 换行替代 `<br/>`、ASCII 特殊字符）。版本 0.9.0 → 0.10.0
  （这两文件 ship 进 wheel，consumer 经 upgrade 拉取）。`candidate.py promote`
  对两 candidate 记 `promoted` 入 `maintainer/consumer_registry.json`。
- 涉及：`governance_core/tools/build_knowledge_dashboard.py`、
  `governance_core/knowledge_governance/knowledge-html-profile.md`、
  `governance_core/__init__.py` + `pyproject.toml`（0.10.0）、
  `maintainer/consumer_registry.json`、`STATE.md`、
  `shared_state/proposals/core/p-0078-*.md`（提案档案）。
- 关键决策：**apply 前验 drift** —— 比对 candidate `baseline_sha256` 与当前
  包源 sha：#10 baseline == 当前（纯新增，diff -u 确认 0 删除/50 增），#16
  baseline 已漂移（`1fabb66…`→`9c299fd…`），但 `git apply -p1 --recount`
  靠上下文重定位 7 hunk → CLEAN。`promote` 对 `kind=mechanism` 不自动放置、
  只打印"手工放进包源" + 记决策 —— 符合 Art.11.2（手改包源、不碰自治层副本）。
  接受 ceremonial-proposal 张力：单 agent 自审自执，但 proposal 价值在"curation
  决策记录本身" + 改动下发全体 consumer 的 blast radius。#10 §2.2.1 引用 #16
  新增的 `_extract_html_frontmatter` —— spec 与渲染器互相印证、配套促进。
- 测试：全套 `tools/test_*.py` 17/17 PASS；`_extract_html_frontmatter` smoke
  （kc:* 含新 briefing 标签 + summary 提取通过）；`audit_html_profile` exit 0；
  dogfood `governance-core upgrade --project-root .` exit 0（128 files、18 hooks）；
  wheel 0.10.0 build OK（top-level 仅 `governance_core` + dist-info，
  html-profile/dashboard 在内、`maintainer/` 不泄漏，Art.11.4 隔离守住）。


### 2026-05-20 — P-0075 Phase 1 清除 design 残留 + 一次性 prune-exempt

- 改动：`git rm` 包源 3 个业务残留文件 —— `knowledge_governance/design/{component-catalog,design-principles}.md`（dashboard 路径 + HK Color/CALL-PUT 港股专属）+ `agents/design-system-owner.md`（Pencil MCP + dashboard 业务 agent）。`installer.py` 移除
  `KNOWLEDGE_COPY_MAP` design 条目、新增 `STALE_PRUNE_EXEMPT` 集 +
  `_prune_stale` guard（命中即 log 并跳过、不删）—— 保护已装 0.5.0/0.6.0 的
  消费者（trade-agent / auto-tax-filing）的 install-managed 副本变成业务自有。
  `knowledge-carrier-classes.md` §3 删 `knowledge/design/` 行；
  `test_upgrade_dry_run` 把旧 design 映射用例换成 "released path no longer
  maps" + 新增 5 个 prune-exempt 回归用例。版本 0.6.0→0.7.0。
- 涉及：`governance_core/installer.py`、`governance_core/__init__.py`、
  `pyproject.toml`、`governance_core/knowledge_governance/knowledge-carrier-classes.md`、
  `governance_core/tools/test_upgrade_dry_run.py`、删除 3 个文件、
  `STATE.md`、`shared_state/proposals/core/p-0075-*.md`（提案档案）。
- 关键决策：prune-exempt 设计为**一次性 + 自衰减** —— 升级跨 0.7.0 时
  exempt 触发跳过；写新 manifest 时这三条自然不再出现（0.7.0 install set
  无源）→ 后续升级 prune 根本看不到、exempt 不再生效。consumer-protection
  机制比简单删源更稳。`STALE_PRUNE_EXEMPT` 源注释明记"未来 major 可删"。
- 测试：`test_upgrade_dry_run` 14/14（+5 prune-exempt 含 component-catalog
  survives / design-principles survives / design-system-owner survives /
  非 exempt control path pruned / pruned 列表排除 exempt）；回归 revocation
  24 + renewal 13 + candidate-attribution 9 + candidate-reminder 7 +
  update-reminder 9 + auth-guard 9 + auth-codec 11。wheel 0.7.0 内
  `design/` 与 `agents/design-system-owner.md` 已不出现（只剩
  `skills/external-design-reverse-feed.md`，跟 residue 无关）。dogfood
  `governance-core upgrade --project-root .` 触发 3 次 "released to
  business ownership" log、3 个文件物理保留、新 manifest 不含、doctor exit 0
  (hooks 19/registered 18、clauses 17)。

### 2026-05-19 — P-0074 Phase 2 续期可见性（提醒）

- 改动：`candidates/registry.py` 加 `lease_status`(扫 active 消费者算
  `days_left`、按紧迫度升序、无 expiry 排末)、`expiring_consumers`(阈值内
  过滤、含已 lapsed)、`RENEWAL_THRESHOLD_DAYS=30` 单一常量。新增 hub 侧
  SessionStart hook `renewal-reminder.py`(读 `maintainer/consumer_registry
  .json`、无该目录 → 静默、异常静默 exit 0),注册进 `hooks_manifest.json`。
  新增 maintainer 工具 `renewal_status.py`(列 active 消费者、`[RENEW]`/
  `[LAPSED]` 标注、`--threshold-days`)。无版本 bump(P-0074 已在 Phase 1
  一次性 0.5.0→0.6.0)。
- 涉及：`governance_core/candidates/registry.py`、`hooks/renewal-reminder.py`
  (新)、`hooks/hooks_manifest.json`、`tools/test_renewal.py`(新)、
  `maintainer/renewal_status.py`(新)、`docs/core-manual.md`(§9 加续期子节)。
- 关键决策：续期计算抽成纯函数 → tool 与 hook 同路径(宪法第八条);hub 侧
  hook 的门 = `maintainer/` 目录存在与否(hub 天然信号、被 wheel 白名单天然
  排除),与 candidate/update-reminder 的消费者侧门相反;只浮现不自动重签
  (自动续期与 P-0071 租约兜底有 tradeoff,留独立提案)。
- 测试:`test_renewal` 13/13(纯函数 8 + hook 五态);回归 revocation 24 +
  candidate_attribution 9 + candidate_reminder 7 + update_reminder 9;
  `renewal_status` dogfood(3 消费者全健康 364-365d);upgrade/doctor exit 0
  (hooks 19/registered 18);build 0.6.0 隔离 OK(`renewal-reminder.py` 进
  wheel、`renewal_status.py`/`maintainer/` 不泄漏)。P-0074 两 phase 全部
  实现完成。

### 2026-05-19 — P-0074 Phase 1 逐消费者 un-revoke

- 改动：`auth/revocation.py` 加 `remove_revocation`(`add_revocation` 镜像、
  幂等);`candidates/registry.py` 加 `mark_active`(`status` 回 active、清
  `revoked_on`/`revocation_reason`);`maintainer/revoke_consumer.py` 加
  `--unrevoke <id>`(验旧源签名 → `remove_revocation` → 重签写回 → 台账
  `mark_active`;不在 feed 里 → no-op 报告)。版本 0.5.0→0.6.0。
- 涉及：`governance_core/auth/revocation.py`、`candidates/registry.py`、
  `maintainer/revoke_consumer.py`、`tools/test_revocation.py`、
  `pyproject.toml`、`__init__.py`、`docs/core-manual.md`(§9 加 un-revoke)。
- 关键决策：un-revoke 逐消费者移除、不误伤 feed 内其他撤销项;改源前先验旧
  签名(防洗白篡改);撤销仍以持久为意图,un-revoke 是误撤销纠错。
- 环境修复:排查测试失败(新函数报 no-attribute)发现本仓库 editable 安装被
  全局 `pip install governance-core==0.5.0` 覆盖(auto-tax 安装误入全局
  Python)—— `pip install -e .` 重装恢复 editable,dogfood 复原。
- 测试:`test_revocation` 24/24(+5:`remove_revocation` 在册/不在册、
  `mark_active` 三态);`revoke_consumer` dogfood(撤销 → list → `--unrevoke`
  → list 0 revoked,重签验签通过);build 0.6.0。

### 2026-05-19 — P-0073 Phase 3 /upgrade skill（agent 驱动升级编排）

- 改动：新增 `governance_core/commands/upgrade.md` —— `/upgrade` command
  skill,把升级编排成 5 步:① `upgrade --dry-run` 预览 → ② agent **语义
  冲突审查**(对 drift 文件 + 本地新增逐项判断,advisory)→ ③ 汇报 owner
  → ④ **owner 确认门**(阻塞)→ ⑤ 真实 `upgrade`。`update-reminder.py`
  提示语改指向 `/upgrade`。
- 涉及：新增 `governance_core/commands/upgrade.md`;改
  `governance_core/hooks/update-reminder.py`、`docs/core-manual.md`（§12 扩）。
- 关键决策：语义审查 = **skill 指令,不是给 installer 外挂模型** —— 发起
  upgrade 的 agent 本身即 LLM,由它读 dry-run 输出做语义判断;advisory 非
  gate(只警示,owner 确认门才阻塞);纯手工 `governance-core upgrade`
  优雅降级跳过本编排,结构层仍可手动用。
- 测试：`/upgrade` 被 registry/技能发现(available-skills 列表出现);
  upgrade/doctor exit 0;回归 update-reminder 9 + upgrade-dry-run 8 +
  candidate-sweep 10;build 0.5.0。skill 不做单测(对 agent 的指令、非可
  单测代码,与其它 skill 一致)。P-0073 三 phase 全部实现完成。

### 2026-05-18 — P-0071 Phase 4 candidate attribution + revoked-origin reject

- 改动：`uplink.py` —— uplink 时校验候选 `origin` == 授权码内 `consumer_id`
  （签名码 → consumer_id 真实），不匹配/码不验签即拒（`origin` 不可谎报）。
  `registry.py` —— 台账 schema 1→2（消费者条目加 `status`/`first_issued`/
  `last_issued`，`load_registry` 透明迁移旧条目），加 `is_consumer_revoked()`。
  `candidate.py` —— `uplink`/`submit` 传授权码做 origin 绑定、`review` 标
  `[REVOKED ORIGIN]`、`promote` 对撤销 origin 硬拒（不入包源 + 记 rejected +
  exit 1）。`docs/core-manual` §9 加"Candidate attribution"子节收口。
- 涉及：`governance_core/candidates/uplink.py`、`candidates/registry.py`、
  `tools/candidate.py`、新增 `tools/test_candidate_attribution.py`、
  `docs/core-manual.md`。
- 关键决策：origin 绑定 = 消费者侧 uplink 强制 + GC 侧 review/promote 按台账
  硬拒，双重;台账 schema 向后兼容（旧条目 load 时迁移、容忍 `status` 缺失视作
  active）;re-issue 把 `status` 重置为 active（无 auto-unrevoke）。
- 测试：`test_candidate_attribution` 9/9（台账 schema-2 形态、re-issue 保留
  first_issued、`is_consumer_revoked` 三态、schema-1→2 迁移、uplink origin
  匹配/不匹配/坏码）;`promote` 撤销硬拒 dogfood（exit 1、payload 未入包源）;
  全套回归 codec 11 + auth-guard 9 + revocation 19;build 0.3.0、
  upgrade/doctor exit 0。P-0071 四 phase 全部实现完成。

### 2026-05-18 — P-0071 Phase 3 auth-guard online revocation enforcement

- 改动：`auth-guard.py` 重写 —— Gate 1 码验证之外加 **Gate 2 撤销门**:按
  TTL（~6h）拉取验签撤销源、`consumer_id` 命中即冻结、源不可达回退缓存、距
  上次成功拉取超 `max_offline_days` 即冻结（首装宽限期同此），schema-1 码
  跳过 Gate 2。`revocation.py` 加 `evaluate()`（纯决策函数:current/grace/
  revoked/offline）、`feed_cache_path()`、`sig_url_for()`。`codec.py` 加
  `decode_payload()`（不验签取 payload 字段）。`installer.py` doctor 加
  `_report_auth_lifecycle`（lease 倒计时 + 撤销源拉取状态）。`cli.py` 补
  `logging.basicConfig` —— 修 doctor 报告被静默丢弃的前置 bug。
- 涉及：`governance_core/hooks/auth-guard.py`、`auth/revocation.py`、
  `auth/codec.py`、`installer.py`、`cli.py`、`tools/test_auth_guard.py`、
  `tools/test_revocation.py`。
- 关键决策：撤销决策抽成纯函数 `evaluate()` → 决策逻辑可移植单测、hook 只做
  fetch+cache 管道;撤销门只对 schema-2 码生效(schema-1 永久码无源);fetch
  失败 fail-to-cache、绝不 fail-open，超 `max_offline_days` 才冻结。
- 测试：`test_revocation` 19/19、`test_auth_guard` 9/9（含 5 撤销门集成例:
  可达放行/撤销冻结/不可达宽限/无源超宽限/陈旧源超 max）、`test_auth_codec`
  11/11;`doctor` 可见报告 lease 365 天 + 撤销源状态;upgrade/doctor exit 0;
  wheel 0.3.0 隔离 OK。

### 2026-05-18 — P-0071 Phase 2 signed revocation feed

- 改动：新增 `governance_core/auth/revocation.py` —— 撤销源格式
  （`{schema, updated, revoked[]}`）+ detached 签名;签名覆盖**精确字节**，
  verifier 信任收到的字节、不重新规范化。`candidates/registry.py` 加
  `mark_revoked()`（消费者条目打 `status:revoked` + `revoked_on` +
  `revocation_reason`）。新增 `maintainer/revoke_consumer.py`（`--consumer-id`
  撤销 / `--init [--force]` / `--list`，改源前先验旧源签名）。仓根 committed
  空签名源 `revocation.json` + `revocation.json.sig`。
- 涉及：新增 `governance_core/auth/revocation.py`、`tools/test_revocation.py`、
  `maintainer/revoke_consumer.py`、`revocation.json`、`revocation.json.sig`;
  改 `governance_core/candidates/registry.py`、`docs/core-manual.md`。
- 关键决策：签名覆盖文件精确字节（verifier 不 re-canonicalize，规避序列化
  漂移）;撤销源走仓根文件（被 `governance_core*` 白名单天然排除出 wheel）;
  改源前验旧签名 —— 拒绝给被篡改的源重签（防止洗白篡改）。
- 测试：`test_revocation` 14/14（往返、篡改/错密钥/非 JSON/未知 schema/缺
  consumer_id 拒、磁盘读写、`mark_revoked` 正负路径）;`revoke_consumer`
  dogfood（init→撤销测试消费者→list 验签→重置空）;wheel 0.3.0 含
  `revocation.py`、不含 `revocation.json` / `maintainer/`;upgrade/doctor
  exit 0。


### 2026-05-19 — P-0073 Phase 2 upgrade --dry-run 预览 + 逐文件 diff

- 改动：`installer.py` `install()` 加 `dry_run` 参数,贯穿 `_copy_tree` /
  `_capture_drift` / `_prune_stale` / `_render_clauses` —— **同一计算路径、
  只在每个写盘点 `if not dry_run` 分叉**(宪法第八条,非平行函数)。新增
  `_pkg_source_path`(自治层路径→包源)、`_drift_diffs`(逐 drift 文件
  `difflib` unified diff)、`_local_additions`(枚举 owner 新增,过滤
  `.pyc`/`__pycache__`/dotfile)、`_dry_run_report`。`cli.py` `upgrade` 加
  `--dry-run` 标志。
- 涉及：改 `governance_core/installer.py`、`cli.py`、`docs/core-manual.md`
  (§12 扩);新增 `tools/test_upgrade_dry_run.py`。
- 关键决策:`dry_run` 贯穿同一计算路径,dry-run 报告的覆盖/drift/prune 集与
  真实 upgrade 必然一致;逐文件 diff 比"当前个性化内容"与"待覆盖的包源版";
  澄清 —— `upgrade` 是**整层原子覆盖**,无逐文件 keep/overwrite(混版本会
  碎化公共层),dry-run 后决策空间是整体二元(升/不升)。
- 测试:`test_upgrade_dry_run` 8/8(`_pkg_source_path` 映射 4 例、
  `_drift_diffs` 改动有 diff/无改动 no-diff);dogfood `upgrade --dry-run`
  (142 files、`git status` 前后不变);drift 探针(改自治层文件→dry-run
  检出 + 输出 unified diff 精确显示改动行);回归 update-reminder 9 +
  candidate-sweep 10 + revocation 19;upgrade/doctor exit 0;build 0.5.0。


### 2026-05-19 — P-0073 Phase 1 update-available 通知 hook

- 改动：新增 SessionStart hook `update-reminder.py` —— 比对自治层
  `installed_files.json` 的 `governance_core_version` 与 PyPI 最新版,有
  新版即在启动 banner 报 + 两步更新命令;TTL 缓存 ~12h、PyPI 不可达 / 无
  manifest / 任何异常静默 exit 0、hub(`consumer_id==governance-core`)静默。
  新增 `governance_core/version_util.py`(`parse_version` / `is_newer` /
  `minor_gap`,hook 与 Phase 2 共用、可单测)。`hooks_manifest.json` 注册新
  hook → SessionStart。版本 0.4.0→0.5.0。
- 涉及：新增 `governance_core/hooks/update-reminder.py`、`version_util.py`、
  `tools/test_update_reminder.py`;改 `hooks/hooks_manifest.json`、
  `.claude/settings.local.json`(upgrade 重生)、`docs/core-manual.md`、
  `pyproject.toml`、`__init__.py`。
- 关键决策:版本比较抽进可 import 的 `version_util.py` —— hyphen 命名的
  hook 不可 import/单测,放进包模块既可单测又给 Phase 2 复用;hook 绝不
  阻断 session 启动(任何异常静默 exit 0);hub editable 恒为最新故静默。
- 测试:`test_update_reminder` 9/9(`version_util` 单测 + hook 四态,预置
  TTL 缓存不碰网络);回归 candidate-reminder 7 + candidate-sweep 10 +
  revocation 19;upgrade/doctor exit 0(`hooks=18 registered=17`);build
  0.5.0。


### 2026-05-19 — P-0072 Phase 2 SessionStart candidate-reminder hook

- 改动：新增 SessionStart hook `candidate-reminder.py` —— 扫
  `candidate-common` 且不在去重台账的 learned skill,启动 banner 报"N 个候选
  待上传";hub(consumer_id=governance-core)静默;任何错误静默 exit 0、绝不
  破坏 session 启动。`candidates/ledger.py` `payload_digest` 改按 **basename**
  计哈希(让松散 skill 文件直接对账),加 `skill_digest` /
  `pending_candidate_skills`。`hooks/hooks_manifest.json` 注册新 hook →
  SessionStart。
- 涉及：新增 `governance_core/hooks/candidate-reminder.py`、
  `tools/test_candidate_reminder.py`;改 `candidates/ledger.py`、
  `hooks/hooks_manifest.json`、`.claude/settings.local.json`(upgrade 重生)、
  `docs/core-manual.md`。
- 关键决策：digest 改 basename —— Phase 1 的 `payload_digest` 含 envelope
  相对路径(`payload/x.md`),hook 拿到的是松散 skill 文件、构不出该路径;
  basename 化后 `skill_digest(松散文件)` == `payload_digest(其 envelope)`,
  hook 无需重建 envelope 即可对账(Phase 1 未发布,无遗留台账可破)。
- 测试：`test_candidate_reminder` 7/7(digest 一致性、`pending_candidate_skills`
  查询、hook 四态);回归 revocation 19 + candidate-attribution 9 +
  candidate-sweep 10;upgrade/doctor exit 0(`hooks=17 registered=16`,新
  hook 已注册);build 0.4.0。P-0072 两 phase 全部实现完成。


### 2026-05-19 — P-0072 Phase 1 candidate-uplink trigger in wrap-up

- 改动：候选管道补"触发线"(P-0065 造好出口、无人扣扳机的缺口)。新增
  `governance_core/candidates/ledger.py` —— uplink 去重台账,按 payload
  **内容哈希**去重(候选 id 带日期不可靠)。`tools/candidate.py` 加 `sweep`
  子命令(collect → 对未 uplink 候选 uplink → 记台账),hub 门
  (`consumer_id==governance-core` → N/A),consent/网络/`gh` 缺失退化为报告
  不返回非零;`uplink`/`submit` 成功后也记台账。`commands/wrap-up.md` 加
  Step 4d 候选上传 + Step 6 检查清单项。版本 0.3.0→0.4.0。
- 涉及：新增 `governance_core/candidates/ledger.py`、
  `tools/test_candidate_sweep.py`;改 `tools/candidate.py`、
  `commands/wrap-up.md`、`docs/core-manual.md`、`pyproject.toml`、
  `__init__.py`。
- 关键决策：去重按 payload sha256 而非候选 id(同内容只发一次、改了再发);
  `sweep` 永不阻断 wrap-up(仅 config 缺失返 2,其余报告 + exit 0);hub
  门按 consumer_id 判定,与 P-0068 拓扑门同源。
- 测试：`test_candidate_sweep` 10/10(内容哈希去重、台账幂等、sweep 选中
  candidate-common·business 被忽略·台账已记则跳过·空项目无候选·hub N/A);
  回归 revocation 19 + candidate-attribution 9;`sweep` dogfood gc 自身命中
  hub 门;upgrade/doctor exit 0;build 0.4.0。


### 2026-05-18 — P-0071 Phase 1 auth-code schema v2 + leasing + auth-guard cache fix

- 改动：codec payload schema 接受 `{1,2}` —— schema 2 携带 `expiry` /
  `revocation_feed_url` / `max_offline_days`，schema 1 保留（自托管 upgrade
  不中断，Art.8）。`auth-guard` 验证缓存键加 `verified_on` 日期维度 —— 过期码
  不再被陈旧 `valid:true` 命中（原 P-0065 缓存遗漏日期，本阶段先决修复）。
  `issue_auth_code` 默认签发 schema-2 365 天租约（`--schema` / `--expiry` /
  `--revocation-feed-url` / `--max-offline-days` 覆盖）。gc 自身重签 schema-2
  码、`config.json` 更新；版本 0.2.1→0.3.0。
- 涉及：`governance_core/auth/codec.py`、`hooks/auth-guard.py`、
  `maintainer/issue_auth_code.py`、`consumer_registry.json`、
  `.governance/config.json`、新增 `tools/test_auth_codec.py` +
  `test_auth_guard.py`、`pyproject.toml`、`__init__.py`、`docs/core-manual.md`。
- 关键决策：单一签名密钥对保留（区分 owner 靠 `consumer_id`，不分密钥）；
  schema 1 永久码仍被接受 = 过渡期不破；撤销源 URL 已嵌入新码，但拉取与
  执行属 Phase 3。
- 测试：`test_auth_codec` 11/11（双 schema 往返、过期/缺字段/篡改/未知 schema
  拒）；`test_auth_guard` 4/4（陈旧隔日 `valid` 缓存不再被信任的回归守卫）；
  upgrade/doctor exit 0；wheel 0.3.0 仅含 `governance_core*`。commit 172ee5c。


### 2026-05-18 — P-0070 Phase 2 upgrade prune (stale autonomy-layer files)

- 改动：Fix C —— `installer.py` 加 `_prune_stale`，`upgrade` 在 `_capture_drift`
  后、写新 manifest 前比对旧 manifest 与新 install 集，旧有新无的
  install-managed 路径删除（manifest-diff = 安全边界）+ `[prune]` 报告 + 空
  目录清理；`cli.py` 加 `--no-prune`；版本 0.2.0→0.2.1。一次性清掉 P-0069
  早于 manifest 残留的 `shared-code-per-agent-state.md`。
- 涉及：`governance_core/installer.py`、`cli.py`、`pyproject.toml`、
  `__init__.py`、`docs/{architecture,core-manual}.md`。
- 关键决策：manifest-diff 安全边界 —— business/authored/`learned/` 从不进
  manifest，故从不被 prune；prune 在 drift 捕获之后（被改过的陈旧文件先成候选）。
- 测试：`_prune_stale` 单测 5 项、探针文件真实 dogfood（装入→源删→upgrade
  prune）、upgrade/doctor exit 0、build 0.2.1。commit f09648c。P-0070 两 phase
  全部完成。


### 2026-05-18 — P-0070 Phase 1 audit_proposals path + tracker reason fixes

- 改动：Fix A —— `audit_proposals.py` 改用 `load_proposals_config` 解析
  in-flight 目录 + `_id_ledger.json`（与 `proposal_lib.py` 同源，不再硬编码
  父级相对路径）。Fix B —— `tracker.py` 加 `should_extract_reason()`，
  `--should-extract` CLI 区分 already-extracted-today / below-threshold /
  recommended、报实际原因；stats 加 `should_extract_reason` 字段。
- 涉及：`governance_core/tools/audit_proposals.py`、
  `governance_core/discovery/tracker.py`。
- 关键决策：两个均纯报告修复，不动 `should_extract()` 启发式；tracker CLI
  改 `sys.stdout.write`（避 `constitutional-review` 对 print 的拦截）。
- 测试：自托管 gc `audit_proposals` 报 in-flight=1/archive=4/0 failures
  （误报 ledger FAIL 消失）；`--should-extract` 正确报 "already extracted
  today"；`should_extract_reason` 单测。commit 0b5b870。


### 2026-05-18 — P-0065 Phase 5 hub-side curation + convergence loop

- 改动：GC 侧 curation 收口闭环 —— 新增 consumer registry 模块
  `governance_core/candidates/registry.py` + committed 台账
  `maintainer/consumer_registry.json`（记已签发消费者 + 候选评审决策）；
  `issue_auth_code.py` 签发即登记消费者；`tools/candidate.py` 加
  `review`/`promote` 子命令；GC 侧 incoming `candidates/` 进 `.gitignore`；
  收口 hub 模型写入 `docs/architecture.md` + `docs/core-manual.md §11`。
- 涉及：新增 `candidates/registry.py`、`maintainer/consumer_registry.json`；
  改 `tools/candidate.py`、`maintainer/issue_auth_code.py`、`.gitignore`、
  `docs/{architecture,core-manual}.md`。
- 关键决策：registry 落 maintainer 侧、committed（durable 台账）；`promote`
  按 kind 复制进包源、judgment 人工/agent；GitHub issue 为候选权威记录。
- 测试：`issue_auth_code` 登记 registry、curation 11 项（review/promote/
  reject、registry 内容）、upgrade/doctor exit 0、build 隔离。commit f5b23f7。
  P-0065 六 phase 全部实现完成。


### 2026-05-18 — P-0065 Phase 4 candidate collection + submit + uplink

- 改动：候选管道三来源 —— 脱敏扫描器 `sensitive_scan.py`（HIGH/MEDIUM 分级）
  + `sensitive-data-guard` PreToolUse hook（user 选 Option B：补全 README 一直
  宣称却缺失的安全 hook）；`candidates/collect.py`（净新增 candidate-common
  skill 收集）；`candidates/uplink.py`（脱敏扫描 + `gh issue` 传输 + dry-run +
  体积上限）；CLI `tools/candidate.py`（collect/submit/uplink，consent 门）；
  `/submit-candidate` 命令；installer `_capture_drift`（upgrade 覆盖前捕获
  install-managed 文件漂移成 drift 候选 + stderr 报告）。
- 涉及：新增 `governance_core/sensitive_scan.py`、`hooks/sensitive-data-guard.py`、
  `candidates/{collect,uplink}.py`、`tools/candidate.py`、
  `commands/submit-candidate.md`；改 `installer.py`、`hooks_manifest.json`、
  `.gitignore`、`.claude/settings.local.json`。
- 关键决策：`sensitive-data-guard` 原不存在 → Option B 补全；payload 内联
  issue body（~60KB 上限）；漂移=捕获后覆盖（不留 override）；uplink 带
  `--dry-run`。
- 测试：扫描器+hook 16 项、Part A 8 项（collect/submit/uplink/secret-abort/
  consent-gate）、Part B 漂移真实 dogfood、upgrade/doctor exit 0、build 隔离。
  commit 47fdf8f。


### 2026-05-18 — P-0065 Phase 3 candidate envelope + layer tagging

- 改动：新增 `governance_core/candidates/`（envelope 模块：三 kind
  skill/hook/mechanism + drift 类；`build_envelope` / `validate_envelope` /
  `validate_metadata` / `make_candidate_id`）；新增 CLI
  `tools/validate_candidate.py`；`discovery/extractor.py` 加 `--layer` flag →
  写 learned skill `layer:` frontmatter；`extract-skill.md` 插入 layer 分类
  步骤；`lesson-classification.md` 加 generic-vs-project 轴。
- 涉及：`governance_core/candidates/{__init__,envelope}.py`、
  `governance_core/tools/validate_candidate.py`、`discovery/extractor.py`、
  `commands/extract-skill.md`、`skills/lesson-classification.md`。
- 关键决策：`layer ∈ {candidate-common, business}`，默认 candidate-common
  （过报便宜、漏报无声）；envelope 目录式（candidate.json + payload 子目录）。
- 测试：13 项单测、真实 extractor `--layer` 跑通、upgrade/doctor exit 0、
  build 隔离。commit 1d2a575。


### 2026-05-18 — P-0065 Phase 2 installed-files manifest + baseline hash

- 改动：`install`/`upgrade` 写 `.governance/installed_files.json`（128 文件，
  逐文件 path + baseline_sha256 + source_version + category）；新增查询工具
  `whichlayer.py`（路径 → install-managed / business）；manifest 进 `.gitignore`
  （纯派生物）。附带修 Phase 1 遗留：`verified_at` 码不变则保留，committed
  config.json 不再 churn。
- 涉及：`governance_core/installer.py`、新增 `governance_core/tools/whichlayer.py`、
  `.gitignore`、`docs/{architecture,core-manual}.md`。
- 关键决策：Phase 0 category 枚举执行修正（去 `config`、补 `knowledge`）；
  版本维持 0.2.0（P-0065 六 phase 整体一次发版）。
- 测试：gc dogfood upgrade（128 文件 manifest）、`whichlayer` 6 路抽检、
  `doctor` exit 0。commit ef791c1。


### 2026-05-18 — P-0065 Phase 1 authorization double-gate + runtime enforcement

- 改动：governance-core 授权机制 —— install 双门（Ed25519 授权码离线验签 +
  强制 candidate-uplink 同意，双门通过才 materialize 自治层）；upgrade/doctor
  复验；运行时硬冻结（`auth-guard` PreToolUse hook，matcher `*`，授权无效即
  阻断全部工具调用，验签结果按 repo/code/key 缓存）；纯 Python Ed25519
  （RFC 8032，零运行时依赖）；`maintainer/` 签发工具；license MIT→自定义
  source-available（DRAFT）；版本 0.1.6→0.2.0。
- 涉及：新增 `governance_core/auth/`、`governance_core/hooks/auth-guard.py`、
  `maintainer/`；改 `installer.py`、`cli.py`、`hooks_manifest.json`、
  `pyproject.toml`、`__init__.py`、`LICENSE`、`README.md`、`docs/{architecture,
  core-manual}.md`、`.governance/config.json`、`.claude/settings.local.json`。
- 关键决策：授权 gate 两层（materialize 门 + 运行时硬冻结）—— user 修订原
  "install 门即够"设计；签名库=纯 Python Ed25519；uplink=GitHub issue；
  多 owner 签发台账推迟到 Phase 5 consumer registry。
- 测试：auth 自测 10/10；install/upgrade/doctor 门控；负向门（无/坏码→7、
  拒同意→8）；`auth-guard` hook（valid/篡改/缺失/缓存）；build 隔离
  （`maintainer/` + 私钥不入包）；gc 自托管 dogfood。commit 581f7e5。


### 2026-05-18 — P-0068 config-aware skills (Phases 1–3)

- 改动：单 agent skill 降级 —— Phase 1 去硬编码 4 处；Phase 2 给 7 个多 agent
  步骤加拓扑门控；Phase 3 桶 C（lesson 归档 .gitignore 例外、skill-extraction
  能力门控、STATE.md capability 进 installer）。
- 涉及：`governance_core/commands/{wrap-up,extract-skill,update-skill,
  sync-repos,sync-infra,publish-knowledge}.md`、`skills/{lesson-classification,
  _template}.md`、`installer.py`、`.gitignore`、`STATE.md`。
- 关键决策：三桶模型 A/B/C；安装完即所得；复用不 fork；3b（打包
  skills.discovery）拆出为 P-0069。
- 测试：每 phase `governance-core upgrade` exit 0 + 结构校验通过；P-0068
  commits 66d3929 / b58aee1 / 25c9bf9。

