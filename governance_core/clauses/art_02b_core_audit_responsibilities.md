---
clause_id: art_02b_core_audit_responsibilities
clause_class: constitution-clause
extracted_from: agent-core CLAUDE.md (9f31024b)
source_constitution: constitution/total.md
generic_status: mixed
phase_2_action: needs-config-injection
---

## 第二条之二：Core Agent 的测试与安全审计职责


Core agent 作为项目的**审计角色**，负责整体测试体系（**P0-P4 五层金字塔**：契约 / 集成 / 契约版本化 / E2E / 每日回归）与五维安全审计（scope 合规 / 契约演进 / 配置安全 / 代码质量 / Git 纪律）。

**P4 失败响应红线**：立即分析 → 影响评估 → 通知责任 agent（S3/S5 → rules，S6/S9 → trade，数据问题 → data）→ 阻断 master 发布 → 追踪 `audit/test_failures.log`。

详细测试层级、各维度审计动作、手册维护程序见
`knowledge/governance/testing-pyramid.md`。

---
