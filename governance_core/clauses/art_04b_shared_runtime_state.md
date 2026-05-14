---
clause_id: art_04b_shared_runtime_state
clause_class: constitution-clause
extracted_from: agent-core CLAUDE.md (9f31024b)
source_constitution: constitution/total.md
generic_status: mixed
phase_2_action: needs-config-injection
---

## 第四条之一：共享运行时数据


某些数据本质上是"机器对外部真实状态的转录"（典型：持仓 = Futu broker 状态镜像），
用 git 管理会持续制造 stash/reset/merge 冲突（见 2026-04-08 SMIC 事件）。
此类数据遵循以下规则：

1. **禁止进任何 git repo**：物理位置统一在 `pythonProject1/shared_state/`（所有 clone 之外）
2. **单一物理副本**：不允许跨 clone 复制或同步（git 不是传输层）
3. **写入必须使用文件锁**：`filelock` 库 + `os.replace()` 原子写，避免半写与并发冲突
4. **路径必须由配置文件提供**：禁止硬编码，走 `config/{agent}_config.json` 的
   `position_state_dir` 字段（遵守第四条"禁止 `.get` 兜底"）
5. **Bootstrap 由权威方负责**：文件缺失时由重建方（如持仓 → data `sync_positions`）
   重建；消费方遇缺失应 fail-fast，不得绕道自建

### 子目录与写权限

| 子目录 | 写权限 | 权威方（Bootstrap） | 消费方 |
|--------|--------|---------------------|--------|
| `shared_state/positions/` | trade（新增 entry）+ data（close/add/account 字段） | data `sync_positions` | trade scheduler, data, rules |
| `shared_state/knowledge/` | all 5 agents（任一 clone 跑 `/dashboard` 即写入 `dashboard.html`） | core agent（mkdir + README；`config/dashboard_config.json` 提供 output_path / lock_path / lock_timeout_sec） | user 浏览器（`file://` read-only） |
| `shared_state/proposals/<agent>/` | 各 agent 自身（写自己子目录的 in-flight proposals；`<agent>` ∈ {core, rules, trade, data, research}） | 各 agent 自身（`/proposal create` 自动 mkdir + filelock 分配 id 通过 `_id_ledger.json`） | all 5 agents（读跨 agent 提案）+ `session-context.py`（渲染 pending）+ owner agent（terminal 状态自档案到 `proposals/_archive/<YYYY>/` 进 git，详见 Art.5.1）|
| `shared_state/proposals/_id_ledger.json` | all 5 agents（filelock 内 RMW append 分配条目） | core agent（migrate 脚本初始化；详见 Art.5.1） | proposal_lib allocate-id + audit_proposals |

### 并发安全要求

- 锁文件：`<目标文件>.lock`，与目标同目录
- 锁内时长：< 100ms（仅 Read-Modify-Write），禁止长时持锁
- 原子写：写临时文件 → `os.replace()` 替换目标

### 审计冷备

对于可能从 git 丢失而本身有历史价值的数据（如已平仓持仓 history），
权威方必须同时 append 一份只增不改的 audit ledger 到本 agent scope 内
（如 data 的 `data/audit/closed_positions/{YYYY-MM}.jsonl`），由本 agent 自动 commit。

### 新增共享数据的流程

新增 `shared_state/` 子目录必须走 `proposals/` 流程，由 core agent 审批并更新：
1. 本条（第四条之一）的子目录表
2. 相关 agent 的 `agent_rules/{agent}.allow.txt`
3. 如有跨 repo 写入需求，评估 hook 白名单是否需扩展

---
