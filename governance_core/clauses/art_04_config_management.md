---
clause_id: art_04_config_management
clause_class: constitution-clause
extracted_from: agent-core CLAUDE.md (9f31024b)
source_constitution: constitution/total.md
generic_status: generic
phase_2_action: ready-to-use
---

## 第四条：配置管理

> **Example content note**: The specific agent names, directory paths, contract files, and pipeline references in tables below come from the Trade Agent project (where governance-core was first developed). Downstream projects substitute their own domain via `.governance/config.json` and project-specific clause files. The principle (multi-agent topology, directory ownership, contract-based exchange) is generic.



1. **所有配置**统一存放在 `config/` 目录，以 JSON 格式保存
2. **永远只有一份**配置文件，不允许任何副本存在于其他目录
3. **禁止** `.get(key, default)` 兜底 — 配置缺失必须立即报错
4. **禁止**在代码中硬编码任何配置参数
5. 配置加载统一通过 `config/__init__.py` 提供的函数
6. 配置文件不存在时，**立即 raise FileNotFoundError**，不提供任何默认值
7. **凡是会被多处代码引用的参数，必须写入 `config/` 配置文件，禁止在代码中硬编码。无默认值。**

### 零硬编码审查标准

以下情况视为违宪：
1. 代码中出现 `time(11, 30)` 等可配置的时间字面量
2. 新增阈值参数直接写死在函数里，没有对应的 config 字段
3. 修改参数需要改代码而非改配置文件
4. 代码中只允许出现"无争议的常量"（如 `weekday() >= 5` 判断周末、数学常数、协议固定值）

### 配置文件示例

项目按需在 `config/` 添加配置文件。命名约定：`<pipeline-or-component>_config.json`。
示例：

| 文件 | 用途 | 主要消费者 |
|------|------|-----------|
| `config/<your-pipeline>_config.json` | 业务管线参数 | `<producer-agent>` |
| `config/<consumer-agent>_config.json` | 消费方策略参数 | `<consumer-agent>` |

### 技术债

| 旧位置 | 迁移目标 | 状态 |
|--------|---------|------|
| `common/config.json` | 合并到 `config/trade_config.json` | 已清理（废弃桩已删除） |
| `common/weight_file.json` | `config/weight_file.json` | 已清理（重复副本已删除） |
| `trade/legacy/config.json` | 合并到 `config/trade_config.json` | 已关闭（文件不存在） |
| `trade/legacy/weight_file.json` | 合并到 `config/weight_file.json` | 已关闭（文件不存在） |
| `trade/config/settings.py` | 改用 `config/__init__.py` | 待迁移（trade scope，18 个文件依赖） |

---
