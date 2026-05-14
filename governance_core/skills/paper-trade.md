---
name: Paper 交易执行
description: 运行 Paper 模式交易管线（模拟执行，不下真单）
theme: trade
allowed-tools:
  - Bash
  - Read
  - Glob
user-invocable: true
when_to_use: "当用户要求模拟交易、paper trade、测试交易时使用"
---

# Paper 交易执行

Paper 模式使用与 Live 完全相同的业务逻辑（宪法第八条），区别仅在 I/O 目标。

## 前置检查

1. **Futu OpenD 预检**（宪法第十五条）:
   ```bash
   python -c "import socket; s=socket.create_connection(('127.0.0.1',11111),timeout=3); s.close(); print('OK')"
   ```
   若不通，启动 daemon:
   ```bash
   cd C:/Users/naphe/AppData/Local/Programs/Python/Python311/pythonProject1/agent-core && python -m skills.start_futu_opend
   ```

2. **确认信号文件存在**: `../agent-rules/artifacts/strangle/signals/{YYYYMMDD}/signals.jsonl`

## 执行命令

### 单次执行（默认 strangle 管线）
```bash
python -m trade.tests.test_full_pipeline
```

### 常用参数
| 参数 | 说明 | 示例 |
|------|------|------|
| `--pipeline` | 管线选择 (strangle / strangle50) | `--pipeline strangle50` |
| `--date` | 指定信号日期 YYYYMMDD | `--date 20260331` |
| `--skip-freshness` | 跳过信号新鲜度检查（测试用） | |
| `--test-chase` | 模拟 N 轮未成交追价 | `--test-chase 5` |

### 示例
```bash
# S50 管线，跳过新鲜度检查
python -m trade.tests.test_full_pipeline --pipeline strangle50 --skip-freshness

# 测试追价逻辑（模拟5轮未成交）
python -m trade.tests.test_full_pipeline --test-chase 5
```

## 调度模式（持续轮询）
```bash
python -m trade.scheduler [--poll-interval 360] [--date YYYYMMDD] [--skip-freshness]
```
调度器在交易时段（11:30-16:00）内持续轮询新信号，午休（11:55-13:05）暂停。

## 产出
- 持仓写入 `trade/purchased_options_paper.json`
- 日志输出 7 个 Stage 的执行结果

## 验证
- 检查持仓文件已更新（新增 positions 或 history 条目）
- 日志无 ERROR 级别输出
- Stage 3 的 7 项风控检查全部通过
