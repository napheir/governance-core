---
clause_id: art_07_code_standards
clause_class: constitution-clause
extracted_from: agent-core CLAUDE.md (9f31024b)
source_constitution: constitution/total.md
generic_status: generic
phase_2_action: ready-to-use
---

## 第七条：代码规范


1. 所有函数必须有 **docstring**
2. 使用 **type hints**
3. 使用 `logging` 模块，**禁止** `print` 用于日志
4. 新代码放对应模块，legacy 代码保持在 `legacy/`
5. 不随意添加新依赖，需先讨论
6. 所有 Futu API 调用通过 `common/` 封装，必须有 try-except，必须关闭 Context
7. Windows 环境下**禁止**在 print/log 中使用 Unicode 符号（✅ ❌ ✓ ✗ ⚠️），使用 ASCII 替代（[OK] [FAIL] [PASS] [WARN]），避免 GBK 编码错误

---
