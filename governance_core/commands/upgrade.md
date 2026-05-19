---
theme: universal
owner: core
---

# /upgrade - 消费者升级编排（预览 → 语义审查 → 确认 → 应用）

把 governance-core 的升级从"裸 CLI 闭眼覆盖"变成 **agent 驱动的预览 + 语义
审查 + 确认 + 应用** 编排（P-0073 Phase 3）。

> `installer` 子进程**不调任何模型**。本 skill 的"语义审查"由**执行本 skill
> 的 agent**（你）来做 —— 你本身就是 LLM。纯手工 `governance-core upgrade`
> 跳过本编排;结构层(`--dry-run`)仍可手动用。

## 何时用

- `update-reminder` hook 在 session 启动报"update available"时。
- owner 主动要求升级 governance-core。

## 前提

升级是两步;本 skill 编排第二步。先确认第一步已做:

```bash
pip install -U governance-core
```

`governance-core upgrade` 只从**已装的**包重新物化自治层 —— 不先 `pip
install -U`,`upgrade` 永远是旧版。

## 步骤

### 1. 预览（dry-run）

```bash
governance-core upgrade --project-root . --dry-run
```

读报告(走 stderr):版本 delta、将覆盖文件数、**逐 drift 文件 unified
diff**、prune 集、**本地新增文件清单**。若报 `version: X -> X`(无新版)
→ 告知 owner 已是最新,结束。

### 2. 语义冲突审查（advisory —— 本 skill 的核心,由你做）

对预览报告里的两类项目逐一判断:

**a. drift 文件**（owner 原地改过的 install-managed 公共层文件）—— dry-run
已给出每个的 unified diff(owner 当前版 vs 即将覆盖的上游版)。逐个审查:
owner 的个性化意图与上游演进是否冲突?覆盖后 owner 会失去什么有意的改动?

**b. 本地新增文件**（owner 自己加的机制,不在 manifest）—— 对每个:
- `Read` 该文件,明确它解决的治理关切(如"STATE 总结只留索引,不留正文");
- 判断升级带来的增量公共层是否触及**同一关切** —— 必要时 `Read` / `Grep`
  将被覆盖的相关包源文件,或查 `proposals/_archive/` 里该版本区间的提案,
  看新公共机制做了什么;
- 若发现语义重叠/冲突(如本地"索引式 STATE"撞新公共机制"细节模板")→
  记一条 advisory:**文件 + 疑似冲突点 + 理由**。

> 这是**尽力而为,非 sound 检测** —— 会漏报会误报。只产出警示,**不阻断**。

### 3. 汇报 owner

汇总给 owner:
- 版本 delta + 跨 minor 警示(若有);
- 将覆盖 / drift / prune 的文件数;
- 第 2 步的语义冲突 advisory(逐条);若无 → 明说"未发现语义冲突(尽力
  判断,非保证)"。

### 4. owner 确认门（阻塞）

**必须**等 owner 明确确认后才进第 5 步。owner 可能选择先处理某个 drift
文件(uplink 其 drift 候选 / 把个性化挪进业务层)再升级,或暂缓。

### 5. 应用真实升级

owner 确认后:

```bash
governance-core upgrade --project-root .
```

(owner 未确认 / 要求暂缓 → 停在此,不执行。)升级后,被 owner 改过的
install-managed 文件已作为 drift 候选留在 `.governance/candidate-outbox/`
—— 提示 owner 可经 `/submit-candidate` 把仍有价值的个性化回流。

## 边界（诚实)

- `upgrade` 是**整层原子覆盖**,无逐文件可选 —— 决策是整体二元(升/不升)。
- 语义审查跑在 agent 在场时;删本 skill / 绕过编排物理上拦不住
  (P-0073 Non-Goals)。

## 与其它 skill 协作

| Skill | 关系 |
|-------|------|
| `update-reminder` hook | session 启动报新版 → 提示语指向 `/upgrade` |
| `/submit-candidate` | 升级后,把 drift 候选里仍有价值的个性化回流 hub |
