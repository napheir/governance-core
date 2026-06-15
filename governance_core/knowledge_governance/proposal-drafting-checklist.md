---
title: Proposal Drafting Checklist (seed)
status: active
created: 2026-06-15
updated: 2026-06-15
owner: core
carrier_class: reference
tags: [governance, proposal, drafting, checklist]
related:
  - .claude/commands/proposal.md
  - tools/proposal_suggest.py
---

# Proposal Drafting Checklist (seed)

这是 `proposal_suggest.py` ② 节（检查项 / 历史经验）的数据源。它是一份**通用治理
起草经验 seed** —— 每条记录"在某类改动里反复踩过的坑 + 怎么避"。`proposal_suggest`
按每条的 `触发` 关键词命中（ASCII 词边界 / CJK 子串），起草时 surface 给 agent
参考，**不阻断**。

## 维护约定

- **域中立**：本 seed 只放跨项目通用的治理/工程经验；消费者按自身域追加条目
  （交易、数据、模型等）由消费者维护，不回流 hub。
- **格式固定**（`parse_checklist` 依赖）：每条为一个 `### 标题`，其下四个字段
  `- **触发**: kw1, kw2, ...` / `- **教训**: ...` / `- **怎么做**: ...` /
  `- **来源**: ...`。`触发` 以 `, ，、` 分隔多关键词。
- 第一个 `###` 之前的文字（本节）会被解析器忽略，仅供人读。

---

### 固化机制前先实读源文件

- **触发**: 固化, 机制, 实读, hook, skill
- **教训**: 凭记忆或描述改治理机制，易踩到过期路径、漏掉调用点或依赖。
- **怎么做**: 起草前先 Read/Grep 目标源文件与其调用点，按现状而非假设落方案。
- **来源**: seed

### 改 skill / 治理体系必走 classify gate

- **触发**: skill, 治理, 宪法, classify, 契约, hook
- **教训**: 仅以"是否 cross-agent / 是否本 scope"为唯一筛会漏判；改治理体系
  （skill / hook / 契约 / 宪法）属全局变更。
- **怎么做**: 任何动治理体系的改动先跑 `/proposal classify`，不自行用人脑判断
  是否需要 proposal。
- **来源**: seed

### 新增非 .py 数据文件须进 package-data

- **触发**: 数据文件, json, 打包, wheel, package-data
- **教训**: 新增 `.json` / `.md` 数据文件不加 package-data glob 会静默漏出
  wheel；editable 安装会掩盖这一点。
- **怎么做**: 加文件后核对打包配置的 package-data 是否覆盖，并以 wheel 内容
  校验兜底（断言新文件确实在 wheel 内）。
- **来源**: seed

### 多 phase / 架构级改动先定 phase 边界与 rollback

- **触发**: 多 phase, 架构, 迁移, rollback, 回退
- **教训**: 大改动无清晰 phase 边界与回退路径，半途失败时难以恢复。
- **怎么做**: proposal 为每个 phase 写明交付物 + 验证 + 退出标准，并给出逐
  phase 的 rollback / recovery 步骤。
- **来源**: seed
