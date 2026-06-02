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

### 2026-06-02 — fix: curate_gate `_fetch_issue_body` Windows GBK 解码崩溃（NO_PROPOSAL）

- 触发:P-0090 例程 advise-only 实测后,本地对真实 issue 跑 `curate_gate.py` 核验闸门——
  #22(mechanism)正确返回 `eligible:false`,但 #24(feedback,body 含非 ASCII 花引号 0x94)
  在 `_fetch_issue_body` 崩:子进程 `text=True` 在 Windows 按 **GBK** 解码 gh 输出 →
  `UnicodeDecodeError` → body=None → `_extract_fence(None)` TypeError。远程 agent(Linux/UTF-8)
  不触发,但 Windows hub 本地跑、或任何非 ASCII body 候选都会崩。
- 修复(窄、清晰复现 → NO_PROPOSAL):`_fetch_issue_body` 改 `encoding="utf-8", errors="replace"`
  (gh 本就输出 UTF-8);`evaluate` 加 body 防御(非 str/空 → `eligible:false`,不崩)。
  测试 +1(case 14 空 body),13 → **14**。版本 0.21.2 → **0.21.3**。
- 涉及:`maintainer/curate_gate.py`、`governance_core/tools/test_curate_gate.py`、pyproject+__init__。
- 验证:#22/#24 现均 rc=0 干净 verdict(拒 mechanism / 拒 feedback);curate_gate 14/14、
  pytest 16、doctor exit 0。
- 未决(非本阶段):P-0090 远程例程 MANUAL run 显示**绿勾成功**但 GitHub 侧零写入(0 评论/标签)——
  疑 session 内 `gh` 未认证到 issues:write(clone 访问 ≠ issue 写权限),待看 run transcript 定位。

### 2026-06-02 — P-0090 P-0082 Phase 2：调度式 C-hybrid 策展例程 + 确定性 auto-promote gate + kill-switch

- 改动：建 P-0082 Phase 2(最重信任面——调度式例程可自主 commit+version-bump)。Phase 1(代码):
  - **`maintainer/curate_gate.py`** —— 唯一放行 auto-promote 的确定性闸门。对 auto-eligible issue:
    **从 body 重建 envelope**(net-new 候选 payload 内嵌 body)→ 全套检查(`validate_envelope` 全检 /
    origin 未撤销 / `scan_envelope` 无密钥 / 非 rejected / kind=skill / layer / net-new / 无 surface /
    skill-theme)→ **隔离 trial-apply(放 net-new 到 target + pytest + unlink)**。返回 GateResult。
    重建 **fail-closed**(drift/diff form 或含 ``` 的 payload → 不 eligible)。LLM 永不能 override False。
  - **`maintainer/auto_curate_enabled`** kill-switch,出厂 `{"enabled": false}`(advise-only)。
  - **`maintainer/curate_routine.md`** —— C-hybrid spec + 自包含例程 prompt。
  - 复用 `candidate_intake` 的 surface/net-new(Art.8);Art.4 配置直接索引(constitutional-review 拦过
    `.get(k,default)` → 改直索引)。版本 0.21.1 → 0.21.2(仅新 test 进 wheel)。
  - Phase 2(无 commit):`/schedule` RemoteTrigger 每日远程例程(见下次执行)。
- 涉及:maintainer/{curate_gate.py,auto_curate_enabled,curate_routine.md}、
  governance_core/tools/test_curate_gate.py(13 例)、pyproject+__init__。
- 关键决策/护栏:**四层纵深**(kill-switch 默认关 + gate 全过 + T0-only + push-creds);doc-gap
  (KINDS 无 doc → AUTO_KINDS={skill});trial-apply 跑在 live checkout(editable install 解析到此)
  但 net-new ⇒ 仅 unlink 清理无残留;**GitHub 远程通道未连**(本机 push≠云端 agent 凭据)→ 例程建后
  dormant,需 /web-setup + 开 kill-switch 两步才真跑。
- 测试:curate_gate 13/13(全 fail-closed 分支 + happy eligible + reconstruct round-trip)、
  **真实 trial_apply 冒烟绿且无残留**、pytest 16、intake 25、boundary 25、doctor exit 0、
  wheel 隔离干净(顶层仅 `governance_core*`,maintainer/ 未泄漏)。

### 2026-06-02 — P-0089 #23 walk-back：intake 只验内嵌 candidate.json + 撤消费者 envelope 发布

- 改动：与 user 讨论 + core 的 Phase 2 handoff 后,采纳 #23 架构决策(接近 C)——
  **消费者绝不该有 hub 写权限**,P-0088 的 option b(消费者 `uplink` 发布 envelope)
  从根上破坏 consumer/hub 信任分离,对非 owner 消费者更不可能。walk back:
  - **撤 option b**:`governance_core/candidates/uplink.py` 删 `publish_envelope` +
    调用 + 仅为它而加的 `import logging/shutil`/`log`(核实无他用)→ uplink 回到
    纯 issue 传输,除创建 issue 外不写 hub。删 `test_candidate_uplink_publish.py`。
  - **intake 改 candidate.json-only**:`maintainer/candidate_intake.py` 删
    `fetch_envelope`;`main()` 用 body 解析的 candidate.json 调**现成的**
    `envelope.validate_metadata`(schema/kind/layer/source_paths,无 payload-on-disk);
    secret 复扫 + digest 去重等**需真 payload 的检查移到 promote-time**(归 Phase 2
    curate_gate)。surface 命中 + net-new 是元数据级,保留。`compute_eligibility`
    简化为 `(metadata_valid, net_new, surface_hit, kind, layer)`。仍绝不 promote。
  - workflow yml 注释去掉"fetch published envelope";版本 0.21.0 → **0.21.1**(同日修正)。
- 涉及:uplink.py、candidate_intake.py、test_candidate_intake.py(重写 25 例)、
  删 test_candidate_uplink_publish.py、candidate-intake.yml、pyproject+__init__。
- 关键决策:`envelope.py` **已有** `validate_metadata`(dict)/`validate_envelope`(dir+payload)
  现成拆分 → #23 的"拆 validate_candidate"自动满足。`KINDS` 无 "doc"(T0_KINDS 含 doc
  但 doc 会先 fail metadata —— 既有不一致,留待后续,非本次范围)。净效果:外部+私有
  消费者都能用,彻底移除"消费者写 hub"。
- 测试:intake 25/25、pytest 16 passed、candidate 家族全绿、doctor exit 0、
  wheel 隔离干净(顶层仅 `governance_core*`,publish_envelope 已从 wheel 移除)。
- 后续:P-0082 Phase 2(调度式 curate_gate + kill-switch)另起 proposal——**最重信任面**
  (远程例程持久握 gc 写 creds 自主 commit),下轮审慎走。

### 2026-06-01 — P-0088 P-0082 Phase 1 gc 侧：候选 intake CI + uplink 发布 envelope（+ #21 de-drift）

- 改动：落地 trade-agent 交接的 P-0082 Phase 1（hub 侧确定性候选 intake，无 LLM、
  绝不 promote）。4 phase：
  - **三件套**：`maintainer/auto_promote_security_surface.json`（8 类 41 globs 拒绝集）、
    `maintainer/candidate_intake.py`（`issues.opened` 跑：区分 candidate/feedback、拉发布
    envelope 结构校验、secret 复扫**复用 uplink.scan_envelope**、查 rejected 去重、算
    确定性 T0-eligibility、打标签+ack）、`.github/workflows/candidate-intake.yml`。
    GC-TODO 全部用真实 gc API 收口；决策核心抽成纯函数 `compute_eligibility`。
  - **uplink 发布**：`governance_core/candidates/uplink.py` 加 `publish_envelope` ——
    issue 创建成功后**幂等+best-effort** 上传 envelope 为 `candidates` 预发布资产
    `<id>.tar.gz`（修掉 handoff 的 `.tgz`/`.tar.gz` 不一致）；发布失败不让 uplink 失败。
  - **labels**：建 5 个（feedback/valid/auto-eligible/needs-human/dup-of-rejected）。
  - **#21 de-drift**（独立 commit）：从 `agent-least-privilege.md`(1) +
    `resource-layer-hardening.md`(3) 的 `related:` 删失效 `proposals/` 引用，bump updated。
- 涉及：上述 3 新文件 + uplink.py + `governance_core/tools/test_candidate_intake.py`(23) +
  `test_candidate_uplink_publish.py`(4) + 版本 0.20.1 → **0.21.0** + 2 个 knowledge_governance 文档。
- 关键决策/caveat：**uplink 发布需对 hub repo 写权限**——纯 issue 传输本不需要；无写权限
  的消费者发布失败 → CI 拿不到 envelope → 标 needs-human（优雅降级，已在码注+小结标注）。
  intake **无 promote 路径** → 本阶段零提权面。`maintainer/`+`.github/` 不进 wheel（Art.11.4）。
- 测试：intake 23/23、uplink-publish 4/4、pytest 16 passed、session-boundary 25/25、
  candidate 家族全绿；`upgrade`+`doctor` exit 0；wheel 隔离干净（顶层仅 `governance_core*`，
  无 maintainer/.github 泄漏）。Check 9 只查 frontmatter LINK_FIELDS（读码确认）。

### 2026-06-01 — P-0087 收编 issue #20：boundary-guard read-only 快速放行漏洞

- 改动：策展通用层候选 **issue #20**（mechanism / drift, trade-agent）—— 修复
  `session-boundary-guard.py` 的真实安全洞。`is_read_only_bash()` 用 start-anchored
  匹配，任何以只读动词（cat/grep/tail…）开头的命令在路径提取 + 关键路径检查**之前**
  就被当只读快速放行 → `cat foo > /越界` 甚至 `> ~/.ssh/...` 整个绕过守卫。实测当前
  包源 guard 对 `cat <in> > <.ssh>` 返回 exit 0（放行），漏洞 live。
- 修复（外科手术式，全文 diff 核实仅此改动）：`is_read_only_bash` 顶部加 redirect
  短路 —— 命令含文件写重定向 `>`/`>>`（负字符类 `[^\s&|;<>]` 排除 `2>&1`/`>&2`
  fd-dup）时返回 `False`，不再快速放行。测试 +4 回归用例（22 cat>outside 拦 /
  23 cat>.ssh 关键拦 / 24 cat>inside 放行 / 25 `2>&1` 放行），21 → **25**。
- 涉及：`governance_core/tools/session-boundary-guard.py`、
  `governance_core/tools/test_session_boundary_guard.py`、
  `pyproject.toml` + `governance_core/__init__.py`（0.20.0 → **0.20.1**，安全 patch）、
  `maintainer/consumer_registry.json`（记 `promoted`）、`STATE.md`、
  `shared_state/proposals/core/p-0087-*.md`。
- 关键决策：mechanism 类候选手工放置包源（Art.11.2 只改 `governance_core/`）；
  机制与示例已通用（`/outside`、`~/.ssh`）→ 无需 de-trade-ify；dogfood —— 本仓库
  自身 guard 同样带洞，`upgrade` 后修复。
- 测试：包源 guard 测试 **25/25**；repo-root `upgrade` 后 **25/25**；全套
  `pytest tools/` **16 passed**；`doctor` exit 0；wheel 隔离（顶层仅
  `governance_core*`、无 `maintainer/` 泄漏、修复在 wheel 副本中）。

### 2026-05-30 — P-0086 de-trade 既有 profile 示例残留（P-0078 cluster 清理）

- 改动：承 P-0085 策展时 grep 闸门发现的**既有** trade 域残留（P-0078 cluster
  promote HTML profile 时未彻底 de-trade），按 user 指令"也一并处理"清干净。改
  `governance_core/knowledge_governance/knowledge-html-profile.md`，profile
  v1.1.0 → **v1.1.1**（Patch：仅示例措辞、无契约变更）。
- 清理 6 处（完整 grep 清单）：§2.2.1 caption（`trade pin pipeline_current.html`）、
  §3.3.1 出处归因（`trade 2026-05-26`）、§3.3.1 strict-mode Mermaid 例
  （`signal_reader/dedup` + `artifacts/trade/{ts}` → gc `collect/dedup` +
  `artifacts/audit/{ts}`）、§4.1 autogen 整例（`s50-tier-metrics` +
  `artifacts/strangle50/...` + Tier/Precision 表 → `governance-audit-summary` +
  proposals/hooks/clauses 审计表）、§7 pilot 行 + Status footer
  （`s50_current.html`/rules → 中性消费者域）。语法/契约教训逐字保留。
- 涉及：`governance_core/knowledge_governance/knowledge-html-profile.md`、
  `pyproject.toml` + `governance_core/__init__.py`（0.19.0 → 0.20.0）、`STATE.md`、
  `shared_state/proposals/core/p-0086-*.md`。
- 关键决策：机制/契约/结构零改 → **audit 工具不 bump**；保留 §7 `harness_defense.html`
  （owner=core，gc 合法）+ §9 v1.1.0 的 "trade-agent" **候选来源归因**（准确 provenance、
  非域示例）；版本历史条目**不复述** trade token（否则自触 grep 闸门）。
- 测试：de-trade grep 闸门**清洁**（唯一命中"折叠面板"是通用 `<details>` 术语，
  非 trade）；全套 `tools/test_*.py` **21/21**；`audit_html_profile.py` exit 0（工具未改）；
  dogfood `upgrade` + `doctor` exit 0。

### 2026-05-29 — P-0085 promote #18: knowledge-html-profile §2.5 业务优先节

- 改动：策展通用层候选 **issue #18**（mechanism / drift, trade-agent）—— 把 net-new
  规范节 **§2.5「信息构建原则（业务优先）」**（~100 行）promote 进
  `governance_core/knowledge_governance/knowledge-html-profile.md`，profile
  v1.0.0 → 1.1.0。§2.5 规定 HTML 的**叙事语域**（§2.1–§2.4 管结构）：主叙事用业务
  语言、机器细节下沉 `<details>`、表格列优先业务语义、whole-document 应用范围。
- baseline drift（候选 baseline `432b40…` ≠ 当前源 `1ddbf8…`）→ **不信旧行号**，
  按上下文锚点手工应用（§2.4 末插 §2.5；§2.1 summary / §6 行 / §8 / §9 同步改）。
- **de-trade-ify**（skill step 3）：机制文字逐字保留，仅把消费者域示例换成 gc 自身域 ——
  §2.5.3 正/反例 trade 期权 pipeline（`option_selector` / strangle）→ **gc upgrade/install
  pipeline**（原子覆盖安装 / 改动文件转存 candidate-outbox）；§2.5.6 反模式去掉 `P-0081`
  与 trade section 名（signal_reader / scheduler / 面板）；provenance 改记 P-0085。
- **audit 工具与机器契约不动**：§2.5 是 voice/framing，机器无法判定 → 明确为
  human-review 层（§2.5.5 + §8）；`audit_html_profile.py` 只校验结构、**不随 profile
  v1.1.0 bump**。
- 涉及：`governance_core/knowledge_governance/knowledge-html-profile.md`、
  `pyproject.toml` + `governance_core/__init__.py`（0.18.0 → 0.19.0）、`STATE.md`、
  `shared_state/proposals/core/p-0085-*.md`。
- 关键决策：改包源（Art.11.2），不碰自治副本；独立 proposal/commit（与 #19 分开）。
  **发现既有 de-trade 缺口**：profile §3.3.1（`signal_reader/dedup` Mermaid 例）+ §4.1
  （`artifacts/strangle50/...` autogen 例）是 P-0078 cluster 遗留的 trade 残留，**不在
  P-0085 scope**（Non-Goals 不动 §3/§4）—— 已向 user 提示为后续候选。
- 测试：全套 `tools/test_*.py` **21/21**；`audit_html_profile.py` exit 0（无 HTML 文件、
  工具未改）；de-trade grep 闸门确认 §2.5（168–227 行）零 trade token；dogfood `upgrade`
  → autonomy profile 刷新到 v1.1.0；`governance-core doctor` exit 0。

### 2026-05-29 — P-0084 promote #19: narrow classify-paths governance glob

- 改动：策展通用层候选 **issue #19**（mechanism, trade-agent）—— bug fix。
  `governance_core/tools/proposal-classify-paths.json` v1.0.0 → 1.1.0：governance
  类的 catch-all `.governance/**/*` 收窄为权威子路径
  `.governance/clauses/**/* + core_keywords.json + config.json`。
- 根因：catch-all 命中**瞬态 gitignored** `.governance/candidate-outbox/`
  （collect.py `OUTBOX_REL`），导致 `/submit-candidate` / `/upgrade` drift-uplink
  每次写 envelope 都被 classify-fast PreToolUse hook 误判 `PROPOSAL_REQUIRED`
  硬阻。**gc 自身（self-host 消费者）现也中招** —— 强 dogfood 信号。matcher
  `_classify_match.py` 无 negation operator，故用显式枚举而非 exclude。同时
  剔除派生物 `.governance/installed_files.json`。
- 涉及：`governance_core/tools/proposal-classify-paths.json`、
  `governance_core/tools/test_proposal_classify_paths.py`（加 P-0084 回归断言 +
  docstring 17→19 globs）、`pyproject.toml` + `governance_core/__init__.py`
  （0.17.0 → 0.18.0）、`shared_state/proposals/core/p-0084-*.md`。
- 关键决策：改**包源**（Art.11.2），不碰自治副本；走独立 proposal（与 #18 分开，
  各自 commit/rollback）；保留所有真实治理源覆盖（实测前后对照：candidate-outbox
  / installed_files True→False，clauses/core_keywords/config/CLAUDE.md 仍 True）。
- 测试：`test_proposal_classify_paths.py`（19 globs、回归断言）+
  `test_proposal_classify.py` 9/9 + `test_proposal_classify_fast_hook.py` 7/7
  （自治层）全绿；dogfood `upgrade` → autonomy 副本刷新到 v1.1.0；
  `governance-core doctor` exit 0。

### 2026-05-29 — P-0083 add /curate-candidate command skill

- 改动：新增 `governance_core/commands/curate-candidate.md` —— hub 侧候选策展的
  编排 skill（`/submit-candidate` 的对偶），从本会话 6 轮策展提炼。**指针式
  checklist**（Art.99：只指向权威工具/文档、不复述）：review → classify（通用 vs
  域特定 / net-new / 完整性）→ verify（drift sha 比对 + `git apply --recount` /
  `--ignore-cr-at-eol` 去 CRLF 噪声;去 trade 化）→ 改包源（Art.11.2）→ wire（hook
  manifest + runtime-import-discipline;新数据文件进 package-data）→ validate（bump
  + 测试 + dogfood + doctor + wheel 隔离）→ record（promote/reject）→ `/proposal`
  + 关 issue。版本 0.16.0 → 0.17.0。
- 涉及：`governance_core/commands/curate-candidate.md`（新）、`governance_core/__init__.py`
  + `pyproject.toml`（0.17.0）、`STATE.md` / `STATE_ARCHIVE.md`（rotate）、
  `shared_state/proposals/core/p-0083-*.md`。
- 关键决策：**packaged command skill**（不是 gitignored `.claude/skills/learned/`
  —— 那会被 upgrade 清掉,自托管 hub 的正确归宿是包源 command）；指针式（Art.99
  单一源、零复述 → 不漂移）；把 6 轮踩过的坑编进去（缺件 / CRLF / 去 trade 化 /
  package-data / 自托管 nuance）。本会话 should-extract 一直 YES,此 skill 是其落点。
- 测试：全套 `tools/test_*.py` **21/21**；dogfood `upgrade` → 已装 + registry 发现
  （available-skills 列出 `/curate-candidate`）；`governance-core doctor` exit 0；
  wheel 0.17.0 build OK（top-level 仅 `governance_core` + dist-info、skill 在内、
  `maintainer/` 不泄漏）。

### 2026-05-27 — P-0077 uplink drift diff + --body-file (issue #15)

- 改动：`candidates/uplink.py` 大改 —— `build_issue` 加 drift 分支：
  当 envelope 有 `drift_target` + `baseline_sha256` 且
  `installer._pkg_source_path` 解析得到 baseline 时，body 渲染
  unified diff（against baseline）+ `payload_form: diff` +
  `payload_sha256:` 行（按 ledger._hash_payload 同算法）；无法解析
  baseline 时 fallback legacy full-payload。net-new envelope 路径不
  变（P-0076 ledger rehash 仍依赖 full payload fence）。`gh_command`
  argv 从 `--body body` 改 `--body-file <tempfile>`：用
  `NamedTemporaryFile(delete=False)` 写 body，pass file path 到 gh，
  finally `unlink(missing_ok=True)`。这绕过 Windows
  CreateProcessW ~32K UNICODE_STRING cmdline 限制（Python 把这个
  surface 为 FileNotFoundError，旧版本误归类为"gh missing"）。
  `UplinkError` 在 stderr 含 "label not found" pattern 时附 hint
  打印 `gh label create candidate / kind/skill / kind/hook /
  kind/mechanism` 4 行。`candidates/ledger.py`
  `parse_payload_from_issue_body` 加 drift body 短路：识别
  `payload_form: diff` 后从 body 读 `payload_sha256:` 返回，跳过
  rehash；`discover_uplinked_from_hub` drift body 直接用
  meta["payload_sha256"]。`maintainer/reject_candidate.py` 同样
  drift 路径不 rehash + 不走 pre-0.8.0 heuristic。版本 0.8.0 →
  0.9.0。docs/core-manual.md §11 加 P-0077 drift-as-diff 子节 + hub
  labels setup 子节。
- 涉及：`governance_core/candidates/uplink.py`、
  `governance_core/candidates/ledger.py`、
  `maintainer/reject_candidate.py`、
  `governance_core/tools/test_uplink_drift_diff.py`（新，20 用例）、
  `governance_core/__init__.py` + `pyproject.toml`（0.9.0）、
  `docs/core-manual.md`、`STATE.md`、
  `shared_state/proposals/core/p-0077-*.md`。
- 关键决策：`payload_form: diff` 显式 metadata（不靠"猜身体形状"）；
  drift fallback 到 legacy full-payload 让 uplink 永不因 baseline
  miss 阻塞；P-0076 net-new rehash 路径完全保留（向后兼容）；
  `--body-file` Linux/macOS 也用（统一行为、no-op for them）；
  Windows newline 提醒在测试用 `write_bytes` 控制 bytes。
- 测试：`test_uplink_drift_diff` 20/20（build_issue 9 + parser 5 +
  discover_recovery 3 + gh_command 3）；全套回归 revocation 24 +
  renewal 13 + candidate-attribution 9 + candidate-reminder 7 +
  update-reminder 9 + auth-guard 9 + auth-codec 11 + upgrade-dry-run
  14 + candidate-recovery 14 + rejected-registry 21 +
  uplink-drift-diff 20 = 151/151 全绿。wheel 0.9.0 含 uplink/ledger/
  test_uplink_drift_diff；dogfood upgrade OK；doctor exit 0、hooks
  19/registered 18。

### 2026-05-26 — P-0076 Phase 2 reject feedback registry

- 改动：新建包源 `candidates/rejected_registry.json`（schema 1，含两条
  backfill 条目对应 #4/#6 + #5/#7、`block_by_name: true` 标记 pre-0.8.0
  sha 不可还原场景）。新建包源模块 `candidates/rejected.py`
  （`load_rejected_registry` / `is_rejected` / `should_block` /
  `format_advisory` 四个 API）。`cmd_sweep` 接 `is_rejected` 检查：
  exact → 阻断 + stdout 打印结构化 SKIPPED advisory；name +
  `block_by_name: true` → 阻断；name + `block_by_name: false` → stderr
  warn + 仍 uplink（允许 hub 重评 rewrite）。`candidate-reminder.py`
  hook 扩展：SessionStart 时 cross-check pending 与 registry，被拒
  skill 在 banner 出 WARNING 行。新建 hub 工具
  `maintainer/reject_candidate.py`（`--issue N --reason X --advice Y
  [--also-close] [--dry-run]`），抓 issue body、复用 Phase 1 共享 parser
  解析 payload、自动判 pre-0.8.0 rstrip 场景 → 写 registry +（可选）
  关闭 issue 加 advisory comment。`pyproject.toml` package-data 加
  `candidates/*.json` 让 registry 进 wheel。版本 0.7.0 → 0.8.0（按
  P-0074/P-0075 模式一次性 bump 跨两 phase）。
- 涉及：`governance_core/candidates/rejected.py`（新）+
  `rejected_registry.json`（新）、`maintainer/reject_candidate.py`（新）、
  `governance_core/tools/test_rejected_registry.py`（新，21 用例）、
  `governance_core/tools/candidate.py`（接 `is_rejected`）、
  `governance_core/hooks/candidate-reminder.py`（SessionStart 增 WARNING）、
  `governance_core/__init__.py` + `pyproject.toml`（0.8.0、package-data
  加 `candidates/*.json`）、`docs/core-manual.md`（§11 加 self-heal +
  reject feedback 两段、新 §13 maintainer reject workflow）、`STATE.md`、
  `shared_state/proposals/core/p-0076-*.md`。
- 关键决策：registry schema 加 `block_by_name: bool` 字段（默认 false、
  pre-0.8.0 backfill 设 true）让 maintainer 显式覆盖 name match 的"宽松"
  默认；不引入"unreject"工作流（rewrite 用新名字、强制语义表态）；不自动
  修改 consumer skill frontmatter（守 autonomy carve-out 不变量）；wheel
  shipped registry，不走另立签名 feed（advisory 非 security critical、
  wheel 签名已证来源）。
- 测试：`test_rejected_registry` 21/21（is_rejected 6 + should_block 4 +
  format_advisory 5 + malformed registry 2 + shipped registry smoke 4）；
  全套回归 revocation 24 + renewal 13 + candidate-attribution 9 +
  candidate-reminder 7 + update-reminder 9 + auth-guard 9 + auth-codec 11
  + upgrade-dry-run 14 + candidate-recovery 14 + rejected-registry 21 =
  131/131 全绿。wheel 0.8.0 build OK（`rejected.py` /
  `rejected_registry.json` 进 wheel、`maintainer/` 不漏）。dogfood
  `governance-core upgrade --project-root .` OK，hooks 19/18 registered、
  doctor exit 0。`reject_candidate.py --dry-run --issue 4` 演练成功，
  自动识别 pre-0.8.0、设 block_by_name=true、sha=null。P-0076 两 phase
  全部实现完成。

### 2026-05-26 — P-0076 Phase 1 sweep ledger 自愈

- 改动：`governance_core/candidates/ledger.py` 加
  `parse_payload_from_issue_body(body) -> (meta, {name: bytes})`（共享
  parser，Phase 2 maintainer 工具也用）+ `discover_uplinked_from_hub(
  origin, repo)`（`gh issue list --state all --search "[candidate]
  (from <origin>)"`、逐 issue 解析 fenced block、rehash、返回
  `[{digest, candidate_id, issue_url}]`、`gh`/网络/解析失败均 best-effort
  退回空）。`uplink.py` 修 payload 段 **不 rstrip**（保留原文 bytes、让
  hash round-trip 正确）。`candidate.py` `cmd_sweep` 在 collect 之后、
  pending 选择之前接 recovery：ledger 空 + outbox 非空 + `gh` 可用即调，
  把 recovery 结果写入 `_uplinked.json`。
- 涉及：`governance_core/candidates/ledger.py`、
  `governance_core/candidates/uplink.py`、
  `governance_core/tools/candidate.py`、
  `governance_core/tools/test_candidate_recovery.py`（新，14 用例）、
  `STATE.md`、`shared_state/proposals/core/p-0076-*.md`。
- 关键决策：保持 `payload_digest` 行为不变（按 `read_bytes()` 哈希）、
  改 `build_issue` 让 issue body 不 rstrip → round-trip 一致；recovery
  全程 fail-safe（FileNotFoundError / CalledProcessError /
  JSONDecodeError 均 logger.info 后返空）；recovery 只在 ledger 真的
  empty 时触发，正常 consumer 不付网络代价。
- 修环境：发现 `pip show` 显示 0.7.0 但 Editable project location 丢失
  ([[editable-install-clobber]] 信号)，`pip install -e .` 重装恢复。
- 测试：`test_candidate_recovery` 14/14（parser 5 + discover 8 +
  end-to-end round-trip 1）；回归 revocation 24 + renewal 13 +
  candidate-attribution 9 + candidate-reminder 7 + update-reminder 9 +
  auth-guard 9 + auth-codec 11 + upgrade-dry-run 14 = 96/96 全绿。
  无版本 bump（按提案 Phase 1+2 单次 bump pattern，待 Phase 2 一起
  0.7.0 → 0.8.0）。
