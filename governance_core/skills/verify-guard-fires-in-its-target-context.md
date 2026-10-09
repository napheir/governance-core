---
theme: universal
name: verify-guard-fires-in-its-target-context
description: "A guard that is registered, documented and file-present can still be completely inert. Before trusting any hook/pre-commit layer -- especially when auditing enforcement or deploying a per-clone hook -- exercise it against the context it claims to guard and assert on the exit code."
type: guide
owner: core
tags: [governance, enforcement, hook, audit, cross-clone, inert-guard, verification]
created: 2026-08-20
updated: 2026-10-09
---

# verify-guard-fires-in-its-target-context

A guard that is registered, documented and file-present can still be completely inert. Before trusting any hook/pre-commit layer -- especially when auditing enforcement or deploying a per-clone hook -- exercise it against the context it claims to guard and assert on the exit code.

## Preconditions

1. You are auditing whether an enforcement layer works, deploying a new per-clone hook, or investigating why a rule did not fire
2. You can construct a realistic payload for the guard (hook stdin JSON, staged diff, command string)

## Workflow

1. Enumerate EVERY registration of that guard machine-readably before concluding anything -- parse the config and print (event, matcher, path-form, target-repo) for every entry, do not grep for the first hit and stop. A config that several generations of tooling have written can hold more than one registration of the same guard, and one of them may be perfectly healthy while another is dead. Getting this wrong produces a confident, wrong "this guard is inert" claim: e.g. two dead absolute-path registrations sitting next to one live variable-based registration, where only the full enumeration shows the guard has been working all along
2. From that table, identify which registrations point at THIS repo's copy and which point elsewhere
3. Determine whether the guard is root-sensitive: does it compute a repo root from __file__ (Path(__file__).parent.parent, os.path.join(_HOOK_DIR, '..', '..')) and use it to normalize incoming paths, glob-match, or set a subprocess cwd? If yes, a registration pointing at ANOTHER repo's copy makes it silently pass everything -- the incoming path never normalizes, nothing matches, exit 0
4. Exercise it, do not infer: pipe a realistic payload naming a path from the TARGET repo into the guard and check the exit code, then repeat with a path from the guard's OWN repo as a control. Different exit codes for the same logical case is the proof
5. For layers claimed by documentation, check the actual deployment surface. Untracked surfaces (.git/hooks/, machine-local config) drift silently: compare checksums across all clones AND grep for the tool the docs say is wired in
6. Fix the class, not the instance: put per-clone hooks under an idempotent registration list in whatever tool writes the registrations (installer / sync tool), so a cross-repo reference is rewritten back to clone-local on every run
7. Guard the fix itself: refuse to register a hook whose clone-local file does not exist. Wrappers that treat a missing file as exit 0 turn a well-meant repoint into a silent disable -- strictly worse than the bug being fixed
8. Re-exercise after the fix in the previously-broken context, and confirm idempotency by running the registration tool twice and diffing

## Outputs

- exit-code evidence for target-context vs own-context (the two must agree once fixed)
- idempotent registration entry in the registration tool covering every affected hook
- checksum parity across clones for any untracked deployment surface

## Notes

- Registered != running. Present-on-disk != running. Documented != running. Only a non-zero exit on a case that should be blocked proves it runs
- The tell for root-sensitivity is a repo root derived from __file__ combined with path normalization or a subprocess cwd
- Documentation is the weakest evidence and often the oldest: several documents can describe a pre-commit layer that no clone has ever called
- When the same misregistration affects several hooks, resist fixing only the one in your scope -- but do not silently expand blast radius either; fix what was reviewed and file the rest with the measured evidence attached
- Two generations of tooling writing the same config is the usual cause of a half-dead guard: the newer generation registers correctly, the older one leaves a dead entry beside it, and the dead entry is what you find first. It also means duplicate live registrations -- the same hook running twice per call -- which an exact (matcher, command) dedupe cannot see because both the matcher strings and the command strings differ
- Prefer a config form that carries no environment identity at all (a variable the runtime expands) over one that hardcodes a path and needs a repair pass. A repair pass loses to anything that rewrites the file behind it -- notably a git merge of a tracked config
- The same check applies to a single-repo project whose enforcing copy lives outside the repo (e.g. a user-global hook directory): fixing the in-repo source does not change what actually runs until the enforcing copy is refreshed -- exercise the enforcing copy, not the source
