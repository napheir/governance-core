---
theme: universal
---

# /publish-knowledge - 知识库跨 agent 发布

把本 clone 的 `knowledge/**` 写入推到 origin，让 master 上的统一 dashboard
能看见此次内容。若是 core agent 调用，还会跨 clone 采集其他 agent 未推的 knowledge
到 master。

> **Topology gate (P-0068)** — multi-agent command. First read
> `.governance/config.json`; if `agents` has length 1 (single-agent
> topology), print `[N/A — single-agent topology — skipped]` and stop —
> there are no other clones to publish to. Otherwise proceed: the full
> capability below is retained for multi-agent consumers.

## 存在原因

知识库联邦模型：
- 每个 agent 在自己 scope 的 `knowledge/<subdir>/**` 写入
- `sync_infra` 单向流 core → clones，**不**路由 knowledge 内容
- 结果：knowledge 跨 agent 流通必须靠 git push + merge

历史教训（2026-04-24 两次触发）：rules 写完 EXP-2026-0010、research 写完
inspiration 库后都没 push → master dashboard 都看不见 → 用户两次 dogfood
都报 "缺了"。此 skill 把"发布"从隐性纪律变成显式、可检查、可强制的步骤。

## 触发时机

**强制调用点**（三处互相引用同一 skill，任一触发都必须走）：

1. `/learn` skill 末步（Step 7）—— 每次写完 knowledge 都触发
2. `experiment-manager` Phase 7 末步（Step 9）—— rules 实验归档闭环
3. `/wrap-up` skill 步骤 2b —— 本 phase git diff 含 `knowledge/**` 时触发

**手动调用**：用户说"推一下知识库" / "发布 inspiration" / "让 master 看到最新归档"
等时直接调。

## 执行流程

### Step 1: 检查本地未 commit 的 knowledge 写入

```bash
git status --short knowledge/
```

- 有 M / A / D 文件 → 异常，说明 `/learn` 或 `experiment-manager` 没完成 commit；
  报错并停，要求先 commit
- 无 → 进 Step 2

### Step 2: 检查未推 commits

```bash
# 对比当前分支与上游（origin/<branch>）
git log @{u}..HEAD --oneline -- knowledge/
```

- 有未推的 knowledge commits → 进 Step 3
- 无 → 退出（`[OK] nothing to publish`）

### Step 3: Push 当前分支

```bash
git push origin HEAD
```

**验证**：stdout 含 `<old>..<new>` hash 范围；非 `Everything up-to-date`。
失败（远程 diverged）→ 先 `git pull --rebase` 再重试。

**非 core agent 到这里就完成**——输出一行：
```
[OK] published <N> knowledge commits to origin/<branch>.
     Core 会在下次 collection 时把新 entries 拉到 master dashboard。
```

### Step 4: Core-only — cross-clone knowledge collection

**仅当 role=core 时执行**。扫描所有非 core clone 的 origin feature 分支，
把 net-new knowledge 文件 targeted-sync 到 master。

4.1 对每个非 core agent（rules / trade / data / research）：

```bash
git fetch ../agent-<name> feature/<branch>
# 或: git fetch origin feature/<branch>  （若已推 origin）
```

4.2 分类 knowledge/ 路径下每个变更文件（P-0055 引入 `diff_classify.py`，
取代原 `grep '^A'` 单 filter，因为它会把合法的 v1.1.0+ frontmatter 补丁
误丢——见 commit `30b197cf` 的真实 regression case）：

```bash
python tools/diff_classify.py --base HEAD --head FETCH_HEAD --paths knowledge/
```

输出 JSONL，每行一文件 `{path, status, reason, added_in_fm, removed_in_fm,
direction, ...}`。`direction`（base=master 为 hub、head=FETCH_HEAD 为 clone 时才
有意义）区分 frontmatter diff 方向：`ahead`（clone 有 hub 缺的 fm 行，
`added_in_fm>0`）/ `behind`（clone 只是落后，`added_in_fm==0 且 removed_in_fm>0`，
被删那行正是 hub 刚加的字段）/ `mixed`（两向都有）/ `na`。状态语义：

| status | 处置 |
|--------|------|
| `A` | 收（新文件，等价旧 grep '^A' 行为） |
| `M-fm-only` + `direction: ahead`/`mixed` | 收（clone 有 hub 缺的 frontmatter 行；diff 完全落在 YAML fm 区、无正文夹带） |
| `M-fm-only` + `direction: behind` | **跳过**：clone 只是落后于 hub（`added_in_fm==0`，被删行是 hub 刚 backfill 的字段）；checkout clone 版本会**静默回滚 hub frontmatter**。clone merge hub 后自动追平（issue #132） |
| `M-mixed` | **跳过 + WARN**：含 owner agent + path + 首条违例 hunk 行号；要求 owner 拆 commit 分发 |
| `D` | 跳过（沉默） |
| `?` | 跳过 + WARN：rename/copy/unmerged 不自动收 |

> **方向门（issue #132）**：`M-fm-only` **只在 `direction != behind` 时收**。
> hub 刚跨多文件 backfill 一个 frontmatter 字段、clone 尚未 merge 时，每个受影响
> 文件都是 `M-fm-only / added_in_fm:0 / removed_in_fm:>0`（`direction: behind`）；
> 若无条件 checkout clone 版本，会把 hub 刚 authored 的字段回滚掉。

4.3 对每个被收的文件（`A`，或 `M-fm-only` 且 `direction != behind`）：

```bash
git checkout FETCH_HEAD -- <path>
```

4.4 归一化 frontmatter：

```bash
python tools/migrate_knowledge_frontmatter.py --scaffold-missing-fm --execute
```

4.5 若新 entry 用了非枚举 status（`completed` / `adopted-partially` / 中文等），
手动 sed 归一化到 `{active, archived, draft, deprecated}` 之一（参见 2026-04-24
STATE 的 normalization 映射表）。

4.6 跑 audit：

```bash
python tools/audit_knowledge.py
```

**必须 Failed=0**。若因 related/supersedes 链引用到 rules 本地的 proposals/，
把那些 proposals 也一并 targeted-sync 过来。

4.7 commit + push master：

```bash
git add knowledge/ proposals/
git commit -m "docs(knowledge): collect <agent> net-new entries via /publish-knowledge"
git push origin master
```

4.8 重建 dashboard（项目自备 renderer 时；可选 —— gc #24/P-0091 已把 renderer
释放到 business 归属，gc 不再 ship）：

```bash
# 若项目拥有 renderer（tools/build_knowledge_dashboard.py 存在，business-owned）：
python tools/build_knowledge_dashboard.py
# 否则跳过——gc 治理流程不强依赖 dashboard。
```

## 不做

- **不自动开 PR**：需要 `gh` / GitHub auth / 人类审阅，留给用户手动
- **不并入 feature 分支的 M-mixed 文件**：含正文夹带的 M 文件仍跳过 + WARN，
  防止回滚 master 的 Phase 3 frontmatter 迁移或意外覆盖 body（P-0055 把
  原"不并入任何 M"放宽为只放行 M-fm-only）
- **不清 working tree**：如有非 knowledge 的 WIP（trade 业务代码 / research prototype），
  原样保留

## 失败恢复

| 失败 | 处置 |
|------|------|
| Push rejected (non-fast-forward) | `git pull --rebase origin <branch>` 再 retry |
| Step 4 merge conflict | 放弃本轮 collect（`git checkout -- .`），留给用户手动处理 |
| Audit FAIL | 不推；逐条修 FAIL 行直到 Pass |
| git fetch 失败（远程 clone 未 push） | 改用本地路径 `git fetch ../agent-<name> feature/<branch>`；或让该 agent 先自己跑 /publish-knowledge |

## 输出

```
/publish-knowledge 报告:
- 本地 knowledge 变更: 3 files (M) + 1 file (A)
- Push 结果: d71ba22..a07fa7b (pushed 4 commits)
- [仅 core] 跨 clone collection:
    rules:    2 A files pulled (EXP-2026-0011 + related proposal)
    trade:    0 (up to date)
    data:     0 (up to date)
    research: 1 A file pulled (new inspiration entry)
- Dashboard rebuilt: 76 -> 79 entries
- Audit: Passed 79 / Failed 0
```

## 与相关 skill 的关系

| Skill | 关系 |
|-------|------|
| `/learn` | /learn Step 7 调用本 skill；本 skill 不重复做 audit/dashboard |
| `experiment-manager` Phase 7 Step 9 | 同 /learn，rules-specific 包装 |
| `/wrap-up` Step 2b | 若本 phase 改过 knowledge/，调用本 skill |
| `/dashboard` | 消费端；本 skill 完成后，/dashboard 能反映最新内容 |
| `cross-clone-targeted-file-sync` | Learned skill，是 Step 4.1–4.3 的底层操作模板 |
