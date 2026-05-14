---
theme: rules
---

# 个股失败模式诊断（per-stock over-signaling / under-precision）

当用户发现某只股票在 Dense Test 或 OOS 中信号多但准确率低，用此流程定位根因。

**重要提醒**（2026-04-17 修订）：不要一眼下"低 base rate 导致失败"的结论。**HK.01801 案例证明**：多只高 base-rate 股的 pure XGBoost AUC 其实也很差（0.16-0.33），只是 base rate 自动托底。真实的失败三条件：(1) 模型 AUC 弱 + (2) base rate 不够高 + (3) hybrid 规则频繁通过。只有三者同时命中才暴露问题。

## 触发场景

- 用户说"HK.XXXX 信号多但差"、"某只股一直拖后腿"、"模型对某只股票过度自信"
- Dense Test 或 OOS 的 per-stock precision 出现极端差值
- 需要决定"是否把某只股票加入 excluded_stocks"

## 诊断步骤

### 0. 先做 Simpson 分解 + lift 分析（必做）

**S50 Dense Test 的实证已证明**：aggregate AUC 可能看起来还行，但这是股票级排序的功劳，不代表模型能择时。必须分别看：

```python
from sklearn.metrics import roc_auc_score
import numpy as np
# (a) pooled
pooled = roc_auc_score(df[label], df["prob"])
# (b) within-stock weighted mean
per_stock = [(c, len(s), roc_auc_score(s[label], s["prob"]))
             for c, s in df.groupby("code")
             if (s[label]==1).sum() >= 3 and (s[label]==0).sum() >= 3]
within = np.average([a for _,_,a in per_stock],
                    weights=[n for _,n,_ in per_stock])
# (c) centered
df["p_c"] = df["prob"] - df.groupby("code")["prob"].transform("mean")
centered = roc_auc_score(df[label], df["p_c"])
```

判断：
- `pooled >> within` ≈ 0.7 vs 0.5 → 模型是**股票选择器**，时间维度没信号
- `centered ≈ 0.5` → 确认时间维度是盲的

### 0b. Lift 分析：规则 vs 模型谁在真正贡献

```python
lift = gate_precision - base_rate  # per stock
```

S50 实证：规则在大多数股票上拉 +20~34pp（**这才是真正的信号**）。Pure XGBoost prob 的贡献很小，主要是 base rate 排序。

### 0c. 识别问题股的方式（改过的）

不是"AUC 最低"，而是**"lift 比同基准率同伴少一半以上"**。例如 HK.01801 base 50% lift +12.8pp，同基准率峰值是 +30pp+，**规则对它衰减**。

### 1. Per-stock 综合表：信号量 + base + AUC + lift

### 1. Per-stock 信号量 + precision 排名（step 1 已降为辅助）

```python
df = pd.read_csv("artifacts/<pipeline>/analysis/dense_predictions.csv")
df_has_label = df[df.get("label_available", True) == True]
sig = df_has_label[df_has_label["is_signal"] == True]
stats = sig.groupby("code").agg(
    n=(label_col, "size"),
    tp=(label_col, "sum"),
).assign(precision=lambda g: g.tp / g.n)
stats["base_rate"] = df_has_label.groupby("code")[label_col].mean()
print(stats.sort_values("n", ascending=False).head(20))
```

识别"信号量 top 但 precision 落在 bottom"的股票作为目标。

### 2. 选对照组（peers）

在目标的±30% 信号量范围内，挑 5-8 只 precision 显著更好的股票。避免比较极端高/低信号量股票。

### 3. TP vs FP 特征均值对比

对目标股票 signal rows：
- `prob` 均值：TP vs FP 分别是多少？**FP prob 反超 TP 是"负校准"强信号**
- `votes`（S50）或 `rule_hits`（S30）分布
- `max_deviation(_new)` 均值：FP 常在 0.15-0.19（擦着 20% 线）
- 对每条 hybrid 规则的特征值：TP vs FP 是否一致方向

同样对 peers 的 signal rows 做一遍作基线。

### 4. 时间序列：regime drift 检查

把目标股的 signal rows 按 trade_date 排序打印：`date / prob / votes / tier / label / maxdev`。观察：
- 是否存在明显的"前段全 TP，后段全 FP"分段？
- 分段边界是什么时间？
- 分段前后 maxdev 均值差多少？

如果存在分段，说明**股票自身波动率 regime 切换**，但 hybrid 规则没感知到。

### 5. 全行特征对比（非仅 signal 行）

目标股 vs peers 在**所有 rows**（不仅 signal）上的：
- base_rate：目标明显低（如 50% vs peers 78%）→ 股票本质上是"更难"
- max_deviation 均值：目标低 → 股票波动幅度普遍更小
- hybrid rule 特征均值：如果目标只是**略**高于 peers，模型会误判为"值得 signal"但实际不值得

### 6. OOS 交叉验证

在 `artifacts/<pipeline>/analysis/oos_predictions.csv` 中检查目标股票的 OOS 表现。如果 OOS 也差（precision < 30%），失败模式持续，不是 Dense Test 偶然事件。

## 根因归类

| 诊断信号 | 根因类别 | 缓解方案 |
|---------|---------|---------|
| FP prob 反超 TP（负校准） | 特征-标签在该股上解耦 | 排除 或 加 per-stock base_rate 特征 |
| 时间段分段明显 | Regime drift 不被规则感知 | 加 stock-level rolling volatility 特征 |
| 目标 base_rate << peers | 训练集由高 base_rate 股主导 | 分层阈值：低 base_rate 股要求更高 prob |
| 所有分层都接近 peers | 真实模型缺陷 | 重新审视特征集 |

## 诊断脚本模板

参考 `rules/strangle/_analyze_01801.py`——里面实现了步骤 1-5，可改 `TARGET` 和 `PEERS` 复用。主要输出：
- Per-stock signal-row 一览表
- 目标 TP vs FP 特征均值对比
- Peers combined TP vs FP 基线
- 全行分布对比
- 目标所有 signal 逐行时间序列

## 实施缓解时的决策顺序

1. **方案 A（低风险）**：先加 `artifacts/<pipeline>/production/excluded_stocks.json` 排除，立即生效。确认 OOS 改善后保留
2. **方案 B（中风险）**：加 `stock_hist_base_rate_60d` 特征重训，观察该股是否被自然 down-weight。若是，其他类似股票也受益
3. **方案 C（低风险可逆）**：加分层阈值门控——`if stock_hist_base_rate < 0.60: require_prob >= 0.72`，写入 `config/strangle*_config.json`

**优先级**：A 最快但只解决当前股，不治本；B/C 治本但需要实验验证。

## 关联

- `knowledge/domain/stock_level_base_rate_failure.md` — HK.01801 的完整案例
- `knowledge/domain/hk_market_regime.md` — 市场级 regime 分析（本文档是个股级的对应）
- `artifacts/<pipeline>/production/excluded_stocks.json` — Wilson CI 2-tier 排除名单
