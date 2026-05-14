---
clause_id: art_08_test_production_unification
clause_class: constitution-clause
extracted_from: agent-core CLAUDE.md (9f31024b)
source_constitution: constitution/total.md
generic_status: generic
phase_2_action: ready-to-use
---

## 第八条：测试与生产统一原则（宪法级）


**核心原则**：测试环境通过 ≠ 生产环境正确。唯一能保证生产正确的方法是：
测试和生产走**完全相同的代码路径**。

### 8.1 禁止分叉（红线）

- **禁止**为测试（paper）和生产（live）创建两套独立的业务逻辑实现
- **禁止**出现 `if is_paper: do_A() else: do_B()` 形式的业务逻辑分支
- **禁止**创建 `xxx_paper()` 和 `xxx_live()` 这样的平行函数
- 发现已有分叉代码时，必须合并为单一实现后才能继续开发

参数化允许维度（I/O 目标 / 外部连接 / 副作用开关 / 测试辅助）、入口分层
规范（业务逻辑层 vs 入口层 + 300 行界限）、违宪审查标准（4 类 anti-pattern）
详见 `knowledge/governance/test-production-unification.md`。

**违宪判定**：§8.1 任一红线 + governance file §3 任一 anti-pattern 成立 →
违宪；commit 阻塞，必须重构合并为单实现后才能继续。

**子宪法扩展点**：各 agent 可在子宪法或 `knowledge/operations/<agent>-manual.md`
补充本 agent 测试与生产对齐的具体场景（如 Futu paper trade vs live 的连接配置），
但不得放宽 §8.1 红线或 governance file 的 anti-pattern 检查。

---
