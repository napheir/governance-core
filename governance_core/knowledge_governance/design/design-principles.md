---
title: Design Principles
tags: [design, principles, ui]
status: active
created: 2026-04-15
updated: 2026-04-15
owner: core
---

> **TL;DR**: Design-then-Code workflow with .pen as single source of truth, HK color conventions, dark-first theme.

## Core Principles

1. **Design Reference is the Single Source of Truth**
   - `.pen` design files are authoritative for all visual implementations
   - Frontend code is merely one implementation; may have drift
   - Never reverse-engineer specs from code or screenshots

2. **Design-then-Code Workflow**
   - New features: Pencil prototype -> user review -> React implementation
   - No coding with spec gaps in Design Reference
   - Every structural change: screenshot-verify immediately

3. **HK Color Convention (Mandatory)**
   - Red = Up/Profit (`#e53935`)
   - Green = Down/Loss (`#43A047`)
   - CALL options = red family, PUT options = green family

4. **Dark-First Theme**
   - Dashboard defaults to dark mode
   - All Design Tokens support Light/Dark variants
   - Pencil files configured with dual-theme variables

## Design Token Categories

| Category | Source File | Description |
|----------|-----------|-------------|
| Colors | `lib/theme.ts` | Color system, chart palette, shape tokens |
| Typography | `lib/typography.ts` | Font scale (size, weight, line-height) |
| Spacing | `lib/spacing.ts` | Gap, padding, chart height system |
| Formatting | `lib/format.ts` | Number, percentage, color mapping utilities |

## Typography

- Data/monospace: `JetBrains Mono`
- Headings/large numbers: `Oswald`

## Spacing Standards

- Section gap: 24px
- Card gap: 16px
- Internal padding: 16px
- Card border-radius: 12px
- Button border-radius: 8px
- Badge border-radius: 999px (pill)
