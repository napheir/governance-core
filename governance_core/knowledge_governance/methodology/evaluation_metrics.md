---
title: 评估指标体系
tags: [methodology, metrics, evaluation, dense, oos]
pipeline: [strangle, strangle50]
status: active
created: 2026-04-04
updated: 2026-04-04
owner: rules
related:
  - methodology/experiment_protocol.md
---

> **Example content disclaimer**: The specific examples in this document (stock symbols, pipeline names like Strangle/S50, Futu OpenAPI references, etc.) are drawn from the Trade Agent project where governance-core was first developed. The patterns and principles are project-agnostic; downstream projects should substitute their own domain examples when applying the principles described here.


> **TL;DR**: Dense test precision 是主指标。Event-sampled 仅参考。OOS 一票否决但不做选择。跨 regime 比较用 lift 不用 raw precision。

## 指标层级

| 层级 | 指标 | 用途 | 数据源 |
|------|------|------|--------|
| **主指标** | Dense test auto_threshold precision | 实验对比 | full_features.csv test 期 |
| **主指标** | Dense AUCPR | 模型判别力 | 同上 |
| 辅助 | 概率校准 (monotonicity + top-bin) | 概率质量 | 同上 |
| 辅助 | Hybrid tier 逐层 precision | S50 策略评估 | 同上 |
| 参考 | Event-sampled precision | 交叉验证 | event_samples.csv test 期 |
| **否决权** | OOS dense precision | 最终门控 | 独立 OOS 数据 |
| 不使用 | Daily Top-1 / Gated Top-1 | - | - |

## 为什么 Dense > Event-sampled

| 维度 | Dense | Event-sampled |
|------|-------|---------------|
| 数据量 | ~35,000 stock-day 行 | ~345 行 (20d cooldown) |
| 统计噪声 | 低 | 高 |
| 与生产一致性 | 高 (generate_signals 评估所有 stock-day) | 低 (cooldown 是训练采样策略) |
| 自相关 | 有 (同股票连续日) | 低 (cooldown 缓解) |

**注意**: Dense 有自相关，有效 N < 名义 N。z-test 需 cluster 修正。但总体仍远优于 event-sampled。

## 跨 Regime 比较

不同时期 base rate 不同 (val 59.6% vs test 38.5%)，raw precision 不可直接比较。

使用 **normalized lift**:
```
lift = (precision - base_rate) / (1 - base_rate)
```

| 时期 | Precision | Base Rate | Lift |
|------|-----------|-----------|------|
| Dec (OOS) | 86.4% | 45.4% | 0.751 |
| Jan (OOS) | 68.8% | 46.6% | 0.416 |

Lift 更准确反映模型真实能力变化。

## OOS 验证规范

1. 数据必须 **daily level** (每 stock 每天取最后一根 bar，非 hourly K_60M)
2. Stock pool 与历史 OOS 一致 (S50: 63 stocks)
3. Base rate = 0% 的日期不参与 (标签窗口超出数据范围)
4. OOS **只确认/否决**，不做模型选择或调参
5. "OOS 好 → 可以上线" 但 "OOS 差 ≠ 模型差"（可能是 regime 不同）

## 常见陷阱

- **OOS 用 hourly 数据**: 信号量虚高 5 倍 (K_60M ~5 bars/stock/day)
- **Dense 和 event-sampled 混用**: 差异 3-5pp，结论可能相反
- **用 test set 选模型**: 这是 model shopping，违反 test set discipline
- **Post-hoc 选择后报告 test 指标**: 需折扣 3-6pp (4-choose-1 inflation)
