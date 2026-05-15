---
title: 已知陷阱汇总
tags: [methodology, pitfalls, lessons-learned]
pipeline: [strangle, strangle50]
status: active
created: 2026-04-04
updated: 2026-05-06
owner: rules
briefing: serendipity
related:
  - methodology/experiment_protocol.md
  - methodology/evaluation_metrics.md
  - experiments/probability_compression.md
---

> **Example content disclaimer**: The specific examples in this document (stock symbols, pipeline names like Strangle/S50, Futu OpenAPI references, etc.) are drawn from the Trade Agent project where governance-core was first developed. The patterns and principles are project-agnostic; downstream projects should substitute their own domain examples when applying the principles described here.


> **TL;DR**: 每个陷阱都是真实踩过的坑。按类别索引，附发现日期和根因。

## 数据类

### P1: kline_lookback_days 不足导致 NaN 特征
- **发现**: 2026-03-25
- **现象**: S50 推生产后 20 天 0 信号
- **根因**: `kline_lookback_days=120` (日历日) → ~396 bars < HV400 需 400 bars → NaN → prob 被压缩
- **修复**: kline_lookback_days = 200 (日历日 → ~700 bars)
- **教训**: 新增长 lookback 特征时**必须**同步更新 kline_lookback_days

### P2: 训练-生产数据不对称
- **本质**: 训练用完整历史 CSV，生产用 API 有限回看
- **影响**: 训练能算出的特征，生产可能 NaN
- **检查**: 推生产后必须做回归测试 (R1)，对已知日期验证 prob 一致 (delta < 0.01)

### P3: OOS 用 hourly 数据导致信号量虚高
- **发现**: 2026-03-30
- **现象**: Hybrid 信号量虚高 5 倍
- **根因**: K_60M ~5 bars/stock/day，未聚合到 daily
- **修复**: OOS 数据必须 daily level

### P4: pe_ratio / turnover_rate 在 K_60M 恒为 0
- **本质**: Futu API 中这些是日线级指标，hourly K 线中恒为 0
- **影响**: 模型在这些特征上 0 splits (自动忽略)
- **教训**: 不要依赖 K_60M 中的日线级字段

## 实验类

### P5: 日历类型混淆导致虚假结论
- **发现**: 2026-03-30
- **现象**: S30 新特征看似 AUCPR +6.3%
- **根因**: `extract_trading_dates` 使用 full calendar (719 dates) 而非 event calendar (420 dates)，产生 13 windows 而非 5
- **影响**: 基线崩塌造成的幻觉，对齐后全部无效
- **教训**: 必须确认日历类型 (S30=event, S50=full_features)

### P6: Dense 和 Event-sampled 结论不同
- **发现**: 2026-03-30
- **现象**: S50 新特征在 event-sampled 上看似改善，dense test 上差异很小
- **根因**: Event-sampled 仅 345 行 (20d cooldown)，统计噪声大
- **教训**: 以 dense test 为主指标

### P7: Val→Test gap 放大掩盖过拟合
- **发现**: 2026-03-30
- **现象**: 同一特征在 13-window 环境看似有效，5-window 环境无效
- **根因**: 13-window 环境 val→test gap 31% >> 5-window 12%，新特征的"改善"是基线退化更多
- **教训**: Baseline 必须先复现，gap 异常时停止实验

### P8: Hybrid 评估用 raw K_60M 数据而非 daily-level
- **发现**: 2026-04-09
- **现象**: Hybrid 评估得到 2341 signals / 76.8%，与知识库 316 / 86.4% 严重不一致
- **根因**: 生产 Hybrid 评估用 daily-level 数据 (prob_history_dense daily agg + max_deviation.notna() 过滤 → 6934 rows, BR 44.4%)，而实验直接用 full_features.csv raw 数据 (40085 rows, BR 38.4%)
- **修复**: 必须 groupby(code, trade_date).last() 聚合 + max_deviation.notna() 过滤
- **教训**: Hybrid 评估数据口径必须与生产一致；raw K_60M 一股多行/天会虚增信号量

### P8b: CSV roundtrip 浮点精度影响 early stopping
- **发现**: 2026-04-09
- **现象**: 同一数据内存计算 vs CSV write→read 后训练，得到 79 vs 75 trees
- **根因**: 生产训练将 237 列写入 CSV 再读回，~3e-8 浮点精度变化改变 early stopping 决策
- **修复**: Snapshot 冻结 augmented+roundtripped CSV（不是原始 17 列），精确匹配生产数据流
- **教训**: XGBoost early stopping 对输入数据极度敏感，CSV roundtrip 不是无损操作

### P8c: derived feature 公式分歧（分母列名 bug）
- **发现**: 2026-04-09
- **现象**: `add_derived_features` 中 `hv50_hv200_ratio` 分母用了 `annualized_volatility200`，生产用 `historical_volatility200`
- **根因**: 9 处独立实现同一公式，某次复制时改错了列名
- **影响范围**: 仅实验脚本（harness + exp_feature_shadowing），生产推理和训练不受影响
- **修复**: `add_derived_features` 不再独立实现，委托 `IndicatorSkill._calc_derived_features`（单一权威源）
- **教训**: 相同逻辑在多处独立实现必然产生分歧。指标计算只允许一个权威源（IndicatorSkill）

### P9: 实验配置不从生产模型提取
- **本质**: 依赖 config 默认值而非 production training_results.json
- **影响**: config 在生产后可能被修改，导致 baseline 不一致
- **教训**: 从 training_results.json 提取 train_days/HP/features

### P16: indicator_skill bfill 导致标签污染
- **发现**: 2026-04-14
- **现象**: Dense test HK.00981 2025-10-24 的 `max_deviation=0.225` (label=1)，但实际未来 60 天 `max(up_dev, down_dev)=0.173` (应为 label=0)
- **根因**: `indicator_skill._calc_label()` 对 `future_max*/future_min*` 和 `max_return*/min_return*` 做了 per-stock `bfill()`。数据末端每只股票最后 ~300 bars (60 交易日) 的 rolling 结果为 NaN，bfill 用更早 bar 的 future window 值填充。用陈旧的 future_max 配当前 bar 的 close 计算偏离 = 语义完全错误
- **影响**: Dense test 6934 行中 2430 行 (35%) 的 label 被污染；109 个 hybrid 信号 (34.5%) 的 TP/FP 判定不准确；AUCPR 被低估 10.6% (0.5872 → 修复后 0.6495)；Val→Test gap 被夸大 (-23% → 修复后 -15%)
- **修复**: 删除 bfill，NaN 自然传播，下游 `filter_incomplete_features` 已有处理。用 OOS K 线数据补充 future window 覆盖到 2026-03-24，确保 dense test 覆盖到 2025-12-16
- **教训**: **前瞻型列（future_max/min/return）绝不能 bfill**。bfill 适用于缺失的历史特征，不适用于依赖未来数据的列。任何涉及 `shift(-N)` 的列，末端 NaN 必须保留

### P17: NaN 比较静默转为 false-zero 标签
- **发现**: 2026-04-14（P16 修复过程中发现）
- **现象**: 删除 bfill 后，`label1210` 等 label 列在数据末端变为 0 而不是 NaN
- **根因**: `(df[key] > threshold).astype(int)` — 当 `max_return` 为 NaN 时，`NaN > 0.25` 返回 False，`.astype(int)` 将 False 变成 0。假的负样本标签污染了 `label1210_avg_*` rolling mean 特征
- **修复**: label 生成改为 NaN-aware：return 为 NaN 时 label 也为 NaN。combination label 同理（`any_nan` → NaN）
- **教训**: **任何 NaN 比较 + astype(int) 都是 bug**。NaN 参与比较运算返回 False/NaN，直接 astype(int) 会静默转为 0。正确做法：先 notna() 筛选，再比较
- **通用检查**: `grep -n "astype(int)" *.py` 排查所有将比较结果强转 int 的代码，确认输入不含 NaN

### P21: 退市股在 universe 中造成评估指标系统性偏差
- **发现**: 2026-04-20
- **现象**: B1_60d top-2 在 dense 147 天中 46 天（31%）被 HK.00489 霸占，这 46 行 hit@0.20=0%，拉低 B1 胜率从 83.7% 到 69.7%
- **根因**: HK.00489 已退市；2025-06~08 股价 +180%（3.45→9.79）为退市前狂欢，非正常市场行为。`stock_recent_maxdev_60d` 在 Dense 期（9~10 月横盘）持续 1.5+，但 forward 60d 已是冷静期，hit rate 为 0
- **识别信号**: 当指标 top-1% 或 top-K 出现单只股票霸占 + 极端 hit rate（0% 或 100%），第一反应应是查询该股票的公司行为（退市、停牌、重大重组、M&A），而不是假定均值回归或调参
- **修复**: (1) 立即：在 `rules/strangle/_data_quality.py` 加 `EXCLUDED_CODES` 并在所有评估侧 pipeline（dense / OOS / signals）过滤，(2) 长期：迁入 `config/strangle50_config.json` → `data_filtering.excluded_codes`
- **训练 vs 评估的范围决策**: 退市前（training 期）的数据可能正常；退市窗口（dense/OOS 期）的数据是病态的。一般规则：**训练侧保留 + 评估侧剔除**，除非训练期也有已知异常
- **教训**: 真实市场 universe 会有退市/停牌股持续进入评估池。任何"极端 top-K 反而变差"的现象都要先走一遍股票级审计，而不是假定指标有缺陷

### P22: 后视峰值指标在极端值区域反预测（past_N_maxdev 结构缺陷）
- **发现**: 2026-04-20（P21 伴生发现）
- **现象**: `stock_recent_maxdev_60d` 作为 B1 score，Q5（mean=0.67）hit@0.20 66%，但 **top 1%**（>=1.10）hit 降至 51%。Q4（mean=0.38）hit 57% 反而最稳
- **根因**: past-N-day maxdev 是**后视峰值指标** — 它在一段大涨跌之后才到达峰值，而此时 forward N 天恰是冷静期。值越极端 → "涨跌已完成"概率越高 → forward 越弱
- **B1 工作区间**: past_60d ≈ 0.9~1.2（持续期，hit 80-100%）；past_60d > 1.5 需额外过滤（多数是 decay 或 delisted 类型）
- **设计教训**: 任何基于"过去最大偏离/最大波动"的指标都有这个反转尾巴。使用时需要：(a) 配 decay indicator（30d vs 60d 对比）识别"还在继续"vs"已结束"，(b) 对极端值区域独立评估 hit rate，不能假设单调
- **关联**: exp_r5 的 `B1_ratio` / `B1_slope` / `B1_filter` 变体就是为区分这两种形态而设计的，但当时还没注意到反转尾巴的量级
- **通用审查**: 任何看起来单调的"score → outcome"关系，检查尾部（top 1% / bottom 1%）的单调性是否破坏

### P20: 混用 event_samples 与连续 K-line 做 Dense 审计 lookback
- **发现**: 2026-04-20
- **现象**: 给 `dense_predictions.csv` 补齐 past-60d/30d maxdev 时，HK.09999 @ 2025/7/15 的 `stock_recent_maxdev_60d` 跑出 **0.82**（真值 ~0.12，6× 虚高）。其他股票也有 max=4.8 级别的离群值
- **根因**: 脚本把 `event_samples.csv`（事件触发采样，~1 行/月）和 OOS base cache（连续小时 bar）合并为一个日度序列，**positional lookback 60 bars 走到 2023 年的稀疏样本**，被当成"过去 60 交易日"。稀疏行 + 位置回看 = 跨年误采
- **修复**: (1) 算法改用主交易日历按"日期 N 日前"定位窗口（非按 stock 自身 row index），(2) 数据源层面 **严禁** event_samples 作为 lookback 源。实操：缺 pre-Dense 历史时拉原始 K_DAY/K_60M，通过 `rules/strangle/_fetch_dense_lookback_klines.py` 统一入口
- **教训**: Dense 审计 lookback 特征的数据源必须是 **连续原始 K 线**。事件采样有合法用途（训练输入重建），但不得作为"历史回看"的单一来源
- **宪法入**: feedback memory `feedback_dense_audit_raw_klines.md`；审查触发短语"用 event_samples 补历史做 Dense 审计" → 立即 STOP
- **关联代码**: `rules/strangle/_fetch_dense_lookback_klines.py`（拉取入口）、`rules/strangle/_augment_dense_predictions_maxdev.py`（消费示例）

### P18: Dense test 的 max_deviation 和方向数据口径不一致
- **发现**: 2026-04-14
- **现象**: 方向分析中 88% 的 winners 被归为 "neither"（涨跌均<20%），但 max_deviation 明确 >=20%
- **根因**: 方向计算用了 **daily-level rolling(60 trading days)** 的 future_max/min，但 max_deviation 是 **bar-level rolling(300 bars)** 的结果。日粒度汇总后再 rolling 与 bar 粒度上 rolling 不等价（因为 close 基准价不同）
- **修复**: 方向计算必须使用与 label 相同的方法：bar-level rolling(300) + first-bar 聚合
- **教训**: **max_deviation 的计算方法（bar-level rolling + 特定窗口大小）必须被理解和复用**，不能用 daily-level 近似替代。验算时 `max_deviation == max(up_dev, down_dev)` 必须精确匹配 (100%)

## 概率/阈值类

### P10: 概率压缩致信号无区分度
- 详见 [probability_compression.md](../experiments/probability_compression.md)
- **核心**: prob 全部 ~0.5408，无法区分质量
- **影响**: 高 vol 日信号稀释，精度从 86% 降到 69%

### P11: Base Rate Drift 使阈值策略失效
- **本质**: Val BR 59.6% vs Test BR 38.5%，差 21pp
- **影响**: 在 val 上校准的阈值在 test 上表现不一致
- **教训**: 用 lift 替代 raw precision 比较；考虑 per-window adaptive threshold

### P12: P-percentile 结构性过拟合
- **发现**: 2026-02-11
- **根因**: per-stock DoF=59 vs ~34 events/stock = 参数远超有效样本
- **修复**: 移除 P-percentile，仅用 auto_threshold

## 代码/配置类

### P13: `clear_cache()` 必须在 `load_strangle_config()` 前调用
- **本质**: config 模块有缓存，修改后不 clear 会读到旧值
- **影响**: 实验中改了 config 但代码行为不变

### P14: `_cfg` vs `cfg` 变量名
- **位置**: train_stage1.py 中使用 `_cfg` 而非 `cfg`
- **影响**: NameError（一个难以发现的 typo）

### P15: 时间轴单位混用
- **本质**: trading_days / calendar_days / bars 混用
- **案例**: kline_lookback_days=120 (日历日) ≠ 120 bars
- **教训**: 变量名加后缀 `_trading_days` / `_calendar_days` / `_bars`

### P19: 推生产未创建快照导致不可复现
- **发现**: 2026-04-15
- **现象**: S30 生产模型（2026-03-22）推生产后未创建 snapshot，之后 event_samples.csv 被重新生成（assign_tier_label NaN 处理逻辑变更 + 新增 label_avg NaN 过滤），早期滚动窗口 W0-W3 无法复现（delta 0.01~0.024）
- **根因**: promote_model.py 没有 snapshot 创建步骤，数据管线代码变更后原始训练数据丢失
- **修复**: promote_model.py 新增 Step 7 强制调用 `Snapshot.create()`，Snapshot 类支持 S30/S50 双管线
- **教训**: 推生产 = 冻结数据。没有快照的模型是不可审计的。写入 R1.3 作为强制步骤
