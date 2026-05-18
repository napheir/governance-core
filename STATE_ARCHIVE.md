# Trade Agent 项目状态文档 — Archive

> 此文件包含 STATE.md 的历史条目（超出滚动窗口的部分）。
> 按时间倒序排列（最新在前）。
> 由 `tools/rotate_state.py` 自动管理。

---

### 2026-05-18 — P-0065 Phase 2 installed-files manifest + baseline hash

- 改动：`install`/`upgrade` 写 `.governance/installed_files.json`（128 文件，
  逐文件 path + baseline_sha256 + source_version + category）；新增查询工具
  `whichlayer.py`（路径 → install-managed / business）；manifest 进 `.gitignore`
  （纯派生物）。附带修 Phase 1 遗留：`verified_at` 码不变则保留，committed
  config.json 不再 churn。
- 涉及：`governance_core/installer.py`、新增 `governance_core/tools/whichlayer.py`、
  `.gitignore`、`docs/{architecture,core-manual}.md`。
- 关键决策：Phase 0 category 枚举执行修正（去 `config`、补 `knowledge`）；
  版本维持 0.2.0（P-0065 六 phase 整体一次发版）。
- 测试：gc dogfood upgrade（128 文件 manifest）、`whichlayer` 6 路抽检、
  `doctor` exit 0。commit ef791c1。


### 2026-05-18 — P-0065 Phase 1 authorization double-gate + runtime enforcement

- 改动：governance-core 授权机制 —— install 双门（Ed25519 授权码离线验签 +
  强制 candidate-uplink 同意，双门通过才 materialize 自治层）；upgrade/doctor
  复验；运行时硬冻结（`auth-guard` PreToolUse hook，matcher `*`，授权无效即
  阻断全部工具调用，验签结果按 repo/code/key 缓存）；纯 Python Ed25519
  （RFC 8032，零运行时依赖）；`maintainer/` 签发工具；license MIT→自定义
  source-available（DRAFT）；版本 0.1.6→0.2.0。
- 涉及：新增 `governance_core/auth/`、`governance_core/hooks/auth-guard.py`、
  `maintainer/`；改 `installer.py`、`cli.py`、`hooks_manifest.json`、
  `pyproject.toml`、`__init__.py`、`LICENSE`、`README.md`、`docs/{architecture,
  core-manual}.md`、`.governance/config.json`、`.claude/settings.local.json`。
- 关键决策：授权 gate 两层（materialize 门 + 运行时硬冻结）—— user 修订原
  "install 门即够"设计；签名库=纯 Python Ed25519；uplink=GitHub issue；
  多 owner 签发台账推迟到 Phase 5 consumer registry。
- 测试：auth 自测 10/10；install/upgrade/doctor 门控；负向门（无/坏码→7、
  拒同意→8）；`auth-guard` hook（valid/篡改/缺失/缓存）；build 隔离
  （`maintainer/` + 私钥不入包）；gc 自托管 dogfood。commit 581f7e5。


### 2026-05-18 — P-0068 config-aware skills (Phases 1–3)

- 改动：单 agent skill 降级 —— Phase 1 去硬编码 4 处；Phase 2 给 7 个多 agent
  步骤加拓扑门控；Phase 3 桶 C（lesson 归档 .gitignore 例外、skill-extraction
  能力门控、STATE.md capability 进 installer）。
- 涉及：`governance_core/commands/{wrap-up,extract-skill,update-skill,
  sync-repos,sync-infra,publish-knowledge}.md`、`skills/{lesson-classification,
  _template}.md`、`installer.py`、`.gitignore`、`STATE.md`。
- 关键决策：三桶模型 A/B/C；安装完即所得；复用不 fork；3b（打包
  skills.discovery）拆出为 P-0069。
- 测试：每 phase `governance-core upgrade` exit 0 + 结构校验通过；P-0068
  commits 66d3929 / b58aee1 / 25c9bf9。

