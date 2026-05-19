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
