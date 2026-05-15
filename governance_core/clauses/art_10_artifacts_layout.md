---
clause_id: art_10_artifacts_layout
clause_class: constitution-clause
extracted_from: agent-core CLAUDE.md (9f31024b)
source_constitution: constitution/total.md
generic_status: mixed
phase_2_action: needs-config-injection
---

## 第十条：Artifacts 输出规范

> **Example content note**: The specific agent names, directory paths, contract files, and pipeline references in tables below are drawn from the upstream project where governance-core was first developed. Downstream projects substitute their own domain via `.governance/config.json` and project-specific clause files. The principle (multi-agent topology, directory ownership, contract-based exchange) is generic.



**红线**：`artifacts/` 不进 git（见第九条 .gitignore 表）。每个 agent 各
写各自子目录。

各 agent 输出路径表（rules/trade/data/simu/research/tests + dataset registry
约定）见 `knowledge/governance/artifacts-layout.md`。

---
