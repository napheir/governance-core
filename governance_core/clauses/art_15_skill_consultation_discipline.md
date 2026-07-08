---
clause_id: art_15_skill_consultation_discipline
clause_class: constitution-clause
extracted_from: governance-core #100 (skill discover->consult->apply loop)
source_constitution: constitution/total.md
generic_status: generic
phase_2_action: ready-to-use
---

## 第十五条：技能咨询纪律

任务开始前，agent 必须先咨询 SessionStart 注入的技能菜单 —— **universal skills**
（每会话注入的 name + 一句话描述）与 **scenario clusters**（`cluster -> members`
映射，skill body 懒加载）。

**纪律规则**：

- 进入某个场景（scenario）时，**加载该 cluster 的相关 skill 而非重新推导**已有
  流程。
- 命中某 universal skill 所描述的任务形态时，先 load 该 skill 再动手。
- skill body 懒加载（Skill tool）；菜单只给名字 + 描述 + cluster 映射，咨询成本
  极低，没有"太贵所以跳过"的借口。
- 咨询是判断而非机械：菜单未命中当前任务时，正常推进，无需强行套用。

**为什么是纪律**：extract -> register -> surface -> **consult** -> apply 这条
闭环只在 skill 被实际咨询时闭合。略过咨询 = 技能体系沦为"提取却从不复用"的
死重（"可发现" != "被咨询"）。

**职责边界**：

- SessionStart 的技能注入**有界**（只发名字 + 描述 + cluster 映射，body 懒加载），
  以免 prompt prefix 膨胀；该注入器由 governance-core 维护。
- universal 集（`theme: universal` 的 skill + 各 agent 自有的 learned skill）与
  scenario-cluster 成员（`knowledge/skills/_scenario_clusters.json`）由**各 agent
  在自己 clone 自著**（`theme` 由 sync_infra 强制路由）；契约见
  `knowledge/governance/skill-scenario-clusters.md`。

**子宪法扩展点**：各 agent 可在子宪法补充本 agent 的 universal 集 / cluster 划分
约定与触发细节，但不得放宽"先咨询、后推导"的纪律。

---
