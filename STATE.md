# STATE — governance-core

Session-bridge log. `/wrap-up` Step 1 prepends a dated entry under
"Updates in This Session"; `tools/rotate_state.py` archives entries older
than 7 days to `STATE_ARCHIVE.md`; `session-context.py` surfaces recent
entries at SessionStart.

This file is committed (authored governance record). Adopted by P-0068
Phase 3c — single-agent governance-core still needs a session-state bridge,
so the STATE.md capability is provided by the package (the installer seeds
an initial copy; `rotate_state.py` ships in `tools/`).

## 1. Updates in This Session

<!-- Newest entry on top. Format:
### YYYY-MM-DD — <short title>
- 改动摘要 / 涉及文件 / 关键决策 / 测试结果
-->

### 2026-07-17 — 发布 v0.42.1（P-0125：boundary-guard cmdsubst/backtick device-sink / issue #137）

- **bump**：0.42.0 → 0.42.1（`pyproject.toml:7` + `governance_core/__init__.py:6`）。patch ——
  纯误报收窄（cmdsubst/backtick 尾部 device-sink 不再被误挡），不破坏、不开真实写路径。
- **发布**：`gh release create v0.42.1`（target master）→ CI `release.yml` run 29554033647 success
  → OIDC Trusted Publisher（P-0064）。push 一度受本地代理（:7890）连接重置阻塞，恢复后成功。
- **消费者影响**：升级后 boundary-guard 不再把 `$(... 2>/dev/null)` / `` `... 2>/dev/null` `` 里
  的 discard 误判为跨界写而 block；真实 subshell 写照旧 block；引号内 `>` 仍由 P-0122 quote-mask 处理。
- **核实**：PyPI `/governance-core/json` → `latest: 0.42.1`，wheel + sdist 均在（非本地意图）。

### 2026-07-17 — P-0125：boundary-guard cmdsubst/backtick device-sink 残尾（issue #137）

- **问题**（issue #137）：P-0121/P-0122 的 device-sink 修复留了严格残尾 —— redirect 捕获类
  `[^\s&|;<>]+` 不排除 `)` `(` 反引号，于是 `$(... 2>/dev/null)` / `` `... 2>/dev/null` `` 尾部的
  discard 把闭合元字符吞进目标（`/dev/null)`），`DEVICE_SINKS` 精确匹配落空 → 误挡（exit 2）。
  `$(... 2>/dev/null)` 是极常见 shell 形态，误报持续复发。
- **诊断**：读 `session-boundary-guard.py:137`（redirect regex）+ `:371`（sink exact-match）；用真实
  hook 复现 `Target: /dev/null)`。判为 PROPOSAL_REQUIRED（改安全 hook 捕获行为，同 P-0122 血脉）。
- **改动**（全在包源 `governance_core/`，单行 + 测试）：
  - `tools/session-boundary-guard.py:137`：redirect 捕获类 `[^\s&|;<>]+` → `[^\s&|;<>()`]+`。裸重定向
    目标在 POSIX 下合法上不含 `(``)`反引号（元字符/语法错误），收窄不漏挡真实写。
  - `tools/test_session_boundary_guard.py`：加 cmdsubst/backtick sink allow + subshell 真实写回归
    （52 → 57 例）。
- **验证**：全套 57 例绿 + peer 绿；`upgrade` 重装自治层 + 重拷 user-global enforcing 副本（`upgrade`
  不碰它，它才生效）；live-dogfood 本 session Bash 跑 `$(echo hi 2>/dev/null)` + 反引号 sink 放行，
  subshell 真实跨界写仍 exit 2 拦截（且 `Target:` 不再带尾 `)`）。
- **收尾**：commit `e9a32b7`（fix）+ `87f2d8b`（archive P-0125）；issue #137 已关闭。已发布 v0.42.1（见上条）。

### 2026-07-15 — 发布 v0.42.0（P-0123：`upstreamed` 终态 / issue #136）

- **bump**：0.41.1 → 0.42.0（`pyproject.toml:7` + `governance_core/__init__.py:6`）。minor ——
  additive：新终态 enum `upstreamed` + 条件字段 `upstreamed_to`/`upstreamed_at` + Check 17，
  backward-compatible（无文件在 bump 前用该状态，无需 grandfather），契约 SemVer 同步 v1.3.0。
- **发布**：`gh release create v0.42.0`（target master）→ CI `release.yml` + OIDC Trusted Publisher（P-0064）。
- **消费者影响**：升级后 proposal 可到达 `upstreamed` 终态记录 hub provenance —— consumer proposal
  的能力上送到 hub 后不再只能在"永久 audit FAIL / 永不终结 / 丢 provenance"三条坏路里选。
  `superseded` 语义不变；写入时 fail-fast 校验 `upstreamed_to`。
- **核实**：actual published state 见本 turn 报告（`gh release list` + PyPI `/0.42.0/json`）。

### 2026-07-15 — P-0123：`upstreamed` 终态（issue #136，consumer proposal 上送到 hub）

- **问题**（issue #136）：candidate/uplink 管线把 consumer proposal 的能力上送到 hub 后，
  该 proposal 真正终结、但替代方案落在**另一仓库**，schema 无终态可表达 ——
  `superseded_by` 强制本地相对路径 + 必须存在 + 反向引用（`audit_proposals.py` Check 6），
  跨仓库引用只会永久 audit FAIL。选 issue 的 **shape B**（一等终态）而非 shape A（复用
  `superseded_by`）。
- **改动**（全在包源 `governance_core/`）：
  - 契约 `contracts/proposal_frontmatter_schema.md` → v1.3.0：§3.1 加终态 `upstreamed`；
    §4.4a 要求 `upstreamed_to` + `upstreamed_at`；§5.6 外部引用 format 规则；§7 不变式。
  - `tools/proposal_lib.py`：`VALID_STATUS` / `TERMINAL_STATUS` 加 `upstreamed`；`*→upstreamed`
    从任意态（比照 supersede）；transition 分支 + CLI `--upstreamed-to`；archive date-map；
    新增**共享谓词** `validate_upstreamed_ref`（writer + validator 同一函数）。
  - `tools/audit_proposals.py`：enum / `REQUIRED_BY_STATUS` / Check 17（format-only，**不解析**
    跨仓库引用）/ `upstreamed_at` 日期集。
  - `hooks/session-context.py`：pending banner 用 allowlist，`upstreamed` 自动隐藏（仅补注释）。
  - `commands/proposal.md`：`upstream` 子命令 + 反模式（区分 supersede）。
  - 新增 `tools/test_upstreamed_status.py`（13 例，覆盖 issue 三条验收 + 谓词 + enum 一致性）。
- **关键决策**（用户）：语法可严，但**写入时即 fail-fast**（`transition` 拒坏 ref，报含示例的
  同一条消息），owner 一次改对、不必反复撞 audit —— 故 writer 与 validator 共用谓词与消息。
- **测试**：新 13/13；rigor 18/18、design-contract 23/23、gates 全绿；audit 全库 0/58。
  **dogfood**：`upgrade` 重装后，安装层 CLI 实测 —— 坏 ref 被拒（exit 1，P-0123 未动）、
  好 ref `draft→upstreamed` 三字段齐全（throwaway P-0124 已完整清理，台账回 59）。

### 2026-07-10 — 发布 v0.41.1（P-0122：quote-aware redirect 消除引号内 `>` 误报）

- **bump**：0.41.0 → 0.41.1（`pyproject.toml:7` + `governance_core/__init__.py:6`）。patch ——
  纯误报收窄（引号内 `>` 不再当重定向），不破坏、不开真实写路径。
- **发布**：`gh release create v0.41.1`（target master）→ CI `release.yml` + OIDC Trusted Publisher。
- **消费者影响**：升级后 boundary-guard 不再把 commit message / 内联脚本里引号内的 `>` 误判为跨界
  写而 block 命令；真实未引号重定向照旧 block；引号不平衡 fail-safe。
- **核实**：actual published state 见本 turn 报告（`gh release list` + PyPI `/0.41.1/json`）。

### 2026-07-10 — P-0122：session-boundary-guard quote-aware redirect（消除引号内 `>` 误报）

- **残留（#134/P-0121 记在案）**：redirect 正则把任意 `>` 当重定向符，引号内的 `>`（commit
  message `-m "x > /path"`、内联脚本 `python -c "a >> b"`）被误当写目标 → 误 block。本 session
  每个带 `>` 的 commit 都得绕 `-F` 文件。
- **修（P-0122，approved）**：新增 `_quoted_char_mask` 纯helper（左到右追踪单/双引号态），
  `extract_bash_paths` 仅对 `redirect` label 跳过"`>` 操作符落在**平衡引号**内"的匹配。引号不平衡
  → 不信 mask、按重定向处理（fail-safe 过度 block，不 under-block）。verb 类 pattern（cp/mv/
  Remove-Item…）不受影响（需真 verb，不会对任意引号内 `>` 误报）。
- **权衡（已在 ADR 记录）**：引号内 subshell 重定向（`bash -c 'echo > /out'`）不再被抓——但那是
  subprocess 内写，**本就是 guard 的 documented non-goal**（#135 Gap B），不失任何已保证的覆盖。
- **验证**：boundary-guard 51/51（新增 47 引号内 commit-msg `>` 放行、48 内联 `>>` 放行、49 真实
  未引号重定向照旧 block、50 引号 TARGET 照旧 block、51 引号不平衡 fail-safe）+ peer 全过。
- **live 自证**：本条 commit 的 message 内联含 `>` 且未用 `-F` —— 部署后的 quote-aware enforcing
  copy 放行了它（若旧版会 block）。
- **涉及**：`governance_core/tools/{session-boundary-guard.py, test_session_boundary_guard.py}`。

### 2026-07-10 — 测试卫生：pytest 不再爬 gitignore 的 artifacts/

- **问题**：`pytest`（repo root）会收集 gitignore 的 `artifacts/candidate-review/**` 里的废弃
  candidate payload（各自带 `test_*.py`）→ 14 个假失败 + 与源码测试的 basename 碰撞。
- **修**：`pyproject.toml` 加 `[tool.pytest.ini_options] norecursedirs`（含 `artifacts` + 复原
  pytest 默认排除项）。纯 dev 配置，不影响 wheel/消费者，无版本 bump。
- **验证**：artifacts 假失败清零（15→8 failed）。剩余 8 个是**既有**包源布局假失败（hook/config
  测试在 `governance_core/tools/` 布局下 config 解析失败；经 autonomy 层 `tools/` 跑 21/21 全过）——
  排除 artifacts 移除了 basename 碰撞、把这批一直存在的布局假失败暴露出来，非本次引入。
- **遗留（未纳入本次）**：`pytest`-from-package-source 对 hook/config 测试的布局假失败是更深的
  "规范测试入口"问题（见 memory gc-test-suite-run-from-autonomy-layer），单列。
- **涉及**：`pyproject.toml`。
