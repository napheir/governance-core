---
name: 持仓检查与对账
description: 查询当前持仓状态，对比 Futu 实际持仓进行对账
theme: trade
allowed-tools:
  - Bash
  - Read
  - Glob
user-invocable: true
when_to_use: "当用户要求查看持仓、对账、检查仓位、position check 时使用"
---

# 持仓检查与对账

## 前置检查

**Futu OpenD 预检**（宪法第十五条）:
```bash
python -c "import socket; s=socket.create_connection(('127.0.0.1',11111),timeout=3); s.close(); print('OK')"
```
若不通，启动 daemon:
```bash
cd C:/Users/naphe/AppData/Local/Programs/Python/Python311/pythonProject1/agent-core && python -m skills.start_futu_opend
```

## 步骤 1: 读取系统持仓

读取本地持仓记录文件:
- Paper 持仓: `trade/purchased_options_paper.json`
- Live 持仓: `trade/purchased_options_live.json`

持仓文件结构:
- `positions[]` — 当前活跃持仓（每个 strangle pair 含 call_code + put_code）
- `history[]` — 已关闭的历史持仓
- `last_updated` — 最后更新时间

汇总报告：
- 活跃持仓数量（按 stock_code 去重，一个 strangle pair = 1 持仓）
- 今日新开仓数量（entry_date = today）
- 各持仓的标的、到期日、行权价

## 步骤 2: 查询 Futu 实际持仓

通过 Futu API 查询账户期权持仓:
```python
from futu import OpenSecTradeContext, TrdEnv, TrdMarket, RET_OK

trd_ctx = OpenSecTradeContext(host='127.0.0.1', port=11111)
ret, data = trd_ctx.position_list_query(trd_env=TrdEnv.REAL, trd_market=TrdMarket.HK)
if ret == RET_OK:
    # data 包含: code, stock_name, qty, cost_price, market_val, pl_val, pl_ratio
    options = data[data['code'].str.contains('HK.')]
trd_ctx.close()
```

## 步骤 3: 对比差异

| 场景 | 含义 | 处理建议 |
|------|------|---------|
| 系统有、Futu 无 | 已过期/被平仓/手动操作 | 移入 history |
| Futu 有、系统无 | 手动开仓未记录 | 补录或标记 |
| 数量不一致 | 部分成交/手动调整 | 核实并修正 |

## 输出格式

```
=== 持仓检查报告 ===
系统持仓: N 个 (paper/live)
Futu 持仓: M 个

[OK] 匹配: X 个
[WARN] 仅系统: code1, code2 (可能已过期)
[WARN] 仅 Futu: code3 (未记录)

每个持仓详情:
  代码 | 方向 | 数量 | 成本价 | 当前价 | 盈亏 | 到期日
=== 结果: MATCH / MISMATCH ===
```

## 快捷查看（不连 Futu）

仅查看系统记录，不做对账:
```bash
python -c "import json; d=json.load(open('trade/purchased_options_live.json','r',encoding='utf-8')); print(f'Active: {len(d.get(\"positions\",[]))} positions, History: {len(d.get(\"history\",[]))}')"
```
