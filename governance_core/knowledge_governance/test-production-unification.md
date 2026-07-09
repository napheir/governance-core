---
title: Test-Production Unification (Constitution Article 8 detail)
status: active
created: 2026-05-07
updated: 2026-06-24
owner: core
carrier_class: reference
tags: [governance, testing, production-parity, art8, paper, live]
---

# Test-Production Unification — Operational Detail

Originally Constitution Article 8 §8.2–§8.4. Migrated here on 2026-05-07
per `proposals/prefix_cost_optimization.md` Phase C1 (extraction commit:
see git log). The constitution keeps the core principle ("测试和生产
走完全相同的代码路径") + the §8.1 禁止分叉 red lines + a pointer to this
file for operational detail.

This file contains:
- §1 — Allowed parameterization dimensions (originally §8.2 inline table)
- §2 — Entry-layer architecture rule (originally §8.3)
- §3 — Code-review anti-patterns (originally §8.4)

These remain CONSTITUTIONAL constraints — moving them to governance does
NOT relax their force. Sub-constitutions cannot weaken them per §第十三条
附录 红线清单 row "第八条".

---

## 1. Allowed parameterization dimensions

Test 与生产的区别**只能**通过参数化实现，不允许分叉业务逻辑：

| 允许参数化的维度 | 说明 |
|----------------|------|
| I/O 目标 | 写入哪个文件（paper.json vs live.json） |
| 外部连接 | 模拟 vs 真实 API（trd_ctx=None vs 真实连接） |
| 副作用开关 | 是否写入持仓、是否发送通知 |
| 测试辅助 | 模拟未成交轮数等测试参数 |

**禁止**参数化的内容：价格计算逻辑、验证规则、风控判断、下单流程 — 这些
必须 paper/live **完全相同**。

## 2. Entry-layer architecture rule

- **业务逻辑层**：唯一实现，接受参数化模式对象，不感知自己是在测试还是生产
- **入口层**：薄壳 CLI wrapper，只负责解析参数、创建连接、构造模式对象，
  然后调用业务逻辑层

入口文件（`test_live_order.py` 等）**不得包含任何业务逻辑**。如果发现入口
文件超过 300 行，说明业务逻辑泄漏到了入口层 — 必须重构为薄壳 wrapper +
统一 pipeline 调用。

## 3. Code-review anti-patterns

代码审查时，以下情况视为违宪：

1. **新增函数名带 `_paper` 或 `_live` 后缀** — 命名级别的分叉，等价于
   `if is_paper: do_A() else: do_B()`。
2. **新增 `is_paper_mode` / `is_live_mode` 条件分支（I/O 层除外）** — I/O
   层（写文件、API 连接）允许参数化，业务逻辑层禁止。
3. **两个文件中出现高度相似的业务逻辑（复制-粘贴-微调模式）** — 必有
   parameterizable 抽象点未提取，必须重构为单实现 + 参数。
4. **入口文件包含 stage 函数调用序列（应调用统一 pipeline 函数）** — stage
   级编排是 pipeline 层职责，入口只能调一次 `run_pipeline(mode)`。

## 4. Why this matters (rationale)

Test 通过不等于生产正确。两个证据来源在历史事件中反复证实：
- Paper-only 验证的 trade flow 在 live 因 race condition 失败（mock vs
  real broker latency 差异）
- Migration 在 paper 数据集上跑通，生产首次运行因 schema variant 失败

唯一能保证生产正确的方法是：测试和生产**走完全相同的代码路径**，
区别只在 I/O 边界的参数化开关。任何业务逻辑层的分叉（如本文 §3 列出的
4 类 anti-pattern）都引入"测试通过 / 生产失败"的可能性，违宪。

## 5. Cross-references

- Constitution 第八条 (slim residue + pointer to this file)
- 第十三条 附录 红线清单 — Art.8 row（子宪法不得放宽 ban）
- `proposals/prefix_cost_optimization.md` §4.2 (extraction rationale)
