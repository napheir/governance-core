---
id: P-0067
agent: core
status: implemented
created: 2026-05-18
approved_at: 2026-05-18
started_at: 2026-05-18
implemented_in: bcfcb08
implemented_at: 2026-05-18
owner: core
---

# Proposal P-0067: Installer emits .claude/settings.local.json (hook auto-wiring)

## Trigger

P-0066 Phase 4 (governance-core self-hosting) surfaced a real packaging gap
(recorded as review #6 follow-up): `governance-core install` copies the hook
scripts into `.claude/hooks/`, but it does **not** register them — there is
no `.claude/settings.local.json` emitted and no settings template shipped in
the package (`default_config/` holds only `config.json.template`).

Consequence: every consumer project (and self-hosted governance-core itself)
must **hand-author** `.claude/settings.local.json`. P-0066 Phase 4 did this by
hand. That is not self-contained: on a fresh machine there is nothing to copy
from, and the hook→event bindings have to be re-derived each time from each
hook's docstring. The package is not "install-and-go".

A second fact reinforces this: the user-global `session-boundary-guard`
treats `.claude/settings.local.json` as a critical path and blocks an agent
from writing it directly (correct — an agent must not wire its own guards).
But `governance-core install` runs as a subprocess; the guard only inspects
Bash command strings, not subprocess filesystem effects. So **the installer
is exactly the right actor** to wire hooks: it can write the file, an
interactive agent cannot.

Why PROPOSAL_REQUIRED: changes governance infrastructure (`installer.py`) +
security-sensitive (settings.local.json registers hooks = code execution) +
affects every downstream consumer.

## Scope

### In-Scope

1. **Per-hook event metadata**: a single source of truth mapping each shipped
   hook to its Claude Code event + tool matcher. Options to decide in Phase 0:
   a package manifest (`governance_core/hooks/hooks_manifest.json`) vs a
   structured header field parsed from each hook file. The binding currently
   lives only in prose in each hook's docstring.
2. **Installer wires hooks**: `install` / `upgrade` generate or merge
   `.claude/settings.local.json`, registering every installed hook under its
   event with `${CLAUDE_PROJECT_DIR}`-relative command paths.
3. **Merge, do not clobber**: if `.claude/settings.local.json` already exists,
   merge the governance hook block without dropping the project's own
   non-governance hooks; an install-managed marker delimits the governed
   region.
4. **doctor check**: `governance-core doctor` verifies the installed hooks are
   actually registered (closes the gap where doctor passes while `/proposal`
   or guards are silently un-wired).

### Out-of-Scope (Non-Goals)

- Not changing any hook's logic or event binding — only mechanizing
  registration.
- Not registering non-governance / business hooks — only the hooks the
  package ships.
- Not removing the ability to hand-edit `settings.local.json` — the installer
  owns only its delimited governed region.

## Non-Goals

参见 Scope.Out-of-Scope。本节保留位仅供归档审查工具识别。

## Guardrails

| Guard | 适用阶段 | 关注点 |
|-------|---------|--------|
| `command-guard` | 全期 | `governance-core install/upgrade`、`git push`、发版前明示 |
| `sensitive-data-guard` | Phase 2 | 生成的 settings.local.json 写入零 token |
| `edit-write-guard` | 全期 | 改 `installer.py` 是公共层变更——在 governance-core repo 改、`upgrade` 回流 |

## Phases

### Phase 0: 设计锁定 — 事件元数据来源

- Deliverables:
  - 决定 hook→event 元数据来源（package manifest vs 解析 hook header）并锁定 schema
  - 锁定 settings.local.json 的 install-managed 区段标记 + merge 算法
- Validation: 设计经 user review
- Exit criteria: 元数据来源 + merge 策略定案

### Phase 1: 元数据 + 生成器

- Deliverables:
  - 为 13 个 shipped hook 落地事件元数据（按 Phase 0 决定的形式）
  - `installer.py` 新增 settings 生成函数：由元数据产出 hooks 块
- Validation: 生成的 JSON 合法、覆盖全部 shipped hook、matcher 正确
- Exit criteria: 给定已装 hook 集，能生成正确的 hooks 块

### Phase 2: install/upgrade 接线 + merge

- Deliverables:
  - `install` / `upgrade` 写入 / merge `.claude/settings.local.json`
  - 既有文件时只动 install-managed 区段，保留项目自有 hook
- Validation: 全新项目 install 后 settings 就位；已有 settings 的项目 upgrade 后
  governance 区段刷新、自有 hook 保留
- Exit criteria: install/upgrade 后 hook 自动接线，无需手抄

### Phase 3: doctor 校验 + 文档 + 发版

- Deliverables:
  - `doctor` 校验已装 hook 均已注册
  - architecture.md / core-manual.md 更新；gc patch bump + 发版
  - governance-core 自身用新 installer `upgrade` 一次，移除 P-0066 手抄的
    settings.local.json 维护负担（dogfood）
- Validation: doctor 对未注册 hook 报错；gc 自身 upgrade 后 settings 由 installer 管理
- Exit criteria: 包"装完即接线"，review #6 缺口闭合

## Approval Criteria

User 在批准前应能确认：

1. 安装包"自闭环"——consumer 不再需要手抄 settings.local.json
2. 事件元数据有单一权威源（不再散落在各 hook docstring）
3. merge 策略保证不误删项目自有 hook
4. 本 proposal 是公共层变更，按 P-0063 在 governance-core repo 改、消费者 `upgrade` 回流
5. 完成后 governance-core 自身改用 installer 管理的 settings（dogfood）

## Validation Plan

- Phase 1：生成的 settings JSON 合法性 + hook 覆盖 + matcher 抽检
- Phase 2：全新项目 install / 既有 settings 项目 upgrade 两路验证 merge
- Phase 3：doctor 负例（未注册 hook）+ gc 自身 upgrade 实证

## Rollback / Recovery

- **Phase 0**：纯设计
- **Phase 1/2**：`installer.py` 改动 `git revert`；生成的 settings.local.json 删除即回手抄态
- **Phase 3**：doctor / 文档改动 revert
- 总体：每 phase 是 governance-core repo 独立 commit，可逐 phase revert + republish

## Risks

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| merge 算法误删项目自有 hook | 中 | 高 | install-managed 区段标记 + Phase 2 显式 merge 验证；保留备份 |
| 事件元数据与 hook 实际行为漂移 | 中 | 中 | 元数据与 hook 同 repo、同 review；doctor 校验注册完整性 |
| 生成的 settings 在某平台 hook 不触发 | 低 | 中 | 沿用 P-0066 验证过的 `${CLAUDE_PROJECT_DIR}` + `python "<path>"` 形式 |

## State Log

- 2026-05-18: draft created by core agent (P-0067)
- 2026-05-18: body authored — P-0066 Phase 5 follow-up (review #6); to be reviewed/approved in a governance-core self-hosted session
- 2026-05-18: draft → pending (ready for approval)
- 2026-05-18: pending → approved (user directed: complete P-0067)
- 2026-05-18: approved → in-progress (begin Phase 0)
- 2026-05-18: in-progress → implemented (P-0067 complete - 4 phases)
