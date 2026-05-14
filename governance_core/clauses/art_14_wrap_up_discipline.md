---
clause_id: art_14_wrap_up_discipline
clause_class: constitution-clause
extracted_from: agent-core CLAUDE.md (9f31024b)
source_constitution: constitution/total.md
generic_status: generic
phase_2_action: ready-to-use
---

## 第十四条：阶段总结纪律（阻塞性）


每个功能阶段完成后，Agent 必须通过调用 `/wrap-up` skill 完成阶段总结。

**阻塞规则**：
- `/wrap-up` skill 全部步骤完成前，禁止开始新任务或响应新请求
- 用户催促下一个任务时，Agent 必须先完成阶段总结再继续
- `/wrap-up` skill（`.claude/commands/wrap-up.md`）是阶段总结的**唯一权威操作清单**；
  skill 步骤随工程实践演化，本宪法不复述其内容
- **禁止**手动列举 skill checklist 的子集充数；未完整执行 skill = 未完成

**违宪判定**：未调用 `/wrap-up` skill 即视为违反本条，下一任务开始前必须补齐。

**子宪法扩展点**：各 agent 的子宪法或 `.claude/agents/<role>.md` 可补充本 agent 的
操作手册路径（`knowledge/operations/<agent>-manual.md`）、触发条件等操作细节，
但不得放宽阻塞规则。

---
