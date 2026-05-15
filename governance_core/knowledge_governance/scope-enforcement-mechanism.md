---
title: Scope Enforcement Mechanism (Constitution Article 12 §3 detail)
status: active
created: 2026-05-07
updated: 2026-05-07
owner: core
tags: [governance, scope, security, art12, hooks, boundary]
---

# Scope Enforcement Mechanism — Operational Detail

> **Example content disclaimer**: The specific examples in this document (stock symbols, pipeline names like Strangle/S50, Futu OpenAPI references, etc.) are drawn from the Trade Agent project where governance-core was first developed. The patterns and principles are project-agnostic; downstream projects should substitute their own domain examples when applying the principles described here.


Originally Constitution Article 12 §第3款 技术执行机制（四层防御）.
Migrated here on 2026-05-07 per `proposals/prefix_cost_optimization.md`
Phase C1 (extraction commit: see git log). The constitution keeps:

- §第1款 Agent Scope 定义
- §第2款 跨仓库写入禁止
- §第3款 简化：四层防御 + 一层会话边界 count + 不可豁免声明 + pointer
  to this file
- §第4款 不可豁免条款
- §第5款 提案流程

This file contains:
- §1 — Two-tier defense semantics (intra-project scope vs session boundary)
- §2 — Intra-project scope defense (4 layers within each clone)
- §3 — Session boundary defense (1 layer at user-global level)
- §4 — Override channel + bootstrap installer notes
- §5 — Cross-references

These remain CONSTITUTIONAL constraints — the inline residue declares the
invariant ("4 layers + 1 boundary"); this file enumerates the
implementation.

---

## 1. Two-tier defense semantics

防御分两层语义：

- **项目内 scope 防御**（3 层 + 配置，前 4 项）保证 5 clone 互不串写——
  即使多 clone 都挂在同一 Claude Code working-directories 列表，agent
  也不能从一个 clone 改另一个 clone 的文件。
- **会话边界防御**（1 层用户全局，第 5 项）保证任何 cwd 启动的 Claude
  session 不能跨项目越界写——即使 agent 跑出本 project 之外想改 ~/.ssh
  或 system 文件也被拒。

两组互补：前者管 intra-project scope（multi-clone monorepo 内部边界），
后者管 extra-project boundary（用户机器上不同 project 之间）。

## 2. 项目内 scope 防御（仓库内）

### Layer 1: Git pre-commit hook

文件：`.git/hooks/pre-commit`

机制：在每 clone 的 `.git/hooks/pre-commit` 安装白名单脚本，commit 时
扫描 staged files 与 `agent_rules/<agent>.allow.txt` 比对，越权文件
拒绝 commit。

豁免：`git commit --no-verify` 一次性绕过（用户授权层）。

### Layer 2: Claude Code PreToolUse hook (Bash)

文件：`.claude/hooks/scope-guard.py`

机制：拦截 Bash 工具调用，扫描命令字符串中出现的路径与 agent scope 比对。
越权 → exit code 2 = block，Claude Code 给出 deny reason。

### Layer 3: Claude Code PreToolUse hook (Edit/Write)

文件：`.claude/hooks/edit-write-guard.py`

机制：拦截 Edit/Write 工具调用，scope 检查 + 多层 entry-point 检查
（L1 path scope, L2 size, L3 knowledge entry-point, L4 secrets,
L5 constitution entry-point）。越权 → exit code 2 = block。

### Layer 4: settings.local.json

文件：`.claude/settings.local.json`

机制：在 hooks.PreToolUse 注册 scope-guard.py / edit-write-guard.py /
data-source-guard.py / sensi-guard.py 等，确保 Claude Code 每次工具
调用前运行 hook。

## 3. 会话边界防御（用户全局）

### Layer 5: Session-boundary guard hook

文件：`~/.claude/hooks/session-boundary-guard.py`（用户全局，非 project repo）

注册：`~/.claude/settings.json` 的 PreToolUse（用户全局 hook）

机制：每个 Claude session 启动时按 `derive_session_boundary.py` 三规则
探测会话边界：
1. **声明式 `projectRoot`** — `<cwd>/.claude/settings.json` 的
   `projectRoot` 字段（trade-agent 在 5 clone 各自声明 `projectRoot: "../"`，
   把边界扩展到 `<install-root>/` 覆盖全部 clone）
2. **git toplevel** — 走 `git rev-parse --show-toplevel`
3. **cwd** — fallback to current working directory

所有 Bash/Edit/Write 工具的目标路径若在边界外则 default-deny。

### 关键路径（critical paths，永不豁免）

即使一次性 override 也不豁免：
- `~/.ssh/`
- `~/.aws/`
- `/Windows/`
- `~/.claude/settings.json` 自身
- `~/.claude/settings.local.json`
- 其他 vendor 内置敏感路径

`CLAUDE_BOUNDARY_OVERRIDE=1` 不能解锁这层（hard-block layer）。

## 4. Override channel + bootstrap

### One-shot override

环境变量：`CLAUDE_BOUNDARY_OVERRIDE=1`

约束：
- **必须 inherited from parent shell**（hook 从 sibling 进程注入的不识别）
- 不能解锁 critical paths（见 §3）

审计：用法写入 `~/.claude/cache/boundary_override_audit.jsonl`，每次
override 留痕（时间、命令、目标路径）。

### Bootstrap installer

文件：`tools/install_session_boundary_guard.ps1`

约束：**必须**由 user 在 PowerShell 终端**直接运行**（不在 Claude
session 内），否则 self-install 会被现有 boundary 阻断（installer 要写
~/.claude/hooks/session-boundary-guard.py，本身在 boundary 外）。

## 5. Cross-references

- Constitution 第十二条 §第3款 (slim residue + pointer to this file)
- Constitution 第十二条 §第4款 不可豁免条款 (本条修改 + scope 扩展 + 弱化机制都需人工审批)
- `proposals/project_boundary_guard_for_extra_project_writes.md` (v2,
  approved 2026-05-01)
- `knowledge/decisions/adr-session-boundary-guard.md` (设计决策)
- `agent_rules/<agent>.allow.txt` (Layer 1+2+3 实际白名单)
- `tools/check_scope.py` (Layer 1 实现，pre-commit 调用)
- `proposals/prefix_cost_optimization.md` §4.2 / audit §2.2 (extraction rationale)
