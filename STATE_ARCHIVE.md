# Trade Agent 项目状态文档 — Archive

> 此文件包含 STATE.md 的历史条目（超出滚动窗口的部分）。
> 按时间倒序排列（最新在前）。
> 由 `tools/rotate_state.py` 自动管理。

---

### 2026-05-18 — P-0071 Phase 1 auth-code schema v2 + leasing + auth-guard cache fix

- 改动：codec payload schema 接受 `{1,2}` —— schema 2 携带 `expiry` /
  `revocation_feed_url` / `max_offline_days`，schema 1 保留（自托管 upgrade
  不中断，Art.8）。`auth-guard` 验证缓存键加 `verified_on` 日期维度 —— 过期码
  不再被陈旧 `valid:true` 命中（原 P-0065 缓存遗漏日期，本阶段先决修复）。
  `issue_auth_code` 默认签发 schema-2 365 天租约（`--schema` / `--expiry` /
  `--revocation-feed-url` / `--max-offline-days` 覆盖）。gc 自身重签 schema-2
  码、`config.json` 更新；版本 0.2.1→0.3.0。
- 涉及：`governance_core/auth/codec.py`、`hooks/auth-guard.py`、
  `maintainer/issue_auth_code.py`、`consumer_registry.json`、
  `.governance/config.json`、新增 `tools/test_auth_codec.py` +
  `test_auth_guard.py`、`pyproject.toml`、`__init__.py`、`docs/core-manual.md`。
- 关键决策：单一签名密钥对保留（区分 owner 靠 `consumer_id`，不分密钥）；
  schema 1 永久码仍被接受 = 过渡期不破；撤销源 URL 已嵌入新码，但拉取与
  执行属 Phase 3。
- 测试：`test_auth_codec` 11/11（双 schema 往返、过期/缺字段/篡改/未知 schema
  拒）；`test_auth_guard` 4/4（陈旧隔日 `valid` 缓存不再被信任的回归守卫）；
  upgrade/doctor exit 0；wheel 0.3.0 仅含 `governance_core*`。commit 172ee5c。


### 2026-05-18 — P-0070 Phase 2 upgrade prune (stale autonomy-layer files)

- 改动：Fix C —— `installer.py` 加 `_prune_stale`，`upgrade` 在 `_capture_drift`
  后、写新 manifest 前比对旧 manifest 与新 install 集，旧有新无的
  install-managed 路径删除（manifest-diff = 安全边界）+ `[prune]` 报告 + 空
  目录清理；`cli.py` 加 `--no-prune`；版本 0.2.0→0.2.1。一次性清掉 P-0069
  早于 manifest 残留的 `shared-code-per-agent-state.md`。
- 涉及：`governance_core/installer.py`、`cli.py`、`pyproject.toml`、
  `__init__.py`、`docs/{architecture,core-manual}.md`。
- 关键决策：manifest-diff 安全边界 —— business/authored/`learned/` 从不进
  manifest，故从不被 prune；prune 在 drift 捕获之后（被改过的陈旧文件先成候选）。
- 测试：`_prune_stale` 单测 5 项、探针文件真实 dogfood（装入→源删→upgrade
  prune）、upgrade/doctor exit 0、build 0.2.1。commit f09648c。P-0070 两 phase
  全部完成。


### 2026-05-18 — P-0070 Phase 1 audit_proposals path + tracker reason fixes

- 改动：Fix A —— `audit_proposals.py` 改用 `load_proposals_config` 解析
  in-flight 目录 + `_id_ledger.json`（与 `proposal_lib.py` 同源，不再硬编码
  父级相对路径）。Fix B —— `tracker.py` 加 `should_extract_reason()`，
  `--should-extract` CLI 区分 already-extracted-today / below-threshold /
  recommended、报实际原因；stats 加 `should_extract_reason` 字段。
- 涉及：`governance_core/tools/audit_proposals.py`、
  `governance_core/discovery/tracker.py`。
- 关键决策：两个均纯报告修复，不动 `should_extract()` 启发式；tracker CLI
  改 `sys.stdout.write`（避 `constitutional-review` 对 print 的拦截）。
- 测试：自托管 gc `audit_proposals` 报 in-flight=1/archive=4/0 failures
  （误报 ledger FAIL 消失）；`--should-extract` 正确报 "already extracted
  today"；`should_extract_reason` 单测。commit 0b5b870。


### 2026-05-18 — P-0065 Phase 5 hub-side curation + convergence loop

- 改动：GC 侧 curation 收口闭环 —— 新增 consumer registry 模块
  `governance_core/candidates/registry.py` + committed 台账
  `maintainer/consumer_registry.json`（记已签发消费者 + 候选评审决策）；
  `issue_auth_code.py` 签发即登记消费者；`tools/candidate.py` 加
  `review`/`promote` 子命令；GC 侧 incoming `candidates/` 进 `.gitignore`；
  收口 hub 模型写入 `docs/architecture.md` + `docs/core-manual.md §11`。
- 涉及：新增 `candidates/registry.py`、`maintainer/consumer_registry.json`；
  改 `tools/candidate.py`、`maintainer/issue_auth_code.py`、`.gitignore`、
  `docs/{architecture,core-manual}.md`。
- 关键决策：registry 落 maintainer 侧、committed（durable 台账）；`promote`
  按 kind 复制进包源、judgment 人工/agent；GitHub issue 为候选权威记录。
- 测试：`issue_auth_code` 登记 registry、curation 11 项（review/promote/
  reject、registry 内容）、upgrade/doctor exit 0、build 隔离。commit f5b23f7。
  P-0065 六 phase 全部实现完成。


### 2026-05-18 — P-0065 Phase 4 candidate collection + submit + uplink

- 改动：候选管道三来源 —— 脱敏扫描器 `sensitive_scan.py`（HIGH/MEDIUM 分级）
  + `sensitive-data-guard` PreToolUse hook（user 选 Option B：补全 README 一直
  宣称却缺失的安全 hook）；`candidates/collect.py`（净新增 candidate-common
  skill 收集）；`candidates/uplink.py`（脱敏扫描 + `gh issue` 传输 + dry-run +
  体积上限）；CLI `tools/candidate.py`（collect/submit/uplink，consent 门）；
  `/submit-candidate` 命令；installer `_capture_drift`（upgrade 覆盖前捕获
  install-managed 文件漂移成 drift 候选 + stderr 报告）。
- 涉及：新增 `governance_core/sensitive_scan.py`、`hooks/sensitive-data-guard.py`、
  `candidates/{collect,uplink}.py`、`tools/candidate.py`、
  `commands/submit-candidate.md`；改 `installer.py`、`hooks_manifest.json`、
  `.gitignore`、`.claude/settings.local.json`。
- 关键决策：`sensitive-data-guard` 原不存在 → Option B 补全；payload 内联
  issue body（~60KB 上限）；漂移=捕获后覆盖（不留 override）；uplink 带
  `--dry-run`。
- 测试：扫描器+hook 16 项、Part A 8 项（collect/submit/uplink/secret-abort/
  consent-gate）、Part B 漂移真实 dogfood、upgrade/doctor exit 0、build 隔离。
  commit 47fdf8f。


### 2026-05-18 — P-0065 Phase 3 candidate envelope + layer tagging

- 改动：新增 `governance_core/candidates/`（envelope 模块：三 kind
  skill/hook/mechanism + drift 类；`build_envelope` / `validate_envelope` /
  `validate_metadata` / `make_candidate_id`）；新增 CLI
  `tools/validate_candidate.py`；`discovery/extractor.py` 加 `--layer` flag →
  写 learned skill `layer:` frontmatter；`extract-skill.md` 插入 layer 分类
  步骤；`lesson-classification.md` 加 generic-vs-project 轴。
- 涉及：`governance_core/candidates/{__init__,envelope}.py`、
  `governance_core/tools/validate_candidate.py`、`discovery/extractor.py`、
  `commands/extract-skill.md`、`skills/lesson-classification.md`。
- 关键决策：`layer ∈ {candidate-common, business}`，默认 candidate-common
  （过报便宜、漏报无声）；envelope 目录式（candidate.json + payload 子目录）。
- 测试：13 项单测、真实 extractor `--layer` 跑通、upgrade/doctor exit 0、
  build 隔离。commit 1d2a575。


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

