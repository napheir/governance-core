---
theme: universal
---

# Skill: start-futu-opend

Futu OpenD 自动启动技能。在需要 Futu API 的操作前，确保 OpenD 无头 daemon 就绪。

## 触发条件

以下操作前必须检查并确保 Futu OpenD 运行：
- 数据采集（K线、行情、板块数据）
- 模型训练（需要拉取实时/历史数据时）
- 交易执行（下单、查询持仓）
- 任何调用 `futu` 库的操作

## 检测（快速端口检查）

在执行上述操作前，先用以下命令快速检测端口：

```bash
python -c "import socket; s=socket.create_connection(('127.0.0.1',11111),timeout=3); s.close(); print('OK')"
```

- 输出 `OK` → OpenD 已就绪，直接继续任务
- 连接失败 → 执行启动流程

## 启动

```bash
cd agent-core && python -m skills.start_futu_opend
```

- Exit code 0 → daemon 已就绪，继续任务
- Exit code 1 → 启动失败，报告用户
- Exit code 2 → 首次使用，需要用户配置 FutuOpenD.xml（见下方）

## 首次配置

exit code 2 表示 `FutuOpenD.xml` 不存在或含占位符。用户需要：

1. 编辑 daemon 目录下的 `FutuOpenD.xml`
2. 填入 `login_account`（Futu 账号）
3. 填入 `login_pwd_md5`（密码的 32 位 MD5）
   - 生成命令：`python -c "import hashlib; print(hashlib.md5(b'YOUR_PASSWORD').hexdigest())"`
4. 重新运行 skill

## 失败处理

- exit code 1 时，向用户报告："Futu OpenD daemon 启动失败，请检查配置后重试。"
- exit code 2 时，向用户报告生成了模板文件的路径，引导填写凭证
- **不要**自动重试
- **不要**尝试修改配置或查找其他路径

## 配置

- 非敏感参数（daemon 路径、端口、超时）：`config/infra_config.json`（进 git）
- 登录凭证：daemon 目录下的 `FutuOpenD.xml`（仓库外，不进 git）
