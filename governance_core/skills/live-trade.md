---
name: 实盘交易执行
description: 运行实盘交易（真实下单到交易所，需确认安全检查）
theme: trade
allowed-tools:
  - Bash
  - Read
  - Glob
user-invocable: true
when_to_use: "当用户明确要求实盘交易、live trade、真实下单时使用"
---

# 实盘交易执行

⚠️ **实盘模式** — 将发送真实订单到港交所。与 Paper 使用完全相同的业务逻辑（宪法第八条）。

## 安全确认

执行前必须向用户确认：
1. `config/trade_config.json` 中 `trading_mode.mode` 已设为 `"live"`
2. 今日信号已生成且参数合理
3. 风控参数已检查（max_daily_opens、min_profit_rate）
4. 用户明确同意执行

## 前置检查

1. **Futu OpenD 预检**（宪法第十五条）:
   ```bash
   python -c "import socket; s=socket.create_connection(('127.0.0.1',11111),timeout=3); s.close(); print('OK')"
   ```
   若不通，启动 daemon:
   ```bash
   cd C:/Users/naphe/AppData/Local/Programs/Python/Python311/pythonProject1/agent-core && python -m skills.start_futu_opend
   ```

2. **配置检查**: `trading_mode.mode` 必须为 `"live"`，否则入口拒绝启动

## 执行命令

### 单次执行
```bash
python -m trade.tests.test_live_order
```

### 常用参数
| 参数 | 说明 | 示例 |
|------|------|------|
| `--date` | 指定信号日期 YYYYMMDD | `--date 20260331` |
| `--skip-freshness` | 跳过信号新鲜度检查 | |
| `--skip-session-check` | 跳过交易时段检查（盘后验收测试） | |
| `--no-record` | 不写入持仓（验收测试模式） | |
| `--rounds` | 覆盖最大追价轮数 | `--rounds 10` |
| `--interval` | 覆盖追价间隔秒数 | `--interval 3` |
| `--max-time` | 覆盖追价最大时间秒数 | `--max-time 120` |

### 验收测试（不下真单的安全验证）
```bash
python -m trade.tests.test_live_order --no-record --skip-session-check --skip-freshness
```

### 调度模式（持续轮询）
```bash
python -m trade.scheduler --live [--no-record] [--poll-interval 360]
```
调度器在交易时段内持续轮询，自动触发 live pipeline。

## 产出
- 持仓写入 `trade/purchased_options_live.json`
- 订单通过 Futu OpenSecTradeContext 发送
- Stage 6 并行执行 CALL+PUT strangle pair（ThreadPoolExecutor）
- 原子判定：BOTH_FILLED → 写入持仓；BOTH_FAILED → 跳过；ROLLED_BACK → 回滚

## 执行后必须核对
- Futu 客户端确认订单状态和成交价格
- 运行 `/reconcile` 对账确认系统记录与实际持仓一致
