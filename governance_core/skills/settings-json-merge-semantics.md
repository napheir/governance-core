---
theme: universal
---

# settings.json + settings.local.json 加性合并语义

Claude Code 启动时同时读取 `.claude/settings.json` 和 `.claude/settings.local.json`，
**加性合并**为单一有效配置：

- `permissions.allow`：两侧合并为一个数组
- `hooks.<event>`：两侧的 entries 列表串联
- 其他顶层字段：`settings.local.json` 覆盖 `settings.json`

## 漂移风险

Hook 是串联而非覆盖 → 同一 hook 可能被登记多次：
- `settings.json` 里登记 Bash scope-guard（旧版/shell）
- `settings.local.json` 里登记 Bash scope-guard（Python 版）
- 结果：每次 Bash 调用跑两次 scope-guard

类似地，`enabledPlugins` 落在 `settings.json` 也会生效——即使用户从没在 local 声明。

## 规范

1. **唯一规范 home 是 `settings.local.json`**，这是 sync_infra 和 audit_hooks 的作用对象
2. 任何 `.claude/settings.json` 包含 `hooks` 或 `enabledPlugins`，视为漂移——走
   `proposals/` 或直接 `git rm` 清除，把内容迁到 `settings.local.json`
3. 新 clone bootstrapping 时只生成 `settings.local.json`，不要创建 `settings.json`
4. `tools/audit_hooks.py` 的 `_check_legacy_settings_json` 会自动发现违反此规范的文件

## 触发模式

在以下任何场景想到本 guide：
- 用户报告"hook 跑了两遍"或"插件莫名被启用"
- 多 clone 系统里出现"有的 agent 有问题有的没有"的不对称 bug
- 设计任何 settings 相关工具（sync、audit、新 hook 注册）
- 继承自别的项目模板，看到 `settings.json` 和 `settings.local.json` 共存

## 相关

- `tools/sync_infra.py` —— 只写 settings.local.json，不会去读/写 settings.json
- `tools/audit_hooks.py._check_legacy_settings_json` —— 漂移报警器
- Claude Code 官方文档：Settings precedence
