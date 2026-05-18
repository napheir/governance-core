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
