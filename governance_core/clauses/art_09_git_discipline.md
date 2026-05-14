---
clause_id: art_09_git_discipline
clause_class: constitution-clause
extracted_from: agent-core CLAUDE.md (9f31024b)
source_constitution: constitution/total.md
generic_status: generic
phase_2_action: ready-to-use
---

## 第九条：Git 纪律


### 不得提交的内容
- `artifacts/` — 所有输出产物
- `*.pkl` — 模型文件
- `logs/` — 日志
- `__pycache__/`、`*.pyc` — Python 缓存
- `.venv/` — 虚拟环境
- `.env`、`credentials.*` — 敏感信息

### 提交信息格式
使用 Conventional Commits，冒号后**必须**使用祈使句（imperative mood），动词原形开头，风格统一：
```
feat(scope): add knowledge/ directory to constitution
fix(guard): handle glob suffix in allow rules
refactor(harness): reduce PostToolUse subprocess overhead
docs(testing): update P4 regression test manual
chore(deps): upgrade numpy to 1.26
```

**禁止**：
- ❌ 名词短语代替动词：`feat: Notion-driven dispatcher`（缺动词）
- ❌ 动词风格混搭：同一次提交中混用 `add` / `Added` / `adding`
- ❌ 过长标题：首行超过 72 字符

### 分支规范
- `master` — 主分支，不直接推送
- `feature/rules-algorithm` — rules-agent 工作分支
- `feature/trade-strategy` — trade-agent 工作分支
- `feature/data-analysis` — data-agent 工作分支
- `feature/research` — research-agent 工作分支
- PR 合并到 master，合并前必须通过 scope gate

---
