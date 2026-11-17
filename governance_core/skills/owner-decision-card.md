---
theme: universal
name: owner-decision-card
description: Whenever you ask the project owner to decide or approve anything (a proposal, a release, an upgrade, a choice between options), lead with a decision card of at most 8 lines, and end every message that leaves something open with a list of what waits on the owner.
type: guide
tags: [governance, owner, approval, communication, proposal]
created: 2026-11-17
updated: 2026-11-17
---

# Owner Decision Card

Owners run several long projects in parallel. They lose track of details and
of what they decided earlier, and long write-ups are where that happens. The
card gives them what they need to decide in one glance. The waiting list makes
sure no question to the owner lives only in the agent's context (P-0139).

## When

Use the card for every request for the owner's decision:
- approving or rejecting a proposal;
- confirming a release, an upgrade or any other outward or hard-to-undo step;
- choosing between options.

One card per decision. Status updates and answers to questions need no card.

## The card

At most 8 lines, in the owner's language, placed before the details:

1. **What changes**: the change in one line, in the owner's terms.
2. **Cost**: effort, time, tokens, or money.
3. **Risk**: what could go wrong, and its mitigation.
4. **How to undo it**: the rollback, and whether data is lost.
5. **How you would notice**: the symptom the owner would see if it went wrong.
6. **Defaults picked for you**: every choice made on the owner's behalf, so a silent "ok" never approves something they did not see.

For a proposal, the same card goes under `## Decision Card` at the top of the
file. `proposal_lib` warns on submit and approve when it is missing, still the
placeholder, or longer than 8 lines.

## The waiting list

End every message that leaves anything open with a short list headed in the
owner's language (for example "Waiting on you" / "等你处理"). It holds every
item that waits on the owner: decisions, confirmations, actions only they can
take (a `!` command, a step in another project's session).
- Include items from earlier messages that are still open.
- Leave the list out only when nothing waits.

## After the decision

When the owner approves with "as you suggest" or similar, record which
defaults were delegated:
- for a proposal, in the approve `--note`;
- otherwise, in STATE or the decision record.

The owner can later see what they actually agreed to.

## Anti-patterns

- A card that restates the proposal's goals instead of its cost, risk and undo.
- Defaults left out of the card because "they are obvious".
- Burying the decision under analysis: card first, details after.
- A question to the owner that appears only mid-message and not in the waiting list.
