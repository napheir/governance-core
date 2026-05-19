---
id: P-0074
agent: core
status: implemented
created: 2026-05-19
approved_at: 2026-05-19
started_at: 2026-05-19
implemented_in: 56b031a
implemented_at: 2026-05-19
owner: core
---

# Proposal P-0074: Auth lifecycle gaps -- per-consumer un-revoke + lease-renewal reminder

## Trigger

签发 `trade-agent` 授权码后的讨论(2026-05-19)暴露 P-0071 租约/撤销模型
的两个生命周期缺口:

**A. 没有 un-revoke。** `revoke_consumer.py` 能把 consumer_id 加进
`revocation.json`,却**没有干净的逐消费者移除**。误撤销一个消费者,只能靠
手改 `revocation.json` + 私钥重签,或 `--init --force`(整源清空,若还有别
的真撤销会误伤)。撤销当初按"持久"设计,但**误撤销恢复**是真实需求。

**B. 没有续期可见性。** schema-2 码是 365 天租约,续期 = 到期前手动重跑
`issue_auth_code.py`。但**没有任何东西告诉 maintainer 哪些消费者将到期** ——
它们会静默过期(与 P-0072 的"出口已建、无触发线"同型缺口)。

用户(2026-05-19)指示立项修这两条。为 PROPOSAL_REQUIRED:新增 hook、改
maintainer 工具、多 phase、触及授权/撤销模型。

## Scope

### In-Scope

1. **Phase 1 — 逐消费者 un-revoke。** `revoke_consumer.py` 加
   `--unrevoke <consumer-id>`:从签名撤销源移除该 consumer_id、重新签名、
   写回 feed + sig;`consumer_registry.json` 该消费者 `status` 改回 `active`、
   清 `revoked_on`/`revocation_reason`。新增 `revocation.remove_revocation`
   (幂等,移除不存在的 id 为 no-op)、`registry.mark_active`。
2. **Phase 2 — 续期可见性。** `maintainer/renewal_status.py`:扫
   `consumer_registry.json`,按租约 `expiry` 列出 active 消费者、标出
   阈值内将到期者(默认 30 天)。新增 `renewal-reminder.py` SessionStart
   hook(**hub 侧**:读 `maintainer/consumer_registry.json`,启动 banner 报
   "N 个消费者租约将到期";消费者项目无 `maintainer/` 目录 → 静默)。注册进
   `hooks/hooks_manifest.json`。

### Out-of-Scope

- **签名自动续期源 —— 本提案不做,留作独立后续提案。** "消费者 auth-guard
  从 GC 签名的续期源按 consumer_id 拉新码"能让续期自动化,但它是个更大的新
  机制,且**与 P-0071 的'租约到期 = 撤销兜底'相权衡**(自动续期削弱时间界)。
  该机制值得单独立项、把这个 tradeoff 摆明;P-0074 只做续期**可见性**
  (提醒),不做自动续期。
- **不**自动重签码 —— 续期仍是 maintainer 跑 `issue_auth_code`;P-0074 只让
  "谁该续"可见。
- `--unrevoke` 是修**误撤销**的 maintainer 纠错动作 —— 撤销仍以持久为意图,
  un-revoke 不是常规反复开关。

## Non-Goals

参见 Scope.Out-of-Scope。诚实边界:续期提醒与所有本系统的 reminder 一样 ——
**只浮现、不强制**,maintainer 可无视。`--unrevoke` 会重签撤销源,重新撤销
随时可做(un-revoke 非不可逆)。与 P-0071/P-0072/P-0073 Non-Goals 同源:
enforcement / 可见性跑在本地,提供线索而非强制。

## Guardrails

| Guard | 适用 | 关注点 |
|-------|------|--------|
| `edit-write-guard` | 全期 | `revoke_consumer.py` / `revocation.py` / `registry.py` / 新 hook 改 `governance_core/` 包源或 `maintainer/`,不碰自治层副本(宪法第十一条) |
| `sensitive-data-guard` | Phase 1 | `--unrevoke` 用私钥重签撤销源 —— 私钥原文不进 git/包/日志 |
| `command-guard` | 全期 | `revoke_consumer.py --unrevoke` / `renewal_status.py` dogfood 调用前明示 |
| `boundary-guard` | 全期 | 在 governance-core 自身 self-hosted session 执行 —— 改包源 in-boundary |

## Phases

### Phase 1: 逐消费者 un-revoke

- Deliverables:
  - `governance_core/auth/revocation.py`:加 `remove_revocation(feed,
    consumer_id) -> feed`(`add_revocation` 的镜像,幂等)。
  - `governance_core/candidates/registry.py`:加 `mark_active(path,
    consumer_id)` —— `status` 改回 `active`、清 `revoked_on` /
    `revocation_reason`;返回该消费者是否存在。
  - `maintainer/revoke_consumer.py`:加 `--unrevoke <consumer-id>` ——
    load+验签现有 feed → `remove_revocation` → 重签写回 → `mark_active`
    台账;消费者不在 feed 里 → 报告 no-op。
  - gc 版本 bump;docs(`core-manual` §9 撤销一节补 un-revoke)。
- Validation:`remove_revocation` 单测(移除在册/不在册 no-op)、`mark_active`
  单测(清 revoked 状态);`revoke_consumer.py` dogfood —— 撤销一个测试
  consumer → `--unrevoke` → `--list` 验已移除、台账 status 回 active。
- Exit criteria:误撤销的消费者可被干净地逐个 un-revoke,不误伤其他撤销项。

### Phase 2: 续期可见性（提醒）

- Deliverables:
  - `maintainer/renewal_status.py`:扫 `consumer_registry.json`,按
    `expiry` 列 active 消费者、标出 N 天内将到期者(默认 30);纯报告。
  - 新增 `renewal-reminder.py` SessionStart hook:读
    `maintainer/consumer_registry.json`(仅 hub 侧存在),启动 banner 报
    将到期消费者;`maintainer/` 不存在(= 消费者项目)→ 静默;任何异常
    静默 exit 0(绝不阻断 session 启动)。
  - 注册进 `hooks/hooks_manifest.json` → SessionStart。
  - gc 版本 bump;docs。
- Validation:到期计算单测(给定台账 + 当日,正确算出将到期集);hook 三态
  (有将到期 → banner / 无 → 静默 / 无 `maintainer/` 目录 → 静默);
  `renewal_status.py` dogfood;upgrade/doctor exit 0。
- Exit criteria:maintainer 在 session 启动 + 经 `renewal_status.py` 看得见
  哪些消费者租约将到期,从而及时重签。

## Approval Criteria

User 批准前应能确认:

1. `--unrevoke` 是逐消费者移除 + 重签,**不误伤** feed 里其他撤销项;撤销仍
   以持久为意图,un-revoke 是纠错。
2. 续期提醒只**浮现**(hub 侧 SessionStart hook + `renewal_status.py` 工具),
   **不自动重签、不自动续期**;续期动作仍由 maintainer 主动执行。
3. 签名自动续期源**不在本提案** —— 它是更大的新机制且与 P-0071 租约兜底
   有 tradeoff,留作独立后续提案。
4. 新 hook 与 `candidate-reminder` / `update-reminder` 同套路:SessionStart、
   异常静默、绝不阻断启动;且为 **hub 侧**(消费者项目静默,与那两个的
   消费者侧正好相反)。
5. 2 phase,各自独立可交付、可单独 revert。

## Validation Plan

- Phase 1:`remove_revocation` / `mark_active` 单测;`revoke_consumer.py`
  dogfood(撤销测试 consumer → `--unrevoke` → `--list` + 台账验证)。
- Phase 2:到期计算单测;`renewal-reminder` hook 三态(临时 repo + 子进程
  驱动);`renewal_status.py` 自托管 dogfood;`build` 验包隔离;upgrade/
  doctor exit 0。
- 全程:`build` 验 `maintainer/` 不进 wheel。

## Rollback / Recovery

- **Phase 1**:`revoke_consumer.py` / `revocation.py` / `registry.py` 改动
  `git revert` → 回到无 un-revoke(误撤销仍只能手改 feed)。
- **Phase 2**:`renewal-reminder.py` + `renewal_status.py` revert +
  `hooks_manifest.json` 移除条目 → `upgrade` 自动解除 hook wiring。
- 每 phase 独立 commit,可逐 phase revert;最坏回到本提案前。

## Risks

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| `--unrevoke` 给被篡改的 feed 重签(洗白篡改) | 低 | 中 | 改 feed 前先验旧 feed 签名(与 `revoke_consumer.py` 撤销路径同款检查),验不过即拒 |
| un-revoke 被当常规开关滥用 | 低 | 低 | 文档明确 un-revoke 是误撤销纠错;撤销仍以持久为意图 |
| 续期提醒被无视、消费者仍过期 | 中 | 中 | 提醒是 advisory(Non-Goals);hub 侧 SessionStart 持续可见是设计上限;到期本由 P-0071 租约设计,过期非故障 |
| renewal hook 读不到 / 误读台账拖慢启动 | 低 | 低 | 任何异常静默 exit 0;台账是本地小 JSON,无网络 |

## State Log

- 2026-05-19: draft created by core agent (P-0074)
- 2026-05-19: draft → pending (submit for review: un-revoke + lease-renewal reminder)
- 2026-05-19: pending → approved (user approval: 批准)
- 2026-05-19: approved → in-progress (Phase 1 started)
- 2026-05-19: in-progress → implemented
