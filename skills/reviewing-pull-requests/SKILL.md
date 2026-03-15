---
name: reviewing-pull-requests
description: Perform effective code review for Mu2e pull requests. Use when reviewing PRs, assessing risk, checking cross-repo impacts, validating tests/builds, and producing actionable reviewer feedback with severity and evidence.
compatibility: Requires git access, Mu2e offline context, and ability to run targeted checks when needed
metadata:
  version: "1.2.0"
  last-updated: "2026-03-06"
---

# Reviewing Pull Requests

## Purpose

Use this skill to review pull requests in a way that is:

- Context-aware for Mu2e Offline/Production/mu2e-trig-config workflows
- Actionable for authors (clear findings, impact, and fixes)
- Proportional to risk (deep where needed, light where safe)

## Scope

These conventions are intended for Mu2e **offline** repositories only.

Apply this skill's conventions to:

- `Offline`
- `Production`
- `EventNtuple`
- `EventDisplay`
- `DQM`
- `Tutorial`
- `PassN`
- `RefAna`
- `ArtAnalysis`

For other repositories, treat these conventions as out of scope unless the PR explicitly asks to apply them. Other repos may be online, personal, or minor projects with different standards.

---

## Standard Review Context Packet

When asking an AI reviewer to review a PR, provide this minimum packet first.

1. **Intent**: what behavior is changing and why.
2. **Scope**: files/modules affected; what is explicitly out-of-scope.
3. **Risk areas**: physics behavior, data products, config compatibility, performance, memory, threading.
4. **Validation evidence**: exact commands run, build/test status, representative outputs.
5. **Environment**: branch, platform, build mode (prof/debug), dependency assumptions.
6. **Cross-repo links**: related changes in `Offline`, `Production`, `mu2e-trig-config`.
7. **Acceptance criteria**: what must be true for approval.

If this packet is missing, ask for missing items before issuing strong conclusions.

---

## Mu2e-Specific Review Priorities

### 1) Correctness and science intent

- Does the change preserve intended physics behavior?
- Are defaults and thresholds justified?
- Any silent behavior changes in reconstruction or filtering?

### 2) Configuration contracts (FHiCL)

- If module config changed, does validated FHiCL schema remain coherent?
- For EDProducer modules, expect validated pattern and parameters alias:

```cpp
using Parameters = art::EDProducer::Table<Config>;
```

- Are `.fcl` keys aligned with `Config` names and types?

### 3) Cross-repo consistency

- Do code changes require corresponding `Production` updates?
- Do trigger/config generation changes require `mu2e-trig-config` updates?
- Are referenced module labels and paths still valid end-to-end?

### 4) Build and operational safety

- Will this pass strict compiler settings (`-Werror`) in expected environments?
- Any likely runtime failures due to missing services/modules or config keys?
- Any obvious performance regressions in hot paths?

### 5) Maintainability

- Is the change minimal and focused?
- Is naming clear and consistent with nearby code?
- Are assumptions documented where non-obvious?

---

## Rules

Source of truth: `https://mu2ewiki.fnal.gov/wiki/CodingStandards`.
If this skill conflicts with that page, follow the wiki.

Reviewers should enforce these high-impact rules:

- Use Mu2e file extensions: `.hh` and `.cc` for Mu2e code.
- Require changes to be compatible with the Mu2e baseline language standard: `-std=c++20`.
- No inter-module communication outside `art::Event` (except EDFilter true/false behavior).
- Include only headers actually needed; avoid speculative includes.
- Do not use `using` directives/declarations in headers; fully qualify types in headers.
- Require header guards on all headers.
- Avoid macros except approved uses (header guards, architecture selection, DEFINE_ART_* macros, message facility macros, debug enabling).
- Keep Mu2e classes in the `mu2e` namespace unless coordinated with software team.
- Require explicit first-order library dependencies in build files.
- Forbid linkage loops between libraries.
- Require clean compile at required warning levels (subject to approved external exceptions).
- Avoid raw `new`/`delete` patterns unless forced by external APIs; prefer safe ownership.
- Enforce data-product rules: no public data, no non-rebuildable pointers, and no MC info inside `RecoDataProducts`.
- Do not cache `art::Handle`/`art::ValidHandle`/`GeomHandle`/`ConditionsHandle` across events.
- Prefer `const` and `override` where applicable.
- For runtime errors, use `cet::exception` with meaningful category/message; do not use `assert` for production runtime control flow.
- Protect production prints with a verbosity flag or message facility.

---

## Recommendations

Source of truth: `https://mu2ewiki.fnal.gov/wiki/CodingStandards`.
If this skill conflicts with that page, follow the wiki.

Reviewers should strongly encourage these recommendations:

- Keep comments focused on intent; avoid code-history comments in source.
- Match local conventions when touching existing files, unless correcting major violations.
- Prefer straightforward, "vanilla" C++ constructs over clever or highly compact patterns in long-lived code maintained by part-time contributors.
- Favor readability and maintainability over compactness or micro-optimizations unless performance data shows the optimization is necessary.
- Prefer clear naming and consistent capitalization; avoid Hungarian notation in normal cases.
- Prefer private data with accessors for broadly used/event-data classes.
- Keep class declarations short; move long function bodies to `.cc` unless inlining is justified.
- Prefer one statement per line.
- Prefer pre-increment (`++i`) over post-increment (`i++`) when equivalent.
- Avoid ambiguous `operator<` definitions for types with multiple meaningful sort orders; prefer named comparator functions.
- Avoid `std::pair` where a named struct improves readability.
- Prefer ordered includes: local interface, local project, non-standard libs, near-standard libs, C++ stdlib, C headers.
- Use CLHEP units/constants with explicit qualification (for example `CLHEP::mm`), especially for short names.
- Follow Mu2e data-product access patterns and validate FHiCL consistency (`fhicl-dump -a`) when config behavior changes.

---

## Local Conventions

Capture and enforce project-local patterns here, even when they are not universal C++ style rules.

### Include Guard Naming

- Canonical style uses project/path words plus file base name with `_hh` suffix.
- Current Mu2e convention example:

```cpp
#ifndef GeneralUtilities_FooBar_hh
#define GeneralUtilities_FooBar_hh
// ...
#endif
```

- Repository prefix rule:
- In `Offline`, omit the repo prefix from include guards.
- In other repos, include the repo name as a prefix in the guard token.

Examples:

- `Offline/GeneralUtilities/inc/FooBar.hh` -> `GeneralUtilities_FooBar_hh`
- `Production/.../MyHeader.hh` -> `Production_<Path>_MyHeader_hh`
- `mu2e-trig-config/.../TrigThing.hh` -> `mu2e_trig_config_<Path>_TrigThing_hh`

Reviewer check:

- Flag headers whose include guards do not follow the repository-specific naming convention.
- Default severity: `S2` (raise if collision or multiple-include bugs are observed).

---

## Review Workflow

1. **Read PR intent** and restate expected behavior changes.
2. **Check PR hygiene** and, if needed, provide a polite reminder labeled as best practice:
  - Keep the PR targeted to a single topic.
  - Provide a meaningful PR description (intent, scope, and validation summary).
3. **Scan changed files** for high-risk categories (interfaces, config, data products, paths).
4. **Check contracts** (code <-> FHiCL <-> job config).
5. **Verify evidence** (tests/build commands and outputs).
6. **Report findings** with severity, evidence, and suggested fix.
7. **Summarize residual risk** and approve/request changes accordingly.

---

## Severity Levels

- **S0 Blocker**: incorrect behavior, data corruption, crash, invalid configuration, or missing required cross-repo change.
- **S1 Major**: high-likelihood bug/regression or incomplete validation for risky change.
- **S2 Minor**: maintainability/readability issue with low immediate risk.
- **S3 Nit**: style/format/comment-only suggestion.

Only raise severity when evidence supports it.

---

## What to Ask the Author (if missing)

Use these concise prompts:

- "Best practice reminder: could you keep this PR focused on a single topic, or split unrelated changes into follow-up PRs?"
- "Best practice reminder: please add a meaningful PR description including intent, scope, and validation evidence."

- "What exact user-visible behavior should change?"
- "Which files/repos are intentionally not touched in this PR?"
- "What commands did you run to validate and what were outcomes?"
- "Any expected downstream config/data-product impacts?"
- "What rollback path exists if this regresses in production?"

---

## Evidence Rules

- Prefer concrete evidence (code locations, command output, failing scenario) over speculation.
- Distinguish **observed issue** vs **potential risk**.
- If uncertain, label assumptions explicitly.
- Avoid requiring unrelated cleanup for approval.

---

## Output Template

```markdown
### PR Review Summary

**Decision**
- <approve | request changes | comment only>

**Scope understood**
- <1-3 bullets>

**Findings**
1. [S0|S1|S2|S3] <title>
   - Evidence: <file/behavior/command>
   - Impact: <why it matters>
   - Suggested fix: <concrete change>

2. [Sx] ...

**Validation check**
- Build/tests run: <yes/no + commands>
- Config contract check: <pass/fail/partial>
- Cross-repo consistency: <pass/fail/needs follow-up>

**Residual risk**
- <short bullets>

**Author follow-ups**
- <numbered actionable requests>
```

---

## Fast Starter Prompt for Copilot Review

```markdown
Review this PR using the `reviewing-pull-requests` skill.

Intent:
<what is changing and why>

Scope:
<files changed + out-of-scope>

Risk areas:
<physics/config/perf/etc>

Validation run:
<commands + outputs>

Cross-repo links:
<related PRs/branches>

Acceptance criteria:
<must-pass conditions>

Return findings with severity (S0-S3), evidence, and suggested fixes.
```

---

## Notes for Mu2e FHiCL-Heavy PRs

For PRs touching `.fcl` composition, include checks that:

- top-level `Production` config intent is preserved,
- `Offline/*/fcl/prolog.fcl` defaults are overridden intentionally,
- dotted epilog overrides resolve as expected,
- include resolution via `FHICL_FILE_PATH` is valid,
- `fhicl-dump -a` provenance confirms final values.
