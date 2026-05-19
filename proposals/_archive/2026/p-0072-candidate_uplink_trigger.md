---
id: P-0072
agent: core
status: implemented
created: 2026-05-19
approved_at: 2026-05-19
started_at: 2026-05-19
implemented_in: 568f44f
implemented_at: 2026-05-19
owner: core
---

# Proposal P-0072: Candidate-uplink trigger in wrap-up -- wire the convergence-hub trigger line

## Trigger

P-0071 收尾后的回测讨论(2026-05-19)暴露一个缺口:P-0065 建的候选管道把
**出口**(`collect` / `uplink` / `review` / `promote`)全造好了,却没有在消费者
侧接**触发线**。`/wrap-up` 的步骤里没有任何一步跑 `candidate.py collect` /
`uplink`;`/submit-candidate` 是纯手动 skill。

后果:消费者项目 extract 出的 learned skill 默认带 `layer: candidate-common`
(extractor `--layer` 默认值即 `candidate-common`),安静躺在
`.claude/skills/learned/` 里 —— 但**没有任何东西提醒 owner、或自动把它们
送出**。governance-core 作为"公共层改造统一收敛点"(P-0065 愿景)因此会饿:
hub 收不到候选,不是因为没打标,而是因为没人扣扳机。

用户(2026-05-19)指示:在 `/wrap-up` 时机加触发器 —— 有候选就上传、没有就
跳过;且该触发器不应能被静默关闭(至少 hook 层做可见性强制;承认人手动
删 hook/skill 物理上阻止不了)。

为 PROPOSAL_REQUIRED:改 `/wrap-up`(治理流程核心)、新增 hook、多 phase、
涉及对外动作(自动 uplink 到公共 repo)。

## Scope

### In-Scope

1. **`/wrap-up` 新增候选上传步骤**(置于 Step 4 skill-learning 之后):跑
   `candidate.py collect` 把当前带 `layer: candidate-common` 的 net-new
   learned skill 打包进 outbox;对每个**尚未 uplink** 的候选信封跑 `uplink`
   (secret-scan + origin 绑定 + consent 门已在 P-0065/P-0071 就位);无候选
   → 干净跳过并在检查清单标注。
2. **uplink 去重台账**:在 `.governance/candidate-outbox/` 下记录已 uplink
   的候选 id + issue URL,使 wrap-up 不会每个 phase 重复 uplink 同一候选
   (避免重复 GitHub issue)。
3. **拓扑/角色门**:governance-core 自身是 hub,不向自己 uplink —— 该步对
   hub(`consumer_id == "governance-core"` 或等价标识)打
   `[N/A — hub, no uplink]` 跳过,与现有 P-0068 拓扑门一致。
4. **检查清单项**:`/wrap-up` Step 6 加 `[x] 候选已上传 / 跳过(原因)` ——
   使该步与 STATE.md / git 等同属阻塞性,漏做 = 阶段总结未完成。
5. **可见性强制 hook**:新增一个 SessionStart hook,检测存在未 uplink 的
   `candidate-common` 候选 → 在 session 启动 banner 上报"有 N 个候选待上传",
   持续提醒 —— 即使 `/wrap-up` 被整体跳过也反复可见。

### Out-of-Scope

- **不**硬阻断 agent 直到 uplink 成功 —— 网络不可达 / `gh` 缺失 / consent
  缺失时该步**退化为报告**而非冻结(uplink 失败不该卡死阶段总结)。
- **不**改候选信封格式、不改 hub 侧 curation(`review` / `promote`)。
- **不**自动 uplink drift 候选 —— 那类在 `upgrade` 时已被捕获并报告;本提案
  聚焦 net-new `candidate-common` skill 的触发。

## Non-Goals

参见 Scope.Out-of-Scope。此外明确诚实边界:**触发器拦不住铁了心本地篡改的
人**。`/wrap-up` 的 skill body、新 hook 都是摊在消费者机器上的文件,一个人
可以删 hook、改 `wrap-up.md` 去掉这步。与 P-0071 Non-Goals 同源:enforcement
跑在本地,hook 提供持续可见性、检查清单赋予"阻塞性步骤"语义,但物理上拦不住
本地篡改。本提案做到的是:让"不上传候选"成为一个**显式、反复可见、与其它
wrap-up 步同级阻塞**的状态,而非一个静默的默认。

## Guardrails

| Guard | 适用 | 关注点 |
|-------|------|--------|
| `edit-write-guard` | 全期 | `wrap-up.md` / `candidate.py` / 新 hook 是 install-managed —— 改 `governance_core/` 包源,不碰自治层副本(宪法第十一条) |
| uplink 内置 secret-scan | Phase 1 | 自动 uplink 前 payload 必过 secret 扫描(HIGH+MEDIUM,P-0065 已有);自动化只省去人手敲命令,不放松扫描 |
| 对外动作审查 | Phase 1 | 自动 uplink = 自动建公共 GitHub issue;受 install 时已收的 `candidate_uplink.consent` 授权(P-0065 设计本就是"同意自动上传候选信封");consent 缺失则该步只报告不发送 |
| `command-guard` | Phase 1 | wrap-up 步骤内调 `candidate.py` / `gh` 前明示 |
| `boundary-guard` | 全期 | 在 governance-core 自身 self-hosted session 执行 —— 改包源 in-boundary |

## Phases

### Phase 1: wrap-up 候选上传步骤 + 去重台账 + 拓扑门 + 检查清单

- Deliverables:
  - `governance_core/commands/wrap-up.md`:Step 4 后新增候选上传步骤 ——
    拓扑/角色门(hub → N/A 跳过)、`collect` → 对未 uplink 候选 `uplink`、
    无候选干净跳过;Step 6 检查清单加 `[x] 候选已上传 / 跳过`。
  - uplink 去重台账(`.governance/candidate-outbox/` 下):记已 uplink 的
    候选 id + issue URL;`uplink` 成功后写台账;wrap-up 步骤只发台账外的。
  - 自动化路径在 consent / 网络 / `gh` 缺失时退化为报告,不阻断 exit。
  - gc 版本 bump;docs(`core-manual` §11 候选管道补"触发时机")。
- Validation:临时消费者项目(P-0071 回测同法的仓内临时项目)构造一个
  `candidate-common` skill → wrap-up 步骤 dry-run 验选中;构造无候选 →
  干净跳过;hub(gc 自身)→ N/A 跳过;去重台账单测(已 uplink 的不重发)。
- Exit criteria:消费者项目跑 `/wrap-up` 时未上传的 `candidate-common`
  候选被自动 uplink、无候选时跳过;gc 自身跳过。

### Phase 2: 未上传候选的可见性强制 hook

- Deliverables:
  - 新增 SessionStart hook:扫 `.claude/skills/learned/` 里 `layer:
    candidate-common` 且不在 uplink 台账中的 skill,启动 banner 上报
    "N 个候选待上传 —— 下次 /wrap-up 会上传,或跑 /submit-candidate"。
  - 注册进 `hooks/hooks_manifest.json`(install/upgrade 自动 wiring,P-0067)。
  - hub 角色下该 hook 自身静默(无 uplink 概念)。
  - gc 版本 bump;docs。
- Validation:构造未上传候选 → 新 session 启动 banner 出现提示;清空(全部
  已上传)→ 无提示;gc 自身 → 无提示。
- Exit criteria:即使 `/wrap-up` 被整体跳过,未上传候选仍在每次 session
  启动持续可见。

## Approval Criteria

User 批准前应能确认:

1. 触发时机 = `/wrap-up`,有候选则自动 uplink、无则跳过 —— 与用户
   2026-05-19 指示一致。
2. 自动 uplink 受 install 时已收的 `candidate_uplink.consent` 授权,且过
   secret-scan + origin 绑定 —— 不新增对外暴露面,只省去手动敲命令。
3. 去重台账确保不重复 uplink 同一候选。
4. hub(governance-core 自身)不向自己 uplink —— 拓扑门跳过。
5. 诚实边界:hook 持续可见性 + 检查清单阻塞性是威慑,拦不住本地手动删改 ——
   如实写入 Non-Goals。
6. 2 phase,各自独立可交付、可单独 revert。

## Validation Plan

- Phase 1:自托管 gc 跑 `/wrap-up` 验 hub N/A 跳过;仓内临时消费者项目构造
  `candidate-common` skill,验 `collect` → `uplink` dry-run 选中、台账去重、
  无候选跳过。
- Phase 2:构造未上传候选,新 session 验启动 banner 出现;清空后验无提示。
- 全程:`build` 验包隔离;`upgrade` / `doctor` exit 0。

## Rollback / Recovery

- **Phase 1**:`wrap-up.md` / `candidate.py` 改动 `git revert` → 回到无触发器
  (纯手动 `/submit-candidate`)。台账文件留存无副作用。
- **Phase 2**:hook 源 revert + `hooks_manifest.json` 移除条目 → `upgrade`
  自动解除 wiring。
- 每 phase 独立 commit,可逐 phase revert;最坏回到 P-0065/P-0071 的纯手动
  uplink。

## Risks

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| 自动 uplink 误发不该公开的内容 | 低 | 高 | uplink 内置 secret-scan(HIGH+MEDIUM)+ origin 绑定;命中即 abort;consent 缺失则只报告不发 |
| 每个 phase 重复 uplink 同一候选 → 重复 issue | 中 | 中 | uplink 去重台账;wrap-up 只发台账外的候选 |
| 网络 / `gh` 不可用卡死阶段总结 | 中 | 中 | 该步失败退化为报告、不阻断 wrap-up(Non-Goals 明确) |
| hub 误把自己当消费者 uplink | 低 | 中 | 拓扑/角色门按 consumer_id 判定,与 P-0068 拓扑门同源 |
| 触发器被本地篡改关闭 | 低 | 中 | 无法技术消解(Non-Goals);hook 持续可见性 + 检查清单阻塞性为威慑 |

## State Log

- 2026-05-19: draft created by core agent (P-0072)
- 2026-05-19: draft → pending (submit for review: candidate-uplink trigger in wrap-up)
- 2026-05-19: pending → approved (user approval: approve P-0072)
- 2026-05-19: approved → in-progress (Phase 1 started)
- 2026-05-19: in-progress → implemented
