---
theme: universal
---

# /dashboard - 知识库可视化统一入口

重新生成 **shared 物理 dashboard**（4 clone 共用单文件）并输出 HTML 路径。

## 触发时机

- 手动检视 knowledge 联邦状态
- 刚 pull 了 master 更新（contracts / tools / knowledge 可能都变了）
- `/learn` 或 `experiment-manager` 自动跑过之后想再看一眼
- 任何需要"给我看一眼当前知识库长啥样"的时刻

## 执行流程

### Step 1: 生成

```bash
python tools/build_knowledge_dashboard.py
```

**必须走 `tools/` 下的统一版本**。不要用 `knowledge/build_dashboard.py`（老版本，Phase 1 已迁移；若 rules clone 还残留那个旧文件，它产出的是过时的 `artifacts/rules/knowledge/dashboard.html` 路径，不是统一产物）。

输出位置由 `config/dashboard_config.json` 指定，默认是 `<install-root>/shared_state/knowledge/dashboard.html` —— **所有 clone 共用同一物理文件**（per `proposals/shared_state_knowledge_dashboard.md`）。`filelock` 包住写入，并发安全。

### Step 2: 验证

stdout 必须含一行 `[OK] wrote <abs path to shared_state\knowledge\dashboard.html> (N categories, M entries)`。

若失败：
- `FileNotFoundError: knowledge/` — 本 clone 没 knowledge/ 目录；检查是不是在错的仓库
- Template parse error — 契约 `contracts/knowledge_index_schema.md` 要求顶层 INDEX.md 的 Subdirectory Overview 表格式，若 INDEX 被改坏会报解析错误

### Step 3: 打开

```
输出路径: <<install-root>>/shared_state/knowledge/dashboard.html
```

本地浏览器直接 `file://` 打开即用。无外部依赖、无服务端、离线可用。**任一 clone 写入此处，所有 user 视图入口立即生效**——不再需要 "core agent rebuild" 的隐性步骤。

### Step 4（可选）: 合规审计

Dashboard 只展示数据，不告诉你 "哪些 entry 违反了契约"。并行跑 audit 更全面：

```bash
python tools/audit_knowledge.py
```

两者互补：dashboard 是 human-consumable，audit 是 CI-gradable。

## Dashboard 功能（Phase 1/3/5/6 积累）

- **分类导航**: INDEX-driven 自发现，新增类别只需改 `knowledge/INDEX.md` 表格
- **Owner badge**: 每条 entry 按 agent 配色（rules=紫 / trade=青 / data=黄 / research=绿 / core=赤）
- **Supersede 链**: `⇐ supersedes` / `⇒ superseded by` 明确显示前后代
- **Referenced-by**: 反向索引 — 这条 entry 被谁的 related / supersedes 引用
- **搜索框**: 实时过滤 title + path + tags（lowercase 匹配）
- **Owner / Status chips**: "all" + 数据中真实出现的 owner/status，单选互斥
- **Tag 过滤**: 点任何 entry 行里的 tag chip 激活；独立 clear 按钮清除
- **Category 自隐**: 某类全部被过滤掉时整个 section 折叠

## 常见误用

- ❌ 每次 `/wrap-up` 手动跑一次 `/dashboard` — `/wrap-up` 不重建 dashboard；`/learn` 和 `experiment-manager` 的归档步骤里才强制重建。如果你本次没写 knowledge，dashboard 不会变
- ❌ 把 dashboard.html 当数据源 — 它是 view，不是 source；audit / 提取结论请直接读 `knowledge/**/*.md`
- ❌ 提交 dashboard.html 到 git — `artifacts/` 按第十条已 gitignore

## 相关

- Dashboard 生成器: `tools/build_knowledge_dashboard.py`（core 权威，sync_infra 扩散）
- Audit: `tools/audit_knowledge.py`
- 契约: `contracts/knowledge_frontmatter_schema.md`, `contracts/knowledge_index_schema.md`
- 写入入口: `/learn` (universal) / `experiment-manager` subagent (rules)
