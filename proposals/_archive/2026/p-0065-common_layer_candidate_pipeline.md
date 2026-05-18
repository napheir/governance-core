---
id: P-0065
agent: core
status: implemented
created: 2026-05-15
approved_at: 2026-05-18
started_at: 2026-05-18
implemented_in: f5b23f7
implemented_at: 2026-05-18
owner: core
---

# Proposal P-0065: GC 统一治理收口 hub —— 授权消费者 + 候选上行 + curated 提升

## Trigger

User architectural discussion（2026-05-15 起，2026-05-18 两轮重写）。

P-0063 让 agent-core 成为 governance-core 真消费者，但暴露：公共层 vs 业务层
无法机械区分、公共层改进回流破坏性（`upgrade` 静默覆盖本地公共层改动 = 改进
丢失）。最初的 P-0065 草案给出"检测/捕获"的**本地、离线**候选管道（4 phase）。

2026-05-18 user 对目标做了实质扩张并细化，本 proposal 据此**完全重写**：

1. **GC 是统一收口方**：所有新的 governance 公共改造（公共 skill + hook +
   其他机制）都收口到 GC，由 GC 决策是否叠加为新公共能力、再下发。
2. **任何**使用 governance 的项目方，产生公共能力候选（技能提取/精炼机制使
   候选很容易出现），都能上报给 GC；既要**自动收集**，也要一个让项目 owner
   **主动提交**候选的 skill。
3. 候选要离开消费者项目、传到 GC —— 因此必须有**使用者同意（consent）**。
4. **授权机制**：由 GC 生产授权码；其他项目 owner 下载包后，**只有填入授权码
   才可使用全部公共层能力**。
5. （细化）授权填写完成后，install 必填"是否同意自动上传候选信封"；**当前
   版本要求必须同意**，否则不可应用该公共层。

这把最初草案显式推迟的"多消费者 + 跨网络"从 follow-up 提进核心：候选不再
只是本地 `cp`，而是跨项目、（可能）跨机器上行到 GC。授权码同时充当消费者
**身份**，把点 2/3/4/5 串成一条线 —— 候选信封的 `origin` 就是授权码里的
consumer id。

Why PROPOSAL_REQUIRED：改 governance-core 治理基础设施（installer / CLI /
extract-skill / lesson-classification）+ 多 phase + 跨 repo 回流路径 +
security-sensitive（授权校验 + 候选上行进**公开** GitHub repo + 触及
scope/security hook 的回流）+ 重定义公共层维护模型与分发授权模型。

## Scope

### In-Scope

整体模型：`governance-core install` 用**离线签名授权码**验证并确立消费者身份、
并在同一步**强制收集上传同意** → 授权 + 同意双门通过后才 materialize 自治层
（= 公共层能力）→ 授权消费者把能力候选（skill / hook / mechanism 三类，统一
信封）经 `gh` 上行到 GC → GC 侧 **curate** 决策提升 → 并入包源 → 发版下发。
manifest + baseline-hash 漂移检测是"检测"的一半，作为其中一个 phase 保留。

1. **授权 + 同意双门（点 4/5）**：Ed25519 离线签名授权码。GC 持签名私钥
   （离线、绝不进 git/包），公钥随包分发。`install` 要求授权码、离线验签、提取
   consumer id；紧接着**强制**询问候选上传同意。两门任一不过 → install 中止 →
   自治层不 materialize → 公共层能力物理不存在。`upgrade` / `doctor` 复验。
   详见下文"机制详解"。license 从 MIT 改为 source-available。
2. **manifest + baseline hash（原 Phase 1）**：`install/upgrade` 写
   `.governance/installed_files.json`（逐 install-managed 文件 path + sha256 +
   source_version + category）。既答"X 属公共还是业务"，又作漂移检测器 +
   附查询工具。
3. **候选统一信封 + tagging（点 2）**：candidate envelope —— 目录式信封承载
   skill / hook / mechanism 三类候选（统一 `kind` 字段 + 元数据）。
   `/extract-skill` 给 learned skill 打 `layer` tag；`lesson-classification`
   增 generic-vs-project 轴。
4. **候选收集 + 主动提交 + uplink（点 2/3）**：三来源 ——（a）净新增
   `layer: candidate-common` learned skill；（b）非破坏 `upgrade` 检出的
   install-managed 文件漂移；（c）`/submit-candidate` skill 让 owner 主动打包
   候选。经 `gh`（issue/PR，形态 Phase 0 锁）上行到 GC。**uplink 前强制
   sensitive-data 扫描**（候选进公开 repo），逐条阻断式。
5. **GC 侧 curation 闭环（点 1）**：审阅工具/skill 扫 incoming 候选 → 逐条
   curate（提升 / 退回带理由 / 转有记录 override）→ 提升进 `governance_core/`
   包源 → 发版。consumer registry 记录已签发授权码与各消费者报过的候选。

### Out-of-Scope (Non-Goals)

- **在线/phone-home 授权校验**：本 proposal 只做离线签名校验；在线吊销/续期
  另议。
- **硬性 DRM**：包是 source-available Python，授权校验可被改源绕过 —— 授权码
  是**威慑 + 身份标识 + 使用条款约束**，不声称不可破解。
- **auto-promote 候选**：judgment 必须 curated（人/agent 审阅）；只有收集 +
  呈现 + 上行自动化。auto-promote 会让项目专属物污染共享层、重演分叉。
- **GC 主动巡检远程消费者 repo**：上行是消费者 push（`gh` issue/PR），不是 GC
  pull/扫描他人 repo。
- **改宪法 total.md / CLAUDE.md**：本 proposal 是机制层。若要把"公共层变更必经
  候选评审"或"使用 GC 须授权 + 强制上传同意"上升为宪法条款，另走
  `/iterate-constitution`。
- **不**阻止项目本地改 install-managed 文件（拦不住，也不应拦）—— 只检测 +
  捕获 + 上行。
- **不**改 business 层文件的任何治理。

## Non-Goals

参见 Scope.Out-of-Scope。本节保留位仅供归档审查工具识别。

## 机制详解：授权码 + 强制同意门

### 授权码：生产 → 分发 → 消费 → 复验

**生产（GC maintainer 侧）**
- maintainer 用 `maintainer/issue_auth_code.py`，输入 consumer 标识（项目名/
  组织名）
- 工具构造 payload `{consumer_id, issued, expiry?}`，用 Ed25519 **私钥**签名
- 输出一段可复制的授权码字符串（payload + signature 的 base32/base64 编码）
- 私钥 maintainer 离线持有；签发工具 committed 于 repo 级 `maintainer/`，
  **排除出 pip 包**

**分发（out-of-band）**
- `pip install governance-core` 本身公开免费 —— 但**未填授权码的包是惰性的**
  （`install` 会中止，自治层不 materialize）
- maintainer 通过带外渠道把授权码交给项目 owner（渠道不在本提案规定范围）

**消费（项目 owner 侧）**
- owner 跑 `governance-core install --project-root . --auth-code <CODE>`
  （或省略 flag 由 CLI 交互提示填入；CI 等非交互场景用 flag）
- installer 用**包内随附的公钥**（`governance_core/auth/pubkey.*`）离线验签
- 验签通过 → payload 的 `consumer_id` 写入 `.governance/config.json`；原始码
  一并存储，供 `upgrade` / `doctor` 复验
- 验签失败 / 缺失 → install **中止**，自治层不被 materialize

**复验**
- `upgrade` / `doctor` 用包内公钥复验已存授权码；（若启用 expiry）过期 →
  `doctor` 标红、`upgrade` 拒绝刷新

**两层 gate（materialize 门 + 运行时强制）**

授权对"全部公共层能力"的 gate 分两层（2026-05-18 user 修订：原设计只做
materialize 门、显式声明"无需运行时校验"—— user 指出已装好的项目事后授权失效
仍照常运行，要求补运行时强制）：

- **materialize 门**：公共层（hooks / skills / commands / clauses / tools）
  抵达项目的唯一路径是 `install` / `upgrade` 写自治层。gate 住这两个动作 →
  无有效码 = 自治层从未 materialize = 能力**物理不存在**。
- **运行时强制**：已 materialize 的项目若事后授权失效（码被篡改 / maintainer
  轮换密钥致旧码失配 / 码被删），自治层文件仍在磁盘上、照常运行 —— 故再加
  `auth-guard` PreToolUse hook（matcher `*`）：每次工具调用前复验存储的授权码，
  无效即**阻断该次调用**。全部工具调用被阻断 = agent 在该项目里寸步难行 =
  "全能力失效"（hooks 直接 gate；proposal / wrap-up / skill 因工具被冻而
  **传递性失效**）。验签结果按 (repo, code, pubkey) 缓存，避免每次工具调用都
  跑 Ed25519 验签。
- **强度 = 硬冻结**：不取"软失效"（只让 proposal 等拒跑、保留 safety hook）——
  那样项目仍可用，且关掉 safety hook 是安全倒退。
- **非 DRM**：运行时强制同样可被改源删除 —— 它让"无效→冻结"成为预期行为、
  抬高门槛，不声称不可破解（与 Out-of-Scope 一致）。
- **恢复**：冻结只作用于 agent 的工具调用；人始终能在自己终端跑
  `governance-core install --auth-code <有效码>` 解冻。

> 注：授权码是**消费者身份标识**（类比 license key），不是密码级机密。
> 对自托管 gc，`.governance/config.json` 是 committed 的 —— 码随之入库可接受
> （泄露后果只是他人可冒充该 consumer id，低危；私钥才是真机密）。

### 强制同意门：install 时收集

- 授权验签通过后，install **接着**询问：「是否同意自动上传候选信封（改进后的
  skill / hook / 机制）到 GC 的**公开** repo？」
- **当前版本：必须同意** —— 答「否」→ install 中止，并明示"本版本下，同意
  上传候选是使用公共层的前置条件"
- 非交互场景用 `--accept-candidate-uplink` flag 表示同意；未带且非交互 → 中止
- 同意 → `.governance/config.json` 记 `candidate_uplink_consent: true` +
  时间戳 + `consent_terms_version`
- 数据模型**向前兼容**：未来版本若放宽为 opt-in，只改 install 门的严格度
  （允许写 `false`），schema 不变、下游无需迁移
- 因候选上行进**公开** repo：每条 envelope 上行前的 `sensitive-data` 扫描是
  强制、逐条阻断式（命中阻断该条，不影响其他候选）

## Guardrails

| Guard | 适用阶段 | 关注点 |
|-------|---------|--------|
| `edit-write-guard` | Phase 1/3 | 改 `/extract-skill`、`lesson-classification`、installer 等 install-managed 资产须改 `governance_core/` 包源、不碰自治层副本（宪法第十一条）；本 proposal 自身吃自己的狗粮 |
| `sensitive-data-guard` | Phase 4 | **强化关注点**：候选上行到**公开** GitHub repo —— 漂移 diff / 主动候选若夹带 secret 即公开泄露。uplink 前强制脱敏扫描、逐条阻断；同意文案须明示"候选进公开 repo" |
| `command-guard` | Phase 1/4/5 | `gh`、`git push`、`governance-core` CLI 调用前明示 |
| 签名私钥保密 | Phase 0/1 | 授权签名私钥 maintainer 离线持有，**绝不**进 git、绝不进 pip 包；签发工具放 repo 级 `maintainer/`，排除出包 |
| 新增依赖审查 | Phase 0 | Ed25519 签名/验签需选签名库 —— 引入 crypto 依赖须按 Art.7.3 讨论；备选纯 Python 内联实现以零新增运行时依赖 |
| `boundary-guard` | 全期 | 本 proposal 在 governance-core 自身 session（self-hosted，P-0066）执行 —— 改包源 in-boundary，无需跨 boundary subprocess |

## Phases

### Phase 0: 设计锁定 —— 授权 / 信封 / license spec

- Deliverables:
  - **授权码 spec**：签名算法（默认 Ed25519）、签名 payload schema
    （`consumer_id` / `issued` / 可选 `expiry`）、授权码编码（base32/base64）、
    公钥随包分发路径（`governance_core/auth/`）、私钥与签发工具布局
    （maintainer 离线 + repo 级 `maintainer/`，排除出 pip 包）
  - **签名库决策**：引入 crypto 依赖（`cryptography` / `PyNaCl`）vs 纯 Python
    内联 Ed25519 实现（零新增运行时依赖）—— 按 Art.7.3 讨论定案
  - **license 选型**：MIT → source-available 的具体许可（候选：自定义"授权
    使用"条款 / PolyForm / BSL —— 经 user 定；注：已发布的 0.1.2–0.1.6 维持
    MIT，变更只对后续版本生效）
  - **`installed_files.json` schema**：`path` / `baseline_sha256` /
    `source_version` / `category`
  - **candidate envelope schema**：目录式信封 = `candidate.json` 元数据
    （`id` / `kind`: skill|hook|mechanism / `origin`（consumer id）/ `created`
    / `layer` / `title` / `rationale` / `source_paths` / 可选 `baseline_sha256`）
    + payload 文件
  - **consent 字段 schema**：`candidate_uplink_consent` / 时间戳 /
    `consent_terms_version`（在 `.governance/config.json` 内）
  - **uplink 形态锁定**：`gh` issue vs PR（倾向 issue —— 消费者零 fork、零写
    权限，仅需 GitHub 账号；PR 留作备选）
  - **`candidates/` 暂存布局**：gc repo 内、按 `origin` 分目录、排除出 pip 包
- Validation: 全部 spec / 选型经 user review
- Exit criteria: schema / 签名库 / license / 形态全部定案

### Phase 1: install 双门 + 运行时强制 —— 授权 + 强制同意

> 2026-05-18 user 修订：原 Phase 1 只做 install-time 双门；user 指出已装好的
> 项目事后授权失效仍照常运行，要求补**运行时强制（硬冻结）**，并入本 Phase。

- Deliverables:
  - 生成 Ed25519 签名密钥对；公钥进 `governance_core/auth/`（随包分发，
    `pyproject.toml` `package-data` 加 `auth/*`），私钥 maintainer 离线持有
  - 签发工具 `maintainer/issue_auth_code.py` + `gen_signing_key.py`
    （maintainer-only；committed 但排除出 pip 包）
  - `installer.py`：`install` 要求 `--auth-code`、用包内公钥离线验签、提取
    consumer id；紧接着**强制**收集候选上传同意（交互提示 /
    `--accept-candidate-uplink` flag）；授权或同意任一不过 → install 中止、
    自治层不 materialize。授权信息 + 同意写入 `.governance/config.json`
  - `upgrade` / `doctor`：复验已存授权码（无效/缺失 → 报错）；`doctor` 额外
    报告同意状态
  - **运行时强制**：`auth-guard.py` PreToolUse hook（matcher `*`，入
    `hooks_manifest.json`）—— 每次工具调用前复验存储授权码，无效即阻断
    （硬冻结）；验签结果按 (repo, code, pubkey) 缓存
  - license 变更：`pyproject.toml` + `LICENSE` + `README`
  - gc 版本 bump + 文档
- Validation: 有效码 `install` 成功且 config 落 consumer id + 同意；篡改/
  无效/缺失码被拒、自治层不生成；同意答「否」→ install 中止；`doctor` 检出
  失效授权与同意状态；`auth-guard` hook 对有效码放行、对篡改/缺失码阻断、
  缓存命中；包隔离（build 不含 `maintainer/` 与私钥）；governance-core 给
  **自身**（self-hosted 消费者）签授权码、走双门、验证 dogfood
- Exit criteria: 无有效授权码 **或** 不同意上传 → 无法 install/upgrade →
  公共层不 materialize；已装项目授权事后失效 → `auth-guard` 冻结全部工具调用；
  授权消费者身份机制确立

### Phase 2: manifest + baseline hash

- Deliverables:
  - `installer.py`：`install/upgrade` 结束写 `.governance/installed_files.json`
    （逐 install-managed 文件 path + sha256 + source_version + category）
  - 查询工具：给路径，答 install-managed / business（读 manifest）
  - gc patch bump + 文档
- Validation: 消费者 `upgrade` 后 manifest 生成、hash 正确；查询工具对已知
  generic/business 文件分类正确
- Exit criteria: 每个授权消费者装完即有权威的 install-managed 清单 + 漂移
  检测基线

### Phase 3: 候选统一信封 + tagging

- Deliverables:
  - candidate envelope spec 落地：承载 skill / hook / mechanism 三 `kind` 的
    统一信封 + 信封校验工具
  - `/extract-skill`（gc 提供）：extraction 时给 learned skill frontmatter 写
    `layer: candidate-common | business`（拿不准默认 candidate-common）
  - `lesson-classification` skill（gc 提供）：增 "generic→候选 vs project→业务" 轴
  - gc patch bump + 文档
- Validation: 跑一次 `/extract-skill` 产出带 `layer` tag 的 skill；信封校验
  工具对三 kind 正确收/拒
- Exit criteria: 候选信封格式 + tagging 就位

### Phase 4: 候选收集 + 主动提交 + uplink

- Deliverables:
  - **自动收集**：（a）`layer: candidate-common` 净新增 skill → 打包 envelope；
    （b）非破坏 `upgrade` —— 覆盖前对每个 install-managed 文件比对当前 hash vs
    manifest baseline，漂移 → 捕获 diff 成漂移候选 envelope（再覆盖，或按选择
    保留有记录的本地 override）
  - **主动提交**：`/submit-candidate` skill（gc 提供）—— owner 把某能力
    （skill / hook / mechanism）打包成 envelope
  - **uplink**：经 `gh` 把 envelope 上行到 GC（issue/PR，形态按 Phase 0）；
    **uplink 前强制 `sensitive-data` 扫描**，命中即阻断该条并报告。uplink 受
    `candidate_uplink_consent` 门 —— 当前版本恒 true（Phase 1 强制），门代码
    为未来 opt-in 放宽预留
  - `upgrade` 输出报告：N 个文件本地漂移、已捕获为候选
- Validation: `/extract-skill` 候选入流；人为制造一个 install-managed 漂移 →
  `upgrade` → 验漂移被检出、diff 被捕获、未静默丢失；`/submit-candidate`
  跑通；secret 扫描验证一次（含一次"夹带 secret 被阻断"用例）
- Exit criteria: 三来源候选（净新增 / 漂移 / 主动）都能在脱敏后上行到 GC

### Phase 5: GC 侧 curation + 收口闭环

- Deliverables:
  - GC 侧审阅工具/skill：扫 incoming 候选（本地 `candidates/` + GitHub 上
    labeled issue/PR），逐条呈现给 reviewer（人或 core agent），curate 决策：
    提升 / 退回（带理由）/ 转为有记录的本地 override
  - **consumer registry**：GC 侧记录已签发授权码、对应消费者、各自报过的候选
  - 提升动作：候选并入 `governance_core/skills|hooks|tools/` 包源 → 从
    `candidates/` 清除 → 发版下发
  - 触发：定时（schedule）或手动；自动做收集 + 呈现，judgment 人工/agent
  - 文档：收口 hub 模型写进 `docs/architecture.md` / `docs/core-manual.md`
- Validation: 跑一次审阅，候选被正确分流（提升的进包源，退回的留记录）；
  registry 内容正确
- Exit criteria: 候选 → 公共层 → 发版的可重复、文档化闭环；GC 成为名副其实的
  统一治理收口 hub

## Approval Criteria

User 在批准前应能确认：

1. **授权模型**：GC 生产离线签名授权码 —— 它 gate 的是**公共层能力本身**
   （无有效码 → `install` 中止 → 自治层不 materialize → 能力物理不存在），
   不只是 `install` 动作。授权码是威慑 + 身份标识 + 使用条款约束，**不**是
   不可破解的 DRM；license 须从 MIT 改为 source-available
2. **强制同意**：install 时**必须**同意自动上传候选信封，否则不可应用公共层
   —— 这意味着采用 GC = 接受本项目的公共层改进将（在脱敏后）回流到 GC 的
   **公开** repo。这是 ToS 级取舍，由 user 明确认可
3. **收口模型**：GC 是唯一上游收口方；公共能力候选（skill/hook/机制）从授权
   消费者**单向上行**到 GC，由 GC curate 决策提升、再下发
4. **判定保持 curated**：收集 + 呈现 + 上行自动化，提升与否人工/agent 审阅，
   不 auto-promote
5. **uplink 安全**：候选进公开 repo —— uplink 前强制脱敏扫描，命中即逐条阻断
6. **dogfood**：本 proposal 自身是公共层变更（改 installer / CLI / extract-skill
   / lesson-classification）—— 在 governance-core 自身 self-hosted session 内
   按宪法第十一条改包源、重装验证，吃自己的新机制（gc 给自身签授权码、走双门）
7. **6 phase 边界**：每 phase 独立可交付、可单独 revert + republish

## Validation Plan

- Phase 0：spec / 签名库 / license / 形态经 user review
- Phase 1：有效/无效/篡改/缺失授权码四路验证（验后三者自治层不生成）；同意
  答「否」中止 install；`doctor` 检出失效授权与同意状态；gc 自身签码 + 走
  双门 dogfood
- Phase 2：`upgrade` 后查 `installed_files.json` 内容 + hash；查询工具分类抽检
- Phase 3：`/extract-skill` 产出验 `layer` tag；信封校验工具三 kind 验证
- Phase 4：三来源候选各跑通；人为漂移 → `upgrade` 验捕获非丢失；secret 夹带
  用例验证被阻断
- Phase 5：跑一次审阅 → 验候选分流 + registry；文档核对
- 全程：governance-core 自身（self-hosted）作首个 dogfood 授权消费者验证

## Rollback / Recovery

- **Phase 0**：纯设计，无代码
- **Phase 1**：授权 + 同意门逻辑 `git revert` → 回到无门的 `install`；license
  变更同 commit 一并 revert（已发布版本不受影响）；密钥对作废重生
- **Phase 2**：`installer.py` manifest 改动 revert；manifest 是新增产物，删之
  即回无 manifest 态
- **Phase 3**：envelope spec / `/extract-skill` / `lesson-classification`
  改动 revert；`layer` 是附加 frontmatter，旧工具忽略即可
- **Phase 4**：收集 / `/submit-candidate` / uplink / 非破坏 upgrade 逻辑 revert
  → 回到覆盖式 `upgrade`；保留 `--force` 逃生口
- **Phase 5**：审阅工具 / registry revert；`candidates/` 暂存可保留
- 总体：每 phase 是 governance-core repo 的独立 commit，可逐 phase revert +
  republish

## Risks

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| 授权码被改源绕过 | 高 | 低 | 已接受 —— 授权是威慑 + 身份 + 条款，非 DRM；Approval Criteria #1 明示 |
| 签名私钥泄露 → 任何人可签授权码 | 低 | 高 | 私钥 maintainer 离线持有，绝不进 git/包；签发工具排除出 pip 包；泄露后轮换密钥对 + 发新版换公钥 |
| 强制同意把候选推进公开 repo —— 用户未预期 | 中 | 高 | 同意文案明示"进公开 repo"；Approval Criteria #2 把此 ToS 取舍显式交 user 认可；uplink 前强制脱敏 |
| 候选 uplink 夹带 secret 进公开 repo | 中 | 高 | Phase 4 uplink 前强制 `sensitive-data` 扫描、命中逐条阻断；显式"夹带 secret 被阻断"验证用例 |
| 强制同意成为采用门槛 → 劝退潜在消费者 | 中 | 中 | 已接受（user 明确"当前版本必须同意"）；数据模型向前兼容未来放宽为 opt-in |
| 消费者侧无 `gh` / 无 GitHub 账号 → 无法 uplink | 中 | 中 | uplink 形态选 issue（零 fork、零写权限）；envelope 可落地为文件供手动提交兜底 |
| 新增 crypto 运行时依赖 | 中 | 低 | Phase 0 评估纯 Python 内联 Ed25519 实现以零新增依赖；按 Art.7.3 讨论 |
| `candidates/` 暂存堆积无人审 → 候选腐烂 | 中 | 中 | Phase 5 审阅可定时触发；审阅工具报告候选积压数 |
| 非破坏 upgrade 漂移检测有 bug → 该刷新没刷新 / 误判漂移 | 中 | 高 | hash 比对逻辑简单 + Phase 4 显式验证；保留 `--force` 覆盖逃生口 |
| `layer` tag 误判（business 标成 candidate）| 中 | 低 | 默认 candidate + Phase 5 审阅兜底；误判只多一次 review，不污染上游 |
| `candidates/` / `maintainer/` / 私钥误打进 pip 包 | 低 | 高 | Phase 0 spec 明确排除；`packages.find` 限定 `governance_core*`；Phase 1/4 验证 `python -m build` 产物 |
| license 变更的法律面 | 中 | 中 | 非法律专业意见 —— Phase 0 由 user 拍板最终许可文本 |
| 6 phase 体量大 | 中 | 低 | 每 phase 独立可交付、可单独 revert；按既往逐 phase checkpoint 节奏执行 |

## Phase 0 锁定结果（2026-05-18 user confirmed）

三个取舍点 user 决定：签名库 = **纯 Python 内联 Ed25519**；license = **自定义
授权条款**；uplink 形态 = **GitHub issue**。8 项 deliverable 定案如下。

### 1. 授权码 spec

- 算法 Ed25519；实现 = vendored 纯 Python RFC 8032 参考实现 →
  `governance_core/auth/_ed25519.py`（public domain，零运行时依赖）。
- 公钥 → `governance_core/auth/pubkey.json`
  `{"alg":"ed25519","key_id":"gc-2026","key_b64":"..."}`（随包分发）；私钥
  maintainer 离线持有，绝不进 git/包。
- 授权码格式（单行）：`GC1.<b64url(payload_json)>.<b64url(signature)>`。
  - `payload_json` = canonical JSON `json.dumps(obj, sort_keys=True,
    separators=(",",":"))`，UTF-8。
  - payload = `{"consumer_id": str, "issued": "YYYY-MM-DD", "schema": 1}`；
    `expiry`（ISO date）为可选保留键 —— 当前签发工具省略 = 永久码；验签侧有
    `expiry` 且已过即失败。
  - `signature` = Ed25519 对 `payload_json` 原始字节签名。
- 验签：拆 3 段 → 验 `GC1` tag → b64url 解码 → Ed25519 verify（包内
  `pubkey.json`）→ 失败即中止 → 成功取 `consumer_id`。
- 签发工具 `maintainer/issue_auth_code.py`：repo committed，排除出 pip 包。

### 2. license

- `LICENSE` 改自定义 source-available 文本：源码公开可读可 fork；**使用**这套
  治理能力需 maintainer 签发的有效授权码；不授予无码使用权；保留其他权利。
- `pyproject.toml` `license` 指向 `LICENSE`；classifiers 去 MIT 改
  `License :: Other/Proprietary License`。已发布 0.1.2–0.1.6 维持 MIT，变更自
  Phase 1 版本 bump 生效。Phase 1 起草 `LICENSE` 草稿交 user 定稿。

### 3. `installed_files.json` schema

`.governance/installed_files.json`：`{schema, governance_core_version,
generated_at, files:[{path, baseline_sha256, source_version, category}]}`，
`category ∈ hook|skill|command|agent|clause|contract|tool|agent_rule|knowledge`。
判定：在 manifest 内 = install-managed，不在 = business。
（Phase 2 执行修正：原锁定枚举含 `config`、缺 `knowledge` —— 实际无
install-managed 的 config 文件，而 `knowledge/` copy 是 install-managed，
故去 `config`、补 `knowledge`。）

### 4. candidate envelope schema

目录式：`<candidate-id>/candidate.json + payload/`。`candidate.json` =
`{schema, id, kind(skill|hook|mechanism), origin(consumer_id), created, layer,
title, rationale, source_paths[], drift_target?, baseline_sha256?}`。drift 类
候选额外带 `drift_target` + `baseline_sha256`。三来源统一此信封。

### 5. consent + authorization 字段（`.governance/config.json`）

- `candidate_uplink: {consent: bool, consent_at, consent_terms_version}` ——
  当前版本 install 门仅 `true` 放行；schema 允许 `false`（未来 opt-in）。
- `authorization: {auth_code, consumer_id, verified_at}`。

### 6. uplink 形态 = GitHub issue

envelope → `gh issue create`；标题 `[candidate] <kind>: <title> (from
<consumer_id>)`；label `candidate` + `kind/<...>`；body = `candidate.json` +
payload。payload 超 issue body 容量（~65 KB）的承载留 Phase 4 细化。

### 7. `candidates/` 布局

- 消费者侧 staging：`.governance/candidate-outbox/<candidate-id>/`（gitignored）。
- GC 侧 incoming：`candidates/<consumer_id>/<candidate-id>/`（gitignored；
  GitHub issue 为权威记录）。
- consumer registry（Phase 5）独立文件、committed。
- 二者排除出 pip 包（Phase 1/4 验证 build 产物）。

## State Log

- 2026-05-15: draft created by core agent (P-0065)
- 2026-05-18: handed off to governance-core self-hosted shared_state (P-0066 Phase 5); to be executed in governance-core's own session
- 2026-05-18: draft → pending (queued behind P-0068 per user)
- 2026-05-18: **完全重写（第一轮）** —— 从本地/离线 4-phase 候选管道，扩张为
  "授权消费者 + 候选上行 + curated 提升"收口 hub 愿景（6 phase）。
- 2026-05-18: **细化（第二轮）** —— 按 user：(1) 授权码 gate 的是公共层能力
  本身（无码 → install 中止 → 自治层不 materialize），新增"机制详解"段写清
  生产/分发/消费/复验；(2) consent 由 opt-in 改为**当前版本强制必须同意**，
  install 双门（授权 + 同意）任一不过即中止。Phase 1 重构为"install 时双门"。
  待 user 审阅。
- 2026-05-18: pending → approved (user approved after 2-round rewrite (authorized hub vision))
- 2026-05-18: approved → in-progress (Phase 0 design-lock started)
- 2026-05-18: Phase 0 完成 —— 8 项 deliverable 定案（签名库=纯 Python Ed25519，
  license=自定义授权条款，uplink=GitHub issue），锁定结果写入"Phase 0 锁定
  结果"段。Phase 0 无代码、无 commit。进 Phase 1。
- 2026-05-18: Phase 1 执行中 —— user 修订：原设计只做 install-time materialize
  门、显式声明"无需运行时校验"。user 指出已装好的项目事后授权失效仍照常运行，
  要求补**运行时强制**。决定（user 确认）：强度=硬冻结，落点=并入 Phase 1。
  "机制详解"改为"两层 gate"，Phase 1 加 `auth-guard` PreToolUse hook。
- 2026-05-18: Phase 1 提交（commit 581f7e5）—— install 双门（授权码 + 强制
  同意）+ 运行时硬冻结（`auth-guard`）+ 纯 Python Ed25519 + `maintainer/`
  签发工具 + license MIT→自定义 source-available（DRAFT）+ 版本 0.2.0。
  多 owner 签发台账经 user 确认推迟到 Phase 5 consumer registry（不在 Phase 1）。
  待办（挂起）：`LICENSE` 终稿待 user 审定；私钥待 user 离线备份。
- 2026-05-18: Phase 1 `/wrap-up` 完成（commit 0d422a0，STATE.md）。审计发现 3
  个 out-of-scope 问题待后续：`audit_proposals.py` in-flight 路径未 reconcile
  到自托管 shared_state；`tracker --should-extract` 输出自相矛盾；`upgrade`
  copy-based 不 prune 致 registry 残留已删 guide。
- 2026-05-18: Phase 2 执行中 —— `installer.py` 写 `.governance/installed_files.json`
  manifest（128 文件，逐文件 path + sha256 + source_version + category）；
  新增查询工具 `governance_core/tools/whichlayer.py`（路径 → install-managed /
  business）；manifest 进 `.gitignore`（纯派生物）。Phase 0 category 枚举执行
  修正（去 `config`、补 `knowledge`）。版本维持 0.2.0（P-0065 整体一次发版）。
- 2026-05-18: Phase 2 提交（commit ef791c1）—— manifest + baseline hash +
  `whichlayer` 查询工具。附带修 Phase 1 遗留：`verified_at` 码不变则保留、
  committed config.json 不再 churn。验证：gc dogfood upgrade（128 文件）、
  `whichlayer` 抽检、`doctor` exit 0。
- 2026-05-18: Phase 2 `/wrap-up` 完成（commit 98d34b3，STATE.md + core-manual §10）。
- 2026-05-18: Phase 3 提交（commit 1d2a575）—— 候选统一信封：新增包
  `governance_core/candidates/envelope.py`（三 kind skill/hook/mechanism +
  drift 类；`build_envelope` / `validate_envelope` / `make_candidate_id`）；
  校验工具 `governance_core/tools/validate_candidate.py`；extractor 加
  `--layer` flag（写 learned skill `layer:` frontmatter，默认 candidate-common）；
  `extract-skill.md` 插入 layer 分类步骤（重排步骤号）；`lesson-classification.md`
  增 generic-vs-project 轴。验证：envelope 三 kind build+validate、validator
  拒 5 类畸形、extractor `--layer` 实跑产出带 tag skill、upgrade/doctor exit 0、
  build 隔离（candidates 入包）。
- 2026-05-18: Phase 3 `/wrap-up` 完成（commit 9a64915，STATE.md + 归档）。
- 2026-05-18: Phase 4 执行 —— 发现 `sensitive-data-guard` 不存在（README 错误
  声明、无 secret 扫描逻辑可复用）。user 选 **Option B**：建扫描器 + 补全
  `sensitive-data-guard` hook（让 README 成真）。完成（commit 47fdf8f）：脱敏扫描器
  `governance_core/sensitive_scan.py`（HIGH/MEDIUM 分级）+ `sensitive-data-guard`
  PreToolUse hook；`candidates/collect.py`（净新增 candidate-common skill 收集）；
  `candidates/uplink.py`（脱敏扫描 + `gh issue` 传输 + dry-run + 体积上限）；
  CLI `tools/candidate.py`（collect/submit/uplink 子命令，consent 门）；
  `/submit-candidate` 命令；installer `_capture_drift`（upgrade 覆盖前捕获
  install-managed 文件漂移成 drift 候选 + stderr 报告）。实现决定：payload
  内联 issue body（~60KB 上限）、漂移=捕获后覆盖、uplink 带 `--dry-run`。
  验证：扫描器+hook 16 项、Part A 8 项（collect/submit/uplink/secret-abort/
  consent-gate）、Part B 漂移真实 dogfood、upgrade/doctor exit 0、build 隔离。
- 2026-05-18: Phase 4 `/wrap-up` 完成（commit 374493a，STATE.md + 归档）。
- 2026-05-18: Phase 5 提交（commit f5b23f7）—— GC 侧 curation + 收口闭环。新增 consumer
  registry 模块 `governance_core/candidates/registry.py` + committed 台账
  `maintainer/consumer_registry.json`（记已签发消费者 + 候选评审决策）；
  `issue_auth_code.py` 签发时登记消费者（兑现 Phase 1 推迟的"多 owner 签发
  台账"）；`candidate.py` 加 `review`（扫本地 `candidates/` + `gh issue`）/
  `promote`（提升进包源 skill/hook、或退回 override 带理由，决策入 registry）
  子命令；GC 侧 incoming `candidates/` 进 `.gitignore`；收口 hub 模型写入
  `architecture.md` + `core-manual.md §11`。验证：`issue_auth_code` 登记
  registry、curation 11 项（review/promote/reject、registry 内容）、
  upgrade/doctor exit 0、build 隔离（registry 模块入包、台账不泄漏）。
- 2026-05-18: in-progress → implemented (P-0065 all 6 phases implemented (581f7e5..f5b23f7))
