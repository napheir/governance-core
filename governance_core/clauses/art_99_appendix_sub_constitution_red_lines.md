---
clause_id: art_99_appendix_sub_constitution_red_lines
clause_class: constitution-clause
extracted_from: agent-core CLAUDE.md (9f31024b)
source_constitution: constitution/total.md
generic_status: generic
phase_2_action: ready-to-use
---

## 附录：子宪法修改红线


子宪法**禁止修改、放宽或豁免**总宪法核心准则，只能引用或补充细节。

**核心条款红线清单 + 判断标准 + 违宪判定流程 + 合规/违规示例**详见
`knowledge/governance/sub-constitution-red-lines.md`。

### 不可豁免原则（即使本附录被改动也必须保留）

- **加严允许，放宽禁止**：子宪法对总宪法 "禁止" / "必须" 项可加严不可放宽；
  总宪法未涉及领域子宪法可自主
- **跨条款原则：Skill 单一权威源**：宪法引用 skill（`.claude/commands/*.md` /
  `.claude/agents/*.md`）时只能以"指针 + 阻塞规则"形式出现，**禁止**复述
  skill 内部步骤 / 命令 / checklist 项数。Skill 是实施文档（快速迭代），
  宪法是治理文档（变更需提案）；冲突时以 skill 为准，并视作宪法需同步更新
  的信号（2026-04-20 rules-agent 按老 Art.14 的 3 项 checklist 做总结、漏掉
  skill 已扩到 7 项的事故即为证据）

### 强制实施

`tools/audit_sub_constitutions.py` 用 `CORE_KEYWORDS` 硬编码 dict 作为
red-line 条款的实际权威源（不解析本附录或 governance 文件）；pre-commit
hook 拦截 `[CONSTITUTION_CHANGE]` tag 中 `Violates-Core: YES` 的 commit。

---
