---
theme: universal
name: triage-and-trim-bloated-memory-index
description: "When a per-agent native memory index (auto-injected MEMORY.md) approaches its read cap, triage entries into 4 buckets and trim/graduate — bounding the always-loaded index without losing durable lessons."
type: guide
owner: core
tags: [memory, native-memory, index-hygiene, skill-graduation, recall, governance]
created: 2026-06-30
updated: 2026-07-01
---

# triage-and-trim-bloated-memory-index

When a per-agent native memory index (auto-injected MEMORY.md) approaches its read cap, triage entries into 4 buckets and trim/graduate — bounding the always-loaded index without losing durable lessons.

## Preconditions

1. native file-based memory 有自动注入的 index(MEMORY.md) 且逼近 read cap
2. 另有 git-tracked knowledge/skill 系统带主动 surface(tier/cluster/router)供毕业

## Workflow

1. 诊断: 分清哪套 memory 撑爆(native MEMORY.md 每会话注入 vs knowledge/ pull-only); 量 index 字节 vs 读取上限 + 每行 hook 长度
2. Triage 每条 index 入 4 桶: B1(durable+跨clone→毕业 skill) / B2(查阅型→knowledge) / B3(易失→留 native 瘦钩子) / B4(已在 skill/hook/宪法→删)
3. Verify-before-drop: 删任何条目前实读其声称的 codification source 坐实覆盖(读 body 非 desc, 可跨≥2 skill 分散覆盖)
4. Line-oriented 瘦索引: 保留条目 hook 压到 ≤100字(relevance trigger 非 content summary); 删行/改行必须按行操作(字符串匹配删会并相邻行)
5. B1 按召回正确性 gate 毕业: skill存在/已覆盖 + 显式声明 surface(tier/cluster 无默认) + router 关键词用真实历史触发语 + closure check 确认 surface 可达再 drop native

## Outputs

- 瘦身后的 MEMORY.md index(≤目标字节, hooks ≤100字)
- 只读 lint 报告器(memory_lint.py 式)
- frontmatter+index schema 契约 + 召回正确性 gate
- 毕业并接好 surface 的 skill

## Notes

- staleness 治不了无界增长——若多数条目 no-expiry(feedback/user), 是 size 纪律+毕业而非 staleness 在 bound index
- B1 毕业是为跨 clone reach 不是主动召回(≤100 native 钩子本就为 owner 每会话注入)
- never auto-delete: 工具只报候选, 人工确认
- 编辑 index 必须 line-oriented(字符串匹配删会并相邻行)
