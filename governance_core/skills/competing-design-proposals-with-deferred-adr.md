---
theme: universal
name: competing-design-proposals-with-deferred-adr
description: "When a design flaw has two-or-more viable fixes: draft both as competing proposals with a shared comparison table, present head-to-head plus recommendation, let the user pick, implement the winner, and record the loser as a deferred decision-record (ADR) with an explicit revisit trigger."
type: guide
tags: [governance, proposal-lifecycle, decision-record, design-tradeoff, adr]
created: 2026-06-11
updated: 2026-06-12
---

# Competing Design Proposals with Deferred ADR

> **Provenance**: Contributed by a consumer agent via the candidate pipeline; the
> one domain-specific illustration was genericized during curation. The mechanism
> is preserved as contributed.

When a design flaw has two-or-more viable fixes: draft both as competing proposals with a shared comparison table, present head-to-head plus recommendation, let the user pick, implement the winner, and record the loser as a deferred decision-record (ADR) with an explicit revisit trigger.

## Preconditions

1. 缺陷已用真实代码行号实证
2. 涉及改现状行为或跨 agent 则 PROPOSAL_REQUIRED
3. 本 agent 对自身 knowledge scope 有写权限 (否则换 owner 目录)

## Workflow

1. 识别多个互斥可行方案; propose-first 不直接改代码
2. 每方案各写一份提案 (proposal_lib create), 两提案末尾同步维护同一张对比表 (维度 含解决直接痛点 解决根因 新数据依赖 改现状行为 校准风险 可逆性 理论最优性 适配现状)
3. 给 user 头对头对比加明确推荐加点出方案间目标函数差异 (非纯优劣) 加分叉示例
4. user 选型后胜者 draft-pending-approved-implemented (带 commit hash)
5. 落败方案记 decision-record ADR (选型理由加显式 revisit trigger), proposal 转 rejected 且 reason 指向 ADR (deferred 非废弃)

## Outputs

- 两份 shared_state proposals (胜者 implemented 落败 rejected-deferred)
- knowledge 决策记录 ADR (revisit trigger) 加 INDEX 注册
- 契约 STATE 同步

## Notes

- ADR 是 decision-record carrier_class 强制 MD 不用 HTML
- 落败方案用 rejected (reason 指向 ADR) 表达 deferred 非废弃 比 superseded 更准 (无替代者)
- 对比表两份提案同步维护避免漂移
- 若方案涉及算法/排序等行为变更, 附与现状基线的回归对比 (如核心指标 delta=0 红线) 避免隐性行为漂移
