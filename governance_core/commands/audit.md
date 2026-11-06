---
theme: core-only
owner: core
---

# /audit - Scope 与宪法合规审计

运行完整的项目合规审计。

## 工作流

1. **Scope 合规（分支审计，P-0135）**：对 `.governance/config.json` 的 `agents` 中每个非 core agent，在 core 仓库里运行
   `python tools/check_scope.py --audit-branch --agent <name> --repo ../<clone_dir>`。
   - 命令会把该 clone 当前检出的提交拉取到 `refs/gc-audit/<name>`，再对照 core ref 上的允许规则，
     检查它与 core ref 的 merge-base 以来的全部净改动。
   - 若该分支已推送，再审计远端：先 `git fetch origin <branch>`，然后对 `--ref origin/<branch>` 再跑一次。
   - exit 1：报告越权文件、相关提交和文件属主；exit 2：审计无法运行（例如 core ref 上缺 allow 文件），报告原因。
   - 单 agent 项目：`[N/A — single-agent topology — skipped]`。

2. **子宪法审计**: 运行 `python tools/audit_sub_constitutions.py --verbose`
   - 检查 agent-rules, agent-trade, agent-data, agent-research 的 CLAUDE.md
   - 检测放宽核心条款的违规行为
   - 报告 HIGH/MEDIUM/LOW 级别违规

3. **配置安全**: 扫描 `config/` 目录
   - 检查是否有 API key、密码等敏感信息硬编码
   - 检查 `.get(key, default)` 兜底用法（违反第四条）

4. **Git 纪律**: 检查最近 10 个 commit
   - 验证 Conventional Commits 格式
   - 检查 .gitignore 覆盖是否完整

5. **Hook 基础设施**: 运行 `python tools/audit_hooks.py`
   - 检查所有仓库的 hook 文件是否齐全
   - 验证 synced hooks 版本与 core 一致
   - 检查 settings.local.json hook 注册完整性
   - 报告 permission 膨胀（>40 条）

6. **Harness 组件生命周期**: 运行 `python tools/audit_harness_expiry.py --verbose`
   - 检查所有 hook 组件的上次审查日期（>90 天为 overdue）
   - 标记退休候选（medium+ expiry likelihood）
   - 区分架构性组件（永不过期）和能力补偿组件（可能过期）
   - 报告 Architectural vs Capability-dependent 比例

## 输出格式

```
=== Scope Audit ===
[OK/FAIL] core: N files checked
[OK/FAIL] rules: N files checked
...

=== Constitution Audit ===
[OK/FAIL] agent-rules: N violations
...

=== Config Security ===
[OK/FAIL] No hardcoded secrets found

=== Overall: PASS/FAIL ===
```
