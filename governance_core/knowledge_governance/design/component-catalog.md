---
title: Component Catalog
tags: [design, components, reference]
status: active
created: 2026-04-15
updated: 2026-04-15
owner: core
---

> **TL;DR**: Cross-branch inventory of design assets and component references.

## Design Assets

| Asset | Location | Branch | Description |
|-------|----------|--------|-------------|
| Dashboard Design (.pen) | `analysis/dashboard/design/dashboard.pen` | feature/data-analysis | Pencil prototype file (172KB) |
| Design Showcase Page | `analysis/dashboard/frontend/src/app/design/page.tsx` | feature/data-analysis | Living design reference at `/design` route |

## Component Reference (Claude Code Design System)

Source: `research/references/claude-code-source/src/components/design-system/`
Branch: feature/research

| Component | File | Description |
|-----------|------|-------------|
| Byline | `Byline.tsx` | Attribution display |
| Dialog | `Dialog.tsx` | Modal dialog |
| Divider | `Divider.tsx` | Visual separator |
| FuzzyPicker | `FuzzyPicker.tsx` | Fuzzy search picker |
| KeyboardShortcutHint | `KeyboardShortcutHint.tsx` | Keyboard shortcut display |
| ListItem | `ListItem.tsx` | List item component |
| LoadingState | `LoadingState.tsx` | Loading indicator |
| Pane | `Pane.tsx` | Panel container |
| ProgressBar | `ProgressBar.tsx` | Progress indicator |
| Ratchet | `Ratchet.tsx` | Incremental progress |
| StatusIcon | `StatusIcon.tsx` | Status indicator icon |
| Tabs | `Tabs.tsx` | Tab navigation |
| ThemeProvider | `ThemeProvider.tsx` | Theme context provider |
| ThemedBox | `ThemedBox.tsx` | Themed container |
| ThemedText | `ThemedText.tsx` | Themed text component |
| Color utilities | `color.ts` | Color manipulation utilities |

## Dashboard Business Components

Source: `analysis/dashboard/frontend/src/components/`
Branch: feature/data-analysis

| Category | Location | Description |
|----------|----------|-------------|
| UI Primitives | `components/ui/` | Generic UI components (shadcn/ui + Radix) |
| Cards | `components/cards/` | Business metric cards |
| Charts | `components/charts/` | Data visualization (Recharts) |
| Tables | `components/tables/` | Data tables |
| Tabs | `components/tabs/` | Page-level tab components |

## How to Use This Catalog

1. **Starting UI work**: Read `knowledge/design/design-principles.md` for mandatory conventions
2. **Need a component**: Check this catalog for existing implementations before creating new ones
3. **Design reference**: Use `.claude/agents/design-system-owner.md` role for Pencil design work
4. **Cross-branch access**: Components on other branches are read-only references; coordinate via proposals for changes
