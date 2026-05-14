---
title: 实验规程
tags: [methodology, experiment, protocol, alignment]
pipeline: [strangle, strangle50]
status: active
created: 2026-04-04
updated: 2026-04-09
owner: rules
related:
  - methodology/evaluation_metrics.md
  - methodology/known_pitfalls.md
---

> **TL;DR**: 使用 Experiment Harness 做实验。harness 自动冻结数据、验证 baseline、标准化评估。手动对齐已被淘汰。

## 推荐流程: Experiment Harness (2026-04-09 起)

```python
from rules.strangle.experiment_harness import ExperimentHarness
harness = ExperimentHarness(SNAPSHOT_PATH)
result = harness.run("my_experiment", xgb_overrides={...})
```

Harness 自动执行:
1. SHA256 校验冻结的 event_samples.csv
2. 重训 baseline → 验证 n_trees + val_aucpr 精确匹配
3. 训练实验 arm → daily-level Hybrid 评估 → 对比表

**CLI 命令**:
- `python -m rules.strangle.experiment_harness snapshot` — 推生产时冻结数据
- `python -m rules.strangle.experiment_harness validate` — 验证 baseline 可复现
- `python -m rules.strangle.experiment_harness calibrate` — 原始数据丢失时校准 targets

**Snapshot 位置**: `artifacts/strangle50/production/w150_hybrid/snapshot/`

## 手动对齐流程 (Legacy, 仅供参考)

### 1. 确认生产模型精确配置
从 `artifacts/<pipeline>/production/*/training_results.json` 提取:
- train_days, HP (depth, gamma, mcw, lr, n_estimators)
- feature list, rolling_window 参数

**不依赖 config 默认值** — config 可能在生产后被修改。

### 2. 确认日历类型
| 管线 | 日历 | 日期数 | 注意 |
|------|------|--------|------|
| S30 | event calendar | ~420 | 必须 monkey-patch `extract_trading_dates` 忽略 `full_calendar_path` |
| S50 | full_features calendar | ~719 | 无需 patch |

### 3. 确认数据一致
- `event_samples.csv` 行数、日期范围、stock pool 与生产模型训练时一致
- 如有变化须说明影响

### 4. 复现 Baseline (阻塞性)
实验 baseline 的 AUCPR / auto_precision / signal count 必须与生产模型一致:
- **delta < 0.01** 才算复现成功
- 不一致 → 停止实验排查原因

## 实验中：数据对齐纪律

**核心原则**: 旧数据行数/环境不变，新特征通过 join 补列，不重新生成数据。

理由: 重新生成可能引入日历类型、stock pool、采样参数等隐性变化，导致无法区分"新特征效果"和"数据变化效果"。

## 实验后：评估流程

### 主指标: Dense Test
- 数据: `full_features.csv` 中 test 期间所有 stock-day 行
- 指标: auto_threshold precision, AUCPR
- 无 cooldown，覆盖所有 stock-day 组合

### 辅助指标
- Dense 概率校准: 单调性 + top-bin actual rate
- Hybrid tier 逐层 precision (S50)

### 仅参考
- Event-sampled precision (20d cooldown, 数据少, 统计噪声大)

### 不使用
- Daily Top-1 / Gated Top-1 (人为约束, 不反映实际交易)

### OOS 验证 (最终门控)
1. OOS 数据必须用 **daily level** (每 stock 每天取最后一根 bar)
2. Stock pool 与历史 OOS 一致 (S50 用 63 stocks)
3. OOS base rate = 0% 的日期不参与评估
4. **OOS 只做最终确认/否决，不做模型选择**

## 审查标准

以下情况实验无效:
- [ ] Baseline 未复现 (delta > 0.01)
- [ ] 仅用 event-sampled 对比，未做 dense test
- [ ] 用 OOS 结果做模型选择
- [ ] 未说明日历类型和数据对齐状态
- [ ] 数据重新生成导致行数变化
