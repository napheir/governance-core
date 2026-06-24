---
title: Sub-Constitution Red Lines (Constitution Appendix detail)
status: active
created: 2026-05-07
updated: 2026-06-24
owner: core
tags: [governance, constitution, red-lines, sub-constitution, appendix]
---

# Sub-Constitution Red Lines — Operational Detail

> **Example content disclaimer**: The specific examples in this document (domain terminology, pipeline names, external API references, stock or asset identifiers, etc.) are drawn from the upstream project where governance-core was first developed. The patterns and principles are project-agnostic; downstream projects should substitute their own domain examples when applying the principles described here.


Originally Constitution 附录 §核心条款清单 + §判断标准 + §违宪判定流程 +
§示例. Migrated here on 2026-05-07 per
`proposals/prefix_cost_optimization.md` Phase C1 (extraction commit:
see git log). The constitution keeps the invariant principles
(子宪法不得放宽 / 加严允许 / Skill 单一权威源) + a pointer to this file.

This file contains:
- §1 — Core articles red-line table (full 10-row reference)
- §2 — Decision criteria (when sub-constitutions can / cannot diverge)
- §3 — Violation detection flow (3-stage pipeline)
- §4 — Compliance vs violation worked examples

These remain CONSTITUTIONAL constraints. Moving them to governance does
NOT relax their force. The constitution's residue Appendix declares the
invariants; this file enumerates the cases.

`tools/audit_sub_constitutions.py` uses a hardcoded `CORE_KEYWORDS` dict
(lines 28–38) as its source of truth, **not** a parser of this file or
the inline 附录 — extraction is transparent to the audit tool.

---

## 1. Core articles red-line table

以下条款为总宪法核心准则，子宪法**禁止修改、放宽或豁免**，只能引用或补充细节。

| 条款 | 核心约束 | 子宪法允许操作 |
|------|---------|---------------|
| **第零条** | 仪式（"如君所愿"） | ✅ 引用<br>❌ 移除或修改 |
| **第四条** | 配置管理 | ✅ 补充本 agent 配置说明<br>❌ 放宽"禁止 .get 兜底"<br>❌ 放宽"禁止硬编码" |
| **第八条** | 测试生产统一原则 | ✅ 补充本 agent 测试规范<br>❌ 允许 is_paper/is_live 分支<br>❌ 允许业务逻辑分叉 |
| **第九条** | Git 纪律 | ✅ 补充本 agent commit 类型<br>❌ 修改 Conventional Commits 格式<br>❌ 修改分支规范 |
| **第十二条** | Scope 执行机制 | ✅ 补充本 agent scope 细节<br>❌ 移除 pre-commit hook<br>❌ 弱化 scope-guard 检查<br>❌ 绕过三层防御 |
| **第十三条** | 宪法保护（本条款） | ❌ **完全禁止修改**（包括本附录）<br>❌ 禁止修改监督机制<br>❌ 禁止修改红线清单 |
| **第十四条** | 阶段总结纪律 | ✅ 补充本 agent 的 wrap-up 操作细节（操作手册路径、触发条件等）<br>❌ 移除"阻塞规则"<br>❌ 允许不调用 `/wrap-up` skill<br>❌ 允许手动列举 skill checklist 子集充数 |
| **第十五条** | Futu OpenD 预检 | ✅ 补充本 agent 预检场景<br>❌ 豁免预检流程<br>❌ 允许跳过预检 |
| **第十六条** | 记忆过期策略与索引规范 | ✅ 补充本 agent 记忆管理细节<br>❌ 豁免过期检查<br>❌ 移除 `updated` 字段要求<br>❌ 放宽 MEMORY.md 分区索引格式 |
| **跨条款原则：Skill 单一权威源** | 宪法任何条款引用 skill（`.claude/commands/*.md` / `.claude/agents/*.md`）时，只能以"指针 + 阻塞规则"形式出现，**禁止复述 skill 内部步骤、命令、checklist 项数**。Skill 是实施文档（快速迭代），宪法是治理文档（变更需提案）；若宪法枚举 skill 内容，两者节奏不匹配必然积累 drift（2026-04-20 rules-agent 按老 Art.14 的 3 项 checklist 做总结、漏掉 skill 已扩到 7 项的事故即为证据）。冲突时以 skill 文件为准，并视作宪法需同步更新的信号。 | ✅ 引用 skill 文件路径 + 声明阻塞约束<br>✅ 声明适用场景（触发条件、禁止事项等宪法语义层）<br>❌ 列出 skill 步骤编号或命令<br>❌ 声明 skill checklist 的项数<br>❌ 复制粘贴 skill 中的 bash 片段 |

## 2. Decision criteria

### 2.1 总宪法定义的"禁止"事项

- 子宪法**不得**放宽为"允许"或"可选"
- 子宪法**可以**增加更多禁止项（更严格）

### 2.2 总宪法定义的"必须"事项

- 子宪法**不得**豁免为"可选"或"建议"
- 子宪法**可以**增加更多必须项（更严格）

### 2.3 总宪法未涉及的领域

- 子宪法**可自主**制定规范
- 示例：data-agent 的定时任务调度规范、research-agent 的沙箱隔离规范

## 3. Violation detection flow

1. **Pre-commit hook 自动检测**：
   - 检测子宪法修改是否涉及核心条款清单中的内容
   - 检测 commit message 是否声明 `Violates-Core: NO`
   - 违规则阻断提交，提示走提案流程

2. **Core agent 审计**：
   - 运行 `tools/audit_sub_constitutions.py`
   - 对比各 agent 子宪法与总宪法核心条款
   - 生成违规报告，创建 issue

3. **人工最终裁决**：
   - 定期审查审计报告
   - 对于边界模糊的案例，由人工判断
   - 追认合规修改，要求回滚违规修改

## 4. Compliance vs violation examples

### ✅ 合规示例

**某 consumer agent 在第九条补充操作手册规范**：

```markdown
### 9.1 核心使用方法管理

在 `knowledge/operations/<agent>-manual.md` 头部展示核心使用方法（如 `governance-core upgrade`）：
- 新增核心使用方法时必须更新本 agent 的操作手册
- 不确定是否算核心使用方法时，询问用户
```

**判定**：这是对总宪法第十四条（阶段总结 → `/wrap-up` skill）的细化，未放宽约束 ✅

### ❌ 违规示例

**假设某 agent 尝试豁免配置兜底检查**：

```markdown
## 第二条：配置管理

本 agent 允许使用 `.get(key, default)` 作为兜底，以提高开发效率。
```

**判定**：这放宽了总宪法第四条的"禁止 .get 兜底"约束 ❌

## 5. Cross-references

- Constitution 附录 (slim residue + pointer to this file)
- Constitution 第十三条 (修改权限 + 监督机制)
- `tools/audit_sub_constitutions.py` (CORE_KEYWORDS dict — actual tool source-of-truth)
- `proposals/prefix_cost_optimization.md` §4.2 / audit §2.5 (extraction rationale)
