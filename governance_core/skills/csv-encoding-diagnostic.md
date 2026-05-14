---
theme: universal
---

# CSV 编码问题诊断（先验证，再修复）

当用户报告 CSV 中文/符号显示异常（mojibake、乱码、列混在一起）时，**先验证文件本身的编码再动手改**。在本项目中，CSV 生产端几乎总是 UTF-8 without BOM；"乱码"往往是 Windows Excel 端的展示问题，不是数据损坏。

## 触发场景

- 用户说"CSV 名字乱码"、"time_key 和 name 合并了"、"中文显示不对"
- 用户在 Excel / 资源管理器打开 CSV 后报告异常
- 想加 `encoding='utf-8-sig'`、`encoding='gbk'` 做"修复"之前

## 诊断步骤（必做，按顺序）

### 1. 读原始字节判断真实编码

```python
# 用 Grep/Read 取 CSV 头部一行字节（Windows 行尾 CRLF）
# 关键：不要先用 pandas.read_csv，它会掩盖问题
import io
with io.FileIO('path/to/file.csv', 'r') as f:
    data = f.read(8000)
nl = data.find(b'\r\n') if b'\r\n' in data[:200] else data.find(b'\n')
row2_start = nl + (2 if b'\r\n' in data[:200] else 1)
row = data[row2_start:data.find(b'\r\n', row2_start)]
name_field = row.split(b',')[1]  # 按实际列位置
print('hex:', name_field.hex())
```

### 2. 识别 UTF-8 三字节序列

UTF-8 CJK 字符通常是 `e4-e9` 打头的三字节序列。例如：
- `e696b0` → 新
- `e9b8bf` → 鸿
- `e59fba` → 基

如果 hex 显示这类模式，**文件本身是合法 UTF-8**，问题在展示端。

### 3. 用 UTF-8 解码验证

```python
print(name_field.decode('utf-8'))  # 正确显示即确认
```

## 修复决策树

| 诊断结果 | 真正原因 | 处置 |
|---------|---------|------|
| hex 是 `e4-e9` 三字节 + UTF-8 解码正确 | 文件 OK，Excel 按 GBK 读才乱码 | **不要改文件**；改下游查看器（如 dashboard 直接 UTF-8 渲染，绕过 Excel）。若用户坚持 Excel 打开，才考虑写入端加 BOM（`to_csv(encoding='utf-8-sig')`） |
| hex 是 `a1-fe` 双字节 + UTF-8 解码失败 | 文件是真 GBK/GB18030 | 生产端加 `encoding='utf-8'` 改写 |
| 不同行编码混杂 | 生产时拼接了不同源 | 定位混入源头，统一编码 |

## 反模式

- ❌ 看到乱码就加 `encoding='gbk'` 去读——如果文件是 UTF-8，这会二次破坏
- ❌ 直接 `to_csv(encoding='utf-8-sig')` 覆盖——下游 pandas 默认读不识别 BOM 会报 `Unnamed: 0`
- ❌ 用 Excel "判断"文件编码——Excel 永远按系统 codepage（中文 Windows = GBK）解读无 BOM CSV
- ❌ 跳过原始字节检查，直接信 pandas 的 `read_csv` 结果——pandas 默认 UTF-8 解码可能显示 replacement 字符 `\ufffd` 而不报错

## 关联

- `common/futu_data_skill.py`：Futu 返回的 `name` 列本就是 UTF-8
- `skills/analysis/indicator_skill.py`：所有 `to_csv` 调用使用默认（UTF-8 无 BOM）
- 宪法 第七条"Windows 环境下 print/log 禁用 Unicode 符号" 针对的是**终端输出**不是文件内容，两个问题独立
