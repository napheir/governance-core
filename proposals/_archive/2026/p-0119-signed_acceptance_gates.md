---
id: P-0119
agent: core
status: implemented
created: 2026-07-08
approved_at: 2026-07-08
started_at: 2026-07-08
implemented_in: 5fa71d5
implemented_at: 2026-07-08
owner: core
---

# Proposal P-0119: Add a signed Approval-Criteria form-gate + opt-in execution-class calibrated phase gates

## Trigger

trade-agent 递交 handoff `proposal-signed-acceptance-gates.md`：在 gc 现有两道 approve-time
form-gate（Current State / Design & Contract）之上，加**第三道签字门**（Signed Approval
Criteria，通用轻量）+ **execution-class 校准轨**（opt-in，重）。

维护者核对 §1 引用对齐 `main`（详见 Current State）：两门机制描述准确；唯一 cite 漂移是 Design
gate 定位——brief 写 `proposal_lib.py:486`（实为 scaffold 标题），真正谓词在 `:829`、强制在
`:998`。§5 的 todo↔proposal 桥经核实**本仓根本没有**（gc 无 todo 系统，grep 零命中），故纯为排除项。

治理适用性：改 `proposal_lib.py` / `contracts/`（新增 + 改 schema）/ `audit_proposals.py` /
`commands/proposal.md` —— 治理体系核心、多 phase、新契约，PROPOSAL_REQUIRED。

维护者已定 §7 命名（见 Design & Open Questions）：execution 标记 `execution: gates`、runner
入口 `/proposal run <id>`；载重的 check grammar（`cmd:`/`agent-rubric:`/`human-verify:`）原样保留。

## Current State (read, not assumed)

gc 已 ship **两道** approve-time form-gate，强制在 `proposal_lib.py::transition_proposal` 的
approve 路径、文档在 `commands/proposal.md`，各有 audit WARN 镜像（共享同一谓词，BLOCK 与 WARN
永不相左）：

- **Current State gate**（P-0108）：谓词 `current_state_adequacy`（`proposal_lib.py:629`），heading
  常量 `_CURRENT_STATE_HEADING`（`:582`）；approve 强制 `:984-993`，豁免 `--allow-empty-current-state`；
  audit Check 13 `_check_current_state_adequacy`（`audit_proposals.py:462`）共享谓词。
- **Design & Contract gate**（P-0124）：谓词 `design_contract_adequacy`（`proposal_lib.py:829`），
  仅对**复杂提案**触发（`_is_complex_proposal`，`:870`：≥2 非占位 `### Phase` 或 `## Scope` 触及
  `contracts/`）；approve 强制 `:998-1006`，豁免 `--allow-thin-spec`；audit Check 14
  （`audit_proposals.py:497`）共享 `design_contract_adequacy` + `_is_complex_proposal`。
- 两门均 **FORM-only**（`proposal_lib.py:577-578` / `:836-837`：形式在场即可，substance 是 approver 判断）。

gc **没有**的：
- `## Approval Criteria` 由 `_v2_scaffold` emit（`proposal_lib.py:546-554`），但 approve 路径
  （`:979-1006`）**只校验 Current State + Design，从不校验 Approval Criteria** —— 项可为
  "does X well" 空话，无可判定 done-condition。
- `## Open Questions` emit（`:515-522`），文档明说"轻量、不 gate"（`proposal.md:137-138`）。
- **无 `execution` frontmatter 字段**（`contracts/proposal_frontmatter_schema.md` §2/§4：
  id/agent/status/created + 状态条件字段，无 execution）；无 execution-class / runner / calibration 概念。
- **无 todo 系统**（§5 排除项已是现实）：`audit_proposals.py` / `proposal_lib.py` grep
  `todo`/`from_todo`/`_check_todo` **零命中** —— brief 所述 consumer 的 todo↔proposal 桥本仓不存在。

cite 校准：brief §1 把 Design gate 记作 `proposal_lib.py:486`，该行是 scaffold 的
`## Design & Contract` 标题；真正的门谓词在 `:829`、approve 强制在 `:998`。其余 file:line
（`:576-634`、`:577-578`、`proposal.md:104-107`、`:123-136`）对齐。

## Scope

在现有两门之上 additive 加第三门 + opt-in execution-class 轨。改动（包源 `governance_core/`）：

- `tools/proposal_lib.py`：
  - 加谓词 `approval_criteria_adequacy(body)`（签字门 FORM 校验：每个 Approval Criteria 项带一个
    check token）+ `gate_calibration_adequacy(body)`（execution-class 校准门）。
  - `transition_proposal` approve 路径追加这两门（在现有两门之后）；豁免 `--allow-unsigned-criteria`
    / `--allow-uncalibrated-gate`。
  - 加 `run(proposal_id)` 入口：仅对 approved/in-progress 的 execution-class 提案执行其 per-phase
    `gate:` cmd。
  - `_v2_scaffold`：Approval Criteria 项模板带 `check:` 语法示例。
- `commands/proposal.md`：文档化第三门 + execution-class + `/proposal run`；grammar。
- `contracts/proposal_gate_schema.md`（**新**）：check/gate/calibration grammar 契约。
- `contracts/proposal_frontmatter_schema.md`：加 optional `execution` 字段（§4.x），bump v1.2.0。
- `tools/audit_proposals.py`：加 WARN-only Check 15 `_check_gate_calibration_adequacy`（+ 签字门
  WARN），共享 BLOCK 谓词；cutover 之前的提案 grandfather。
- `pyproject.toml`：确认新契约 `.md` 在 package-data（`contracts/` glob 应已覆盖，核实）。
- 测试：签字门（项有/无 check）、校准门（phase 有/无 neg+golden）、豁免路径、`run` 拒未批、grandfather。

## Design & Contract

> Proportionate. Trivial change: one line "implementation self-evident; no interface
> or data-flow change." Otherwise fill all three sub-parts; use "N/A — <reason>" for
> any that genuinely doesn't apply — never leave a placeholder.

### Interfaces, I/O & Realization
- **`approval_criteria_adequacy(body) -> (bool, reason)`**（proposal_lib.py，新）— INPUT：proposal
  body；FORM 校验 `## Approval Criteria` 每个 `- [ ]` 项带一个 check token（`cmd:` / `agent-rubric:`
  / `human-verify:`）。OUTPUT：(ok, reason)。realizer：proposal_lib（approve BLOCK + audit 共享）。
  只查"有 check token"，不查它 pass（延续现有 form-only 立场）。
- **`gate_calibration_adequacy(body) -> (bool, reason)`**（proposal_lib.py，新）— INPUT：body +
  frontmatter `execution` 存在性；FORM 校验每个非占位 `### Phase` 带 `gate:` + `calibration:`
  （证据 `neg <fixture> → FAIL` + `golden <fixture> → PASS`）。realizer：proposal_lib（approve BLOCK
  for execution-class + audit Check 15 WARN 共享）。
- **`run(proposal_id)`**（proposal_lib.py CLI `run --id` + skill `/proposal run <id>`，新）— INPUT：
  approved/in-progress 的 execution-class 提案；对每个 phase 的 `gate:` 若为 `cmd:` 则执行、exit 0=pass；
  非 execution-class 或非 approved → 拒绝（exit 非 0）。approve **冻结** gate 集：改已批 gate = 需重批。
  realizer：proposal_lib CLI（同步执行，非 daemon）。
- **`transition_proposal` approve 路径**（proposal_lib.py:979-1006，改）— 在现有 Current State +
  Design 门之后追加：`approval_criteria_adequacy`（迁移期 WARN→BLOCK）+（若 `execution` 在）
  `gate_calibration_adequacy` BLOCK。豁免 `--allow-unsigned-criteria` / `--allow-uncalibrated-gate`。
- **`_v2_scaffold`**（proposal_lib.py:546，改）— Approval Criteria 项模板改为带 `check:` 示例。
- **`audit_proposals.py::_check_gate_calibration_adequacy`**（新，Check 15）— 对 in-flight 非终态
  execution-class 提案 WARN 未校准 gate；共享谓词；cutover 前 grandfather（镜像 Check 13/14）。

### Field Dictionary

| field | type | meaning | producer | consumer | constraints / allowed values |
|-------|------|---------|----------|----------|------------------------------|
| `execution` | str (runner id) | 标记 execution-class 提案 | 起草 agent | proposal_lib approve/run、audit Check 15 | 值=runner id，gc ship `gates`；缺省=普通提案；治理：`contracts/proposal_frontmatter_schema.md` §4 |
| `check`（Approval Criteria 项内） | token | 每个验收项的可判定检查 | 起草 agent | `approval_criteria_adequacy` | grammar `cmd:`/`agent-rubric:`/`human-verify:`；治理：**新** `contracts/proposal_gate_schema.md` |
| `gate` / `calibration`（Phase 内） | token/line | phase 机检门 + 校准证据 | 起草 agent | `gate_calibration_adequacy`、`run` | `calibration: neg <f>→FAIL; golden <f>→PASS`；治理：`contracts/proposal_gate_schema.md` |

### Flow
```
draft（scaffold 带 check grammar）
  └─approve→ form-gates: [1] Current State  [2] Design(复杂)  [3] Approval-Criteria signed
                          [4] 若 execution: gate calibration (neg→FAIL + golden→PASS)
       └─(execution-class) approve 冻结 gate 集
            └─/proposal run <id>→ 逐 phase 执行 gate: cmd → exit 0 = pass
  audit_proposals（in-flight 非终态）→ Check 13 / 14 / 15 WARN，各自共享 approve 的同一谓词
（todo↔proposal 桥：consumer-local business，本仓不引入 —— §5）
```

## Non-Goals

- 不动现有两门（Current State / Design & Contract）—— 严格 additive。
- 门保持 **FORM-only**（结构在 + 有可判定 check；不判 substance 对错）—— approver 的判断不变。
- **排除 consumer 的 todo↔proposal 桥**（§5）：`_check_todo_proposal_linkage` / `try-close
  --proposal` / `from_todo` 是 consumer 本地业务，**gc 无 todo 系统**（本仓 grep 已零命中），**不引入**。
- runner 是薄的 gate 执行器，**非**通用 workflow 引擎；不做 DAG / 并行 / 重试。
- approve **不自动** run gate；`run` 是独立显式步骤。
- 不改 A/B/C injection tier、不改 candidate / whichlayer / theme 等正交轴。

## Open Questions

> Known-undecided design points to resolve (or explicitly defer) BEFORE approval.
> Lightweight — NOT gated; the approver decides each. Write "None" rather than leaving
> the placeholder.

§7 命名（维护者已定，per user 指令）：
- **execution 标记** = `execution: gates`（frontmatter；值 = runner id；gc ship 单一 runner `gates`）。
- **runner 入口** = `/proposal run <id>` → `proposal_lib.py run --id P-NNNN`。
- **grammar**（载重、runner-agnostic，原样保留）= `cmd:` / `agent-rubric:` / `human-verify:`。

待裁定：
- **签字门引入方式** — leaning 迁移期 WARN（镜像 Current-State 门的 staged 引入），一个 rotation
  后翻 BLOCK；避免一上来 block 掉在途提案。**不决则按 transitional-WARN。**
- **单 agent hub 是否需要 execution-class runner** — leaning 需要：gc 自身跑 staged 迁移（P-0118
  即是），signed gate 把"validation: run X"空话变成可执行、校准过的门。它在 `execution` 字段背后
  opt-in，普通提案永不触发 → 零成本共存。**不决则 Phase 2 照做但 opt-in。**
- **`run` 执行 `cmd:` 的安全面** — 见 Guardrails；leaning 只跑 approved（冻结）gate + 记录，approve
  execution-class = 授权其 gate cmd；与 command-guard 交互在 Phase 2 定。

## Alternatives & Rationale

1. **签字项：check-token grammar vs 自由散文**：选 grammar。散文验收项无可判定信号（approver 勾
   空框）；一个 check token（cmd/rubric/human-verify）给出可复现 done-condition，且延续 gc 现有
   form-only 立场（查"有 check"非"check 过"）。
2. **execution-class：校准（neg+golden）vs 直接信任 gate**：选校准。"在坏输入上也 pass 的 check
   不是门"——neg-fixture 必 FAIL + golden 必 PASS 才证明门有判别力。
3. **复用现有 adequacy-gate 机制 vs 新子系统**：选复用。共享谓词让 approve BLOCK 与 audit WARN
   永不相左（镜像 Check 13/14），起草者一处学会全套。
4. **runner 读 proposal body vs 独立 run-spec**：选 body 单源。approve 冻结 body 内 gate 集 =
   "approved proposal → runnable gates" 单一真源，不与平行 run-spec 漂移。

## Guardrails

- `edit-write-guard`：改包源 `governance_core/**`（非宪法三文件）—— 允许。
- `constitutional-review`：新谓词守 Art.4 零 `.get(k,default)`（用成员测试，如现有 gate）、Art.7
  无 print / 无 Unicode 符号。
- **`run` 执行任意 `cmd:` 的安全红线**（重点）：`run` 只对 **approved（冻结）** 的 execution-class
  提案跑 `cmd:`，在 repo root 同步执行；approve execution-class 提案 = 显式授权其 gate cmd（文档写明）。
  改已批 gate 需重批（zero-tolerance drift）。与 `command-guard` 的交互须评估（gate cmd 是否过白名单）
  —— 列入 Phase 2 设计细化。
- 打包隔离（11.4）：新 `contracts/proposal_gate_schema.md` 须在 pyproject package-data（`contracts/`
  glob 应已覆盖，核实）。
- dogfood（11.3）：改完包源 `governance-core upgrade --project-root .` 重装。

## Phases

### Phase 0: 契约（docs-only，先行、低风险）

- Deliverables: 新 `contracts/proposal_gate_schema.md`（check/gate/calibration grammar）+ 在
  `contracts/proposal_frontmatter_schema.md` 加 optional `execution` 字段（§4.x），bump v1.2.0。
- Validation: `python tools/audit_proposals.py` 仍绿（尚未引用新字段）；契约自洽。
- Exit criteria: §7 命名与"签字门引入方式"Open Q 已决。

### Phase 1: 通用签字门（Signed Approval Criteria）

- Deliverables: `approval_criteria_adequacy(body)`；`_v2_scaffold` 的 Approval Criteria 项模板带
  `check:` 语法；approve 路径追加签字门（迁移期 **WARN**）；audit 签字 WARN。
- Validation: 单测（项有/无 check token）；BLOCK==WARN 共享谓词一致性；现有两门回归字节不变。
- Exit criteria: 签字门 WARN 生效、零回归；本提案自身 Approval Criteria 即通过该门。

### Phase 2: execution-class 校准轨 + runner（opt-in）

- Deliverables: `gate_calibration_adequacy(body)`；approve 对 `execution:` 提案的校准 BLOCK +
  豁免 `--allow-uncalibrated-gate`；`run(proposal_id)`（`/proposal run` + CLI）；audit Check 15
  `_check_gate_calibration_adequacy` + cutover grandfather。command-guard 交互定案。
- Validation: 单测（phase 有/无 neg+golden；execution 有/无；`run` 拒未批 + 拒非 execution-class；
  grandfather）；全套件；`/audit` 绿；dogfood upgrade。
- Exit criteria: execution-class 端到端；普通提案零触发。

### Phase 3: 签字门 WARN→BLOCK（rotation 后）

- Deliverables: 一个 rotation 后把签字门从 WARN 翻 BLOCK（或按 Open Q defer）。
- Validation: 迁移期在途提案不被误挡；翻 BLOCK 后缺 check 项被拦。
- Exit criteria: 签字门达 BLOCK，与 Current State/Design 门同级。

## Approval Criteria

> Concrete checks to tick before approval — derive from the spec above, don't restate
> goals. For a complex proposal include, as applicable:

- [ ] Every Field Dictionary entry names its governing `contracts/` file (or is N/A) — human-verify: each field row cites a contracts/ file
- [ ] Every user-facing capability / mutation has a named realizer — human-verify: nothing implied-but-unbuilt
- [ ] All Open Questions are resolved or explicitly deferred — human-verify: none left undecided
- [ ] 现有两门（Current State/Design）行为字节不变 — `human-verify:` 既有 gate 单测无改动全过
- [ ] 新签字/校准门单测全过 — `cmd: python -m pytest governance_core/tools/test_proposal_gates.py`
- [ ] `run` 拒未批 — `cmd: python tools/proposal_lib.py run --id <unapproved-fixture>`（退出非 0）
- [ ] 加 Check 15 后 audit 仍 0 failures — `cmd: python tools/audit_proposals.py`
- [ ] §5 todo 桥未被引入 — `cmd: grep -rL "从不引入" ...`（等价：`grep -r "from_todo\|_check_todo" governance_core/` 零命中）
- [ ] 新契约进 wheel — `human-verify:` `rm -r build; python -m build` 后 wheel 含 proposal_gate_schema.md

> 注：本 `## Approval Criteria` 各项已按本提案要引入的签字格式书写（每项一个
> `cmd:`/`agent-rubric:`/`human-verify:` check token）—— 即 dogfood Phase 1 的签字门。

## Validation Plan

- 单元：签字门（项有/无 check token）、校准门（phase 有/无 neg+golden、`execution` 有/无）、豁免
  `--allow-unsigned-criteria`/`--allow-uncalibrated-gate`、`run` 拒未批 + 拒非 execution-class、
  grandfather（cutover 前提案不 WARN）。共享谓词 BLOCK==WARN 一致性测试。
- 套件：从 repo 根跑 `tools/test_*.py`（pytest + script 两风格分跑，记忆 `gc-test-suite-two-styles`）；
  `python tools/audit_proposals.py` 0 failures。
- 现有两门回归：既有 Current State/Design 门测试字节不变。
- dogfood：本提案自身 `## Approval Criteria` 即用签字格式（Phase 1 门可自校）。
- 打包：`rm -r build; python -m build` 后核 wheel 含新契约（记忆 `wheel-package-data-nonpy`）。

## Rollback / Recovery

- 每 phase 独立 commit，可 `git revert`。
- 签字门迁移期为 WARN（Phase 1）→ 不阻断在途提案；Phase 3 才 BLOCK，可停在 WARN。
- execution-class 全在 `execution` 字段背后 opt-in：不加字段 = 零行为变化，可整体 defer Phase 2。
- Phase 0 契约 docs-only，可单独 revert。

## Risks

- **`run` 执行任意 cmd**（中高）：gate `cmd:` 是任意命令。缓解：只跑 approved（冻结）gate、
  approve = 显式授权、与 command-guard 交互在 Phase 2 定；文档红线。
- **签字门误伤在途提案**（中）：翻 BLOCK 会挡缺 check 的在途提案。缓解：迁移期 WARN + cutover
  grandfather（镜像 Check 13/14）。
- **谓词 BLOCK/WARN 漂移**（低）：两处逻辑分叉。缓解：共享单一谓词（现有模式）。
- **打包漏新契约**（低）：缓解：Phase 0 即核 package-data + wheel 验证。
- **过度工程 execution-class**（中）：单 agent hub 可能用不上 runner。缓解：opt-in 字段，普通提案
  零触发；先交付通用签字门（Phase 1），Phase 2 可视用量 defer。

## State Log

- 2026-07-08: draft created by core agent (P-0119)
- 2026-07-08: draft → pending (submit for review: signed acceptance-criteria gate + execution-class calibrated phase gates; brief §1 verified, §5 todo-bridge excluded, §7 naming decided (execution: gates, /proposal run))
- 2026-07-08: pending → approved (user approval: 批准 P-0119; full 4-phase scope (Phase 3 WARN->BLOCK deferred to a rotation per design))
- 2026-07-08: approved → in-progress
- 2026-07-08: in-progress → implemented (spans 3aa9a33 (Phase 0-1 signed-criteria gate) + 5fa71d5 (Phase 2 calibration gate + run). Reconcile benign: gate_schema/frontmatter_schema in the earlier commit; pyproject untouched (new contract covered by existing contracts/*.md package-data glob). Phase 3 (criteria WARN->BLOCK) deferred to a rotation. Non-goal honored: no todo bridge.)
