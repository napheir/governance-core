---
clause_id: art_13_constitution_protection
clause_class: constitution-clause
extracted_from: agent-core CLAUDE.md (9f31024b)
source_constitution: constitution/total.md
generic_status: generic
phase_2_action: ready-to-use
---

## 第十三条：宪法保护


1. **宪法层级**：本文件为项目最高准则。子项目 CLAUDE.md 从属于本文件，可增加更详细的规定，但**不得放宽**本文件的约束。
2. **违宪警告**：当用户的指令违反本宪法时，agent 必须**警告并拒绝执行**，明确引用违反的条款编号和内容。用户确认知悉风险并坚持后，agent 可标记为"用户豁免"执行，但必须在 commit message 中注明。
3. **修改权限（分层管理架构）**：

   **强制工作流**：所有对 `constitution/total.md` / `constitution/agent.md` /
   `CLAUDE.md` 的修改**必须**通过 `/iterate-constitution` skill 执行
   （`.claude/commands/iterate-constitution.md`）。直接 Edit/Write 这三类
   文件会被 `edit-write-guard.py` Layer 5 阻断。本条款只声明"必须走该 skill"
   的阻塞规则；具体 step 见 skill 文件本身（Skill 单一权威源原则，见 附录）。

   总宪法（agent-core）vs 子宪法（4 clones）的修改边界、决策标准、
   commit message 强制模板详见
   `knowledge/governance/constitution-protection-mechanism.md`。
   **硬性约束**：子宪法不得放宽总宪法的约束（只能更严格或补充细节）；冲突时以总宪法为准。

4. **监督机制（五层防御）**：Pre-commit hook + 核心条款清单（见附录）+
   commit message 强制模板 + Core agent 自动审计（`tools/audit_sub_constitutions.py`）+
   人工定期审查。详细 layer 表 + pre-commit hook 阻止规则见
   `knowledge/governance/constitution-protection-mechanism.md`。

   **不可豁免**：核心条款的修改、`Scope: cross-agent` commit、`Violates-Core: YES` commit、
   缺 `[CONSTITUTION_CHANGE]` 标签 → 一律 pre-commit 阻断，提示走提案流程。

---
