# Trade Agent 项目状态文档 — Archive

> 此文件包含 STATE.md 的历史条目（超出滚动窗口的部分）。
> 按时间倒序排列（最新在前）。
> 由 `tools/rotate_state.py` 自动管理。

---

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

