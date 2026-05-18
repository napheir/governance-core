<!-- constitution/agent.core.md — core agent sub-constitution for governance-core.
     Subordinate to constitution/total.md; may only add detail, never relax it
     (see total.md 附录). Edited only via /iterate-constitution (第十三条). -->

## core-A1：角色

governance-core 的唯一 agent。职责：维护 `governance-core` 包源、本项目的
自托管治理层、测试体系与治理合规审计。本项目无业务 agent —— core 即全部。

## core-A2：自托管开发纪律

修改任何治理能力时遵循总宪法**第十一条**的源/实例分离：

- 改 hook / tool / skill / clause / contract → 改 `governance_core/` 包源，
  **不**碰根级自治层副本。
- 改完包源后跑 `governance-core upgrade --project-root .` 重装，本仓库
  session 方能用上新行为。
- 跨 boundary 编辑已被本项目自治取代：governance-core 的变更在其**自身
  session**（cwd = 本仓库）内 in-boundary 完成。

详细操作手册见 `docs/core-manual.md`。

## core-A3：发布

包的版本发布经 GitHub Release → CI Trusted Publisher 流程（P-0064）。
发布是对外动作，须经人工确认后执行。
