---
id: P-0071
agent: core
status: implemented
created: 2026-05-18
approved_at: 2026-05-18
started_at: 2026-05-18
implemented_in: 5ce81f7
implemented_at: 2026-05-18
owner: core
---

# Proposal P-0071: Per-consumer authorization lifecycle -- signed revocation feed, leasing, attribution hardening

## Trigger

P-0065 建立了授权机制:单一 Ed25519 密钥对、`GC1.<payload>.<sig>` 授权码、
install 双门 + `auth-guard` 运行时硬冻结。但它对**消费者群体**只有一个粗粒度
开关 —— 撤销的唯一手段是轮换密钥对,旧码全废、所有消费者一起重签。

用户(2026-05-18)要把授权细分到**单个 owner**:GC 会把包分发给多个项目
owner,需要能(1)区分每个 owner 上传的候选技能/机制,(2)在某个 owner 的
项目脱离组织后,**主动、定向**地剔除他的授权 —— 且明确点出离队者不会主动
`upgrade`,撤销不能依赖消费者配合。

设计讨论确认了三件事:

1. **签名密钥对保持唯一。** 安装包是单一产物,所有人拿到同一份 `pubkey.json`;
   "每人一对公私钥"需为每个 owner 构建不同的包,模型崩坏。区分 owner 靠
   payload 内的 `consumer_id`,不靠分密钥。
2. **对铁了心篡改本地 `auth-guard.py` / 卸载 governance-core 的对抗者,无法
   冻结** —— 验证者跑在对手硬件上,这是物理事实(见 Non-Goals)。本提案的
   目标是**被动离队者**(governance 原样装着、hook 未动、机器联网)与
   **半合作者**(会屏蔽撤销源但不改 hook)。
3. 现有 `auth-guard` 缓存有 bug:缓存条目只含 `{code_sha256, pubkey_sha256,
   valid}`,**不含日期** —— 一个码验证通过被缓存后,即便其 `expiry` 已过,
   缓存命中仍直接 `exit(0)`。expiry 现在实际不生效。这是先决修复。

为 PROPOSAL_REQUIRED:改授权模型(security-sensitive)、改 hook 源、多 phase、
引入网络读取与 schema 版本升级、需 rollback。

## Scope

### In-Scope

1. **授权码 schema v2 + 租约默认。** `codec.py` payload schema 升到 2,新增
   `revocation_feed_url`、`max_offline_days` 两字段;`issue_auth_code.py` 的
   `--expiry` 默认 = 签发日 +365 天(租约,而非永久)。codec 同时**接受
   schema 1**(legacy 永久码、无撤销源)以保自托管 upgrade 不中断。
2. **`auth-guard` 缓存日期 bug 修复。** 缓存判定纳入日期/expiry —— 过期码不
   再被陈旧 `valid:true` 命中;这是 expiry 与撤销源生效的先决条件。
3. **签名在线撤销源。** 仓内 committed 文件 `revocation.json` +
   detached `.sig`(GC 私钥签名),经 `raw.githubusercontent.com` 公开。新增
   `governance_core/auth/revocation.py`:撤销源格式 + 签名校验。
4. **`auth-guard` 在线撤销执行 + 离线上限。** `auth-guard` 按 TTL 拉取并验签
   撤销源;`consumer_id` 在撤销名单 → 冻结;源不可达 → 用上次成功拉取的已签名
   缓存;**距上次成功拉取超过 `max_offline_days`(=30)→ 冻结**。
5. **maintainer 撤销工具。** `maintainer/revoke_consumer.py`:把 `consumer_id`
   加入 `revocation.json`、重新签名、在 `consumer_registry.json` 标记。
6. **归属加固 + 候选管道撤销硬拒。** 候选 uplink 携带消费者授权码,校验
   `candidate.json` 的 `origin` 与码内 `consumer_id` 一致(origin 不可谎报);
   `tools/candidate.py` 的 `review`/`promote` 对 `origin` 属撤销名单的候选
   硬拒。`consumer_registry.json` 升级为续期/撤销台账(`status`、`revoked_on`、
   `expiry`、`last_issued`)。
7. `doctor` 报告:撤销状态、距上次撤销源拉取天数、expiry 倒计时。

### Out-of-Scope

- **不**改为每消费者独立密钥对 —— 单一签名密钥对保留。
- **不**做强制联网设计 —— 离线在 `max_offline_days` 内照常工作,撤销源退化为
  上次缓存的已签名副本。
- **不**改候选评审的人工判断属性(promote 仍是 maintainer 决策)。
- **不**把撤销/租约模型写进宪法 —— 与 P-0065 一致,操作记录归 `docs/core-manual`
  §9 + 本提案;无 Phase 0。

## Non-Goals

参见 Scope.Out-of-Scope。此外明确声明本提案**做不到**的事(诚实边界):

**无法冻结篡改本地 enforcement 的主动对抗者。** `auth-guard.py` 是一份摊在
消费者 `.claude/hooks/` 里的 Python 源码,跑在对手的机器上。一个铁了心的离队者
可以删掉它、把它改成 `exit(0)`、钉死旧包版本、或整体卸载 governance-core ——
**没有任何密码学或软件机制能阻止**(验证者跑在对手硬件上,与所有 DRM 失败同因)。
本提案覆盖:被动离队者(撤销源更新后即时冻结)、屏蔽撤销源者(`max_offline_days`
后冻结)、永久离线者(365 天 expiry 后冻结);**不覆盖**篡改 hook 的对抗者 ——
对这类只剩非技术手段(拿不到新码、拿不到改进、提交的候选被硬拒且 origin 可证
非法)。drift 检测可把被篡改的 `auth-guard` 标记为漂移,但那也跑在本地,是威慑
非强制。

## Guardrails

| Guard | 适用阶段 | 关注点 |
|-------|---------|--------|
| `edit-write-guard` | 全期 | `codec.py` / `auth-guard.py` / `installer` 等是 install-managed —— 改 `governance_core/` 包源,不碰自治层副本(宪法第十一条) |
| `sensitive-data-guard` | 全期 | 私钥签名撤销源 —— 私钥原文不得进 git/包/日志;`revocation.json` 与 `.sig` 不含机密;commit/输出无 `seed_b64` |
| `command-guard` | 全期 | `governance-core upgrade` dogfood、`revoke_consumer.py` 调用前明示 |
| `boundary-guard` | 全期 | 在 governance-core 自身 self-hosted session 执行 —— 改包源 in-boundary |
| 网络读取审查 | Phase 3 | `auth-guard` 拉取撤销源用 stdlib `urllib`、短超时、不新增依赖;失败 fail-to-cache,绝不 fail-open |

## Phases

### Phase 1: 授权码 schema v2 + 租约默认 + auth-guard 缓存 bug 修复

先决正确性修复 + 租约语义,不含网络。

- Deliverables:
  - `codec.py`:`PAYLOAD_SCHEMA` 接受 `{1, 2}`;schema 2 的 `canonical_payload`
    新增 `revocation_feed_url`、`max_offline_days`;`verify_auth_code` 对 schema 1
    视作 legacy 永久无源码、对 schema 2 解析新字段。
  - `issue_auth_code.py`:`--expiry` 默认签发日 +365;签发 schema-2 payload
    (带 feed URL + `max_offline_days`);保留 `--expiry` / `--schema` 覆盖。
  - `auth-guard.py`:缓存条目纳入日期维度 —— 过期码不再被陈旧 `valid:true`
    命中(重新验证或缓存键含当日)。
  - 自托管 gc 以 schema-2 365 天租约重新签发自身授权码;gc 版本 bump;docs。
- Validation:`verify_auth_code` 单测(schema 1 接受/schema 2 字段/过期拒);
  构造"昨日缓存 valid + 今日过期"验缓存不再误放行;自托管 gc upgrade/doctor
  exit 0。
- Exit criteria:expiry 真正生效;schema-2 码可签发可验证;schema-1 码不破。

### Phase 2: 签名撤销源 — 格式、签名、GC 侧发布

- Deliverables:
  - `governance_core/auth/revocation.py`:撤销源格式
    `{schema, updated, revoked: [{consumer_id, revoked_on, reason}]}` + detached
    签名的构造/校验(复用 `auth.sign`/`auth.verify` + bundled pubkey)。
  - 仓根 committed `revocation.json` + `revocation.json.sig`(初始空名单);
    **不进 pip 包**(经网络拉取,bundle 会陈旧)—— 确认 `pyproject.toml`
    `packages.find` 仍只匹配 `governance_core*`。
  - `maintainer/revoke_consumer.py`:`--consumer-id` 加入撤销源、用
    `~/.governance-core/signing_key.json` 重新签名、`consumer_registry.json`
    标记 `status: revoked` + `revoked_on`。
  - docs:撤销源 raw URL、撤销操作手册。
- Validation:`revocation.py` 构造/验签单测(合法/篡改/错签名);
  `revoke_consumer.py` dogfood(加一个测试 consumer_id→验签通过→registry 标记)。
- Exit criteria:GC 一次 commit+push 即可定向撤销一个 consumer_id,撤销源可验签。

### Phase 3: auth-guard 在线撤销执行 + max_offline_days 兜底

- Deliverables:
  - `auth-guard.py`:从 payload 读 `revocation_feed_url`,TTL 缓存拉取
    (每数小时至多一次,非每次工具调用);验签撤销源;`consumer_id` 命中名单
    → 冻结。源不可达 → 用上次成功拉取的已签名缓存;距上次成功拉取 >
    `max_offline_days` → 冻结;首装从未拉到 + 不可达 → 自安装日起 grace
    `max_offline_days`。stdlib `urllib`、短超时、fail-to-cache。
  - `doctor`:报告撤销状态、距上次撤销源拉取天数、expiry 倒计时。
  - gc 版本 bump;docs。
- Validation:模拟撤销源含 gc 自身 consumer_id → 验冻结;模拟源不可达 + 缓存
  在期 → 验放行;模拟距上次拉取 > 30 天 → 验冻结;验签失败的源 → 拒用、不
  fail-open。
- Exit criteria:被动离队者撤销源更新后即时冻结;屏蔽源者 30 天后冻结。

### Phase 4: 归属加固 + 候选管道撤销硬拒

- Deliverables:
  - 候选 uplink(`tools/candidate.py` / `candidates/uplink.py`):携带消费者
    授权码,校验 `candidate.json` 的 `origin` 与码内 `consumer_id` 一致。
  - `candidate.py` `review`/`promote`:`origin` 属撤销名单的候选硬拒并标注。
  - `consumer_registry.json` schema:`status`(active/revoked)、`revoked_on`、
    `expiry`、`last_issued`;`registry.py` 配套读写。
  - docs:`docs/core-manual` §9 撤销/租约/归属一节完整化。
- Validation:`origin` 与码不一致的信封被拒单测;撤销名单内 `origin` 的候选
  被 `review`/`promote` 硬拒单测;`consumer_registry.json` 升级 schema 单测。
- Exit criteria:候选归属不可谎报;撤销 owner 的候选在 GC 侧气密拒收。

## Approval Criteria

User 在批准前应能确认:

1. 单一签名密钥对保留;区分 owner 靠 `consumer_id`,不分密钥。
2. 诚实边界:篡改本地 `auth-guard.py` 的对抗者**冻不住**,本提案不假装能 ——
   覆盖的是被动离队者 + 半合作者 + 永久离线者三类。
3. `max_offline_days = 30`、expiry 默认 365 天、撤销源走仓内 committed 文件 +
   GitHub raw —— 三个参数符合 2026-05-18 设计讨论的决定。
4. `auth-guard` 不会每次工具调用都联网(TTL 缓存);源不可达时 fail-to-cached-
   signed-feed,**绝不 fail-open**。
5. 4 phase,每 phase 独立可交付、可单独 revert;schema 1 码在过渡期不破。

## Validation Plan

- Phase 1:`codec` schema 单测;`auth-guard` 缓存"昨缓存今过期"回归;自托管
  gc 重签 schema-2 码后 upgrade/doctor exit 0。
- Phase 2:`revocation.py` 构造/验签单测;`revoke_consumer.py` dogfood。
- Phase 3:模拟撤销命中 / 源不可达在期 / 离线超 30 天 / 验签失败四态,逐一
  验 `auth-guard` 行为;`doctor` 报告字段。
- Phase 4:归属一致性 + 撤销硬拒单测;registry schema 升级单测。
- 全程:gc 自身 self-hosted 实例 dogfood;每 phase 末 `build` 验包隔离
  (`revocation.json` 不进 wheel)。

## Rollback / Recovery

- **Phase 1**:`codec` / `issue_auth_code` / `auth-guard` 改动 `git revert`;
  schema 2 码 revert 后无法验证 —— 需同时回退到重签 schema-1 码,故 revert
  Phase 1 前先确认自托管 gc 持有可用的 schema-1 码。
- **Phase 2**:`revocation.py` + `revoke_consumer.py` revert;`revocation.json`
  保留为空名单无副作用。
- **Phase 3**:`auth-guard` 在线检查逻辑 revert → 回到 Phase 1 的纯本地
  (expiry-only)行为;撤销源不再被读取,但 expiry 兜底仍在。
- **Phase 4**:候选管道改动 revert → 回到 origin 自报、无撤销硬拒。
- 总体:每 phase 独立 commit,可逐 phase revert;最坏情形回退到 P-0065 的
  授权模型(单开关 + 密钥轮换)。

## Risks

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| `auth-guard` 联网拖慢每次工具调用 | 中 | 中 | TTL 缓存,撤销源每数小时至多拉一次;短超时;拉取失败立即用缓存,不阻塞 |
| 撤销源被中间人伪造成空名单 | 低 | 高 | 撤销源 detached 签名 + bundled pubkey 验签;验签失败即拒用该源,不 fail-open |
| 屏蔽撤销源 URL 逃避撤销 | 中 | 中 | `max_offline_days=30` 兜底 —— 距上次成功拉取超 30 天即冻结;365 天 expiry 再兜底 |
| 篡改/删除本地 `auth-guard.py` 的对抗者 | 低 | 高 | **无法技术消解**(见 Non-Goals);drift 检测标记被篡改 hook(威慑);非技术手段:停发码、候选硬拒 |
| schema v2 升级破坏自托管 upgrade | 中 | 中 | codec 接受 schema `{1,2}`;Phase 1 内自托管 gc 重签 schema-2 码完成切换 |
| 正常消费者长期离线被误冻结 | 低 | 中 | `max_offline_days=30` 已含此权衡(用户 2026-05-18 选定);doctor 报告剩余离线天数预警 |
| `revocation.json` 误进 pip 包变陈旧快照 | 低 | 中 | 文件置于 `governance_core/` 之外;每 phase `build` 验 wheel 仅含 `governance_core*` |

## State Log

- 2026-05-18: draft created by core agent (P-0071)
- 2026-05-18: draft → pending (submit for review: per-consumer authorization lifecycle)
- 2026-05-18: pending → approved (user approval: 理解整个机制，可以开始执行P-0071)
- 2026-05-18: approved → in-progress (Phase 1 started)
- 2026-05-18: in-progress → implemented
