# Analyzer Patterns Refactor Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Close the self-improvement feedback loop so the renovate-pr-analyzer reads accumulated patterns from the reference file, and eliminate duplicate domain knowledge between the agent and reference file.

**Architecture:** Slim the agent to a generic process engine, centralize all domain-specific patterns in `analysis-patterns.md`, and have the processor skill inject the file path in the dispatch prompt.

**Tech Stack:** Claude Code agents, skills, markdown

**Design doc:** `docs/plans/2026-02-24-analyzer-patterns-refactor-design.md`

**Closes:** #369

---

### Task 1: Add dependency type classification table to analysis-patterns.md

This table currently exists only in the agent (lines 33-41). Move it to the reference file so the agent can load it from there.

**Files:**

- Modify: `.claude/skills/renovate-pr-processor/references/analysis-patterns.md:1-3`

**Step 1: Add the classification table**

Insert a new section after line 3 (after the intro paragraph), before "## Upstream Source Updates":

```markdown
## Dependency Type Classification

Classify each Renovate PR by matching its labels and changed files:

| Label / File Pattern                         | Type              | Upstream Source                |
| -------------------------------------------- | ----------------- | ------------------------------ |
| `renovate/script` + `metadata.yaml` changed  | Upstream source   | GitHub repo from metadata.yaml |
| `renovate/script` + `flavor.yaml` changed    | Docker base image | Container registry project     |
| `renovate/github-actions` + workflow changed | GitHub Actions    | Action's GitHub repo           |
| `renovate/script` + `.devcontainer/` changed | Script/tool dep   | Tool's GitHub repo             |
| `renovate/devcontainer`                      | DevContainer dep  | Devcontainer feature repo      |
| `.pre-commit-config.yaml` changed            | Pre-commit hook   | Hook's GitHub repo             |
| None of the above                            | Other             | Best-effort GitHub search      |
```

**Step 2: Add per-type changelog fetch strategies**

Insert a new section before "## Changelog Parsing Heuristics" (currently around line 200):

````markdown
## Upstream Changelog Fetch Strategies

Follow research priority: Context7 → GitHub → WebFetch → WebSearch (last resort).

**For upstream sources (metadata.yaml):**

The upstream repo is in metadata.yaml's `upstream` field or renovate annotation.

```bash
gh release list --repo <upstream-repo> --limit 10
gh release view <tag> --repo <upstream-repo>
```
````

**For Docker base images (flavor.yaml):**

Find the project repo from the image name using the "Upstream Repo Discovery" mappings in each dep type section.

```bash
gh release list --repo <upstream-repo> --limit 10
gh release view <tag> --repo <upstream-repo>
```

**For GitHub Actions:**

Action repo is in the `uses:` field (e.g., `actions/checkout` → `actions/checkout`).

```bash
gh release list --repo <action-repo> --limit 10
gh release view <tag> --repo <action-repo>
```

**Fallback — CHANGELOG.md:**

```
WebFetch: https://raw.githubusercontent.com/<org>/<repo>/main/CHANGELOG.md
```

**Context7 for well-known projects:**

```
resolve-library-id(libraryName: "<project>", query: "changelog breaking changes <version>")
query-docs(libraryId: "<resolved-id>", query: "breaking changes migration <version>")
```

````

**Step 3: Verify the file is valid markdown**

Read the file back and confirm structure makes sense.

**Step 4: Commit**

```bash
git add .claude/skills/renovate-pr-processor/references/analysis-patterns.md
git commit -m "fix(skills): add dep classification and changelog strategies to analysis patterns

Moves dependency type classification table and per-type changelog
fetch strategies from the analyzer agent into the shared reference
file, preparing for agent slimdown.

Closes #369"
````

---

### Task 2: Slim down renovate-pr-analyzer.md

Remove baked-in domain patterns and add Step 0 to read the reference file.

**Files:**

- Modify: `.claude/agents/renovate-pr-analyzer.md`

**Step 1: Add Step 0 (load analysis patterns)**

Insert after `## Process` (line 19), before `### Step 1`:

```markdown
### Step 0: Load Analysis Patterns

Your dispatch prompt includes an `Analysis patterns:` field with a file path. Read this file using the Read tool before proceeding. It contains:

- Dependency type classification table
- Per-type breaking change signals and impact assessment procedures
- Known upstream repo mappings
- Changelog fetch strategies and parsing heuristics
- Scoring logic for combining signals into a verdict
- Common NO_IMPACT and HIGH_IMPACT scenarios for this repository

Apply these patterns throughout Steps 1-7 below. If no analysis patterns path is provided, proceed with your best judgment but note this in your output.
```

**Step 2: Replace Step 2 (classify dependency type)**

Replace lines 31-41 (the entire Step 2 section including the baked-in table) with:

```markdown
### Step 2: Classify Dependency Type

Using the dependency type classification table from the analysis patterns (Step 0), match the PR's labels and changed files to determine the dependency type and upstream source.
```

**Step 3: Replace Step 4 (fetch upstream changelog)**

Replace lines 55-95 (the entire Step 4 section with per-type strategies) with:

```markdown
### Step 4: Fetch Upstream Changelog

Follow the changelog fetch strategies from the analysis patterns (Step 0). Use the research priority: Context7 → GitHub → WebFetch → WebSearch (last resort).

Use the known upstream repo mappings from the patterns to resolve image names to GitHub repos.
```

**Step 4: Replace Step 6 (impact analysis)**

Replace lines 108-187 (the entire Step 6 section with per-type assessment details) with:

```markdown
### Step 6: Impact Analysis Against Our Configuration

**This is the most critical step.** A breaking change only matters if it affects what we actually use. You MUST cross-reference every breaking change against our real config.

#### 6a: Locate our configuration files

From the PR diff, identify which image or component is affected. Use the config file location map from the analysis patterns (Step 0) to find the relevant files. Read them using the Glob and Read tools.

#### 6b: Cross-reference each breaking change

For EACH breaking change or deprecation found in Steps 4-5, use the per-type impact assessment procedures from the analysis patterns (Step 0) to determine whether it affects our configuration.

#### 6c: Classify impact

| Impact Level       | Meaning                                                             |
| ------------------ | ------------------------------------------------------------------- |
| **NO_IMPACT**      | Breaking change exists but we don't use the affected feature/config |
| **LOW_IMPACT**     | Default changed but may not affect builds; or deprecation warning   |
| **HIGH_IMPACT**    | We use the affected config/feature — will break builds or tests     |
| **UNKNOWN_IMPACT** | Cannot determine if we use the affected feature                     |

Consult the common NO_IMPACT and HIGH_IMPACT scenario tables from the analysis patterns to inform your classification.
```

**Step 5: Replace Step 7 (evaluate verdict)**

Replace lines 189-225 (the entire Step 7 section with baked-in red flags and criteria) with:

```markdown
### Step 7: Evaluate and Determine Verdict

Use the scoring heuristic and red flag keywords from the analysis patterns (Step 0) to evaluate the overall risk.

**SAFE criteria (ALL must be true):**

- No breaking changes found, OR all breaking changes have **NO_IMPACT** on our config
- No open bugs with high engagement (>5 reactions) for target version
- Breaking changes exist but verified that we don't use the affected features

**RISKY criteria (ANY is true):**

- Breaking change with **HIGH_IMPACT** — we use the affected config/feature
- Known bugs with significant engagement affecting features we use
- Migration steps required that affect our build pipeline

**SAFE despite breaking changes (important distinction):**

- Major version bump BUT all breaking changes are **NO_IMPACT** → still SAFE
- Feature removed BUT we don't use that feature → still SAFE

**UNKNOWN criteria:**

- Cannot find upstream repo or changelog
- Changelog is empty or unhelpful
- Cannot determine scope of changes
- Breaking change found but **UNKNOWN_IMPACT** — cannot verify if we use the feature
```

**Step 6: Verify the agent file reads cleanly**

Read the full file back and confirm the step numbering (0-10) is consistent and all references to "analysis patterns (Step 0)" make sense.

**Step 7: Commit**

```bash
git add .claude/agents/renovate-pr-analyzer.md
git commit -m "fix(skills): slim analyzer agent to generic process engine

Removes baked-in domain patterns from Steps 2, 4, 6, 7 and adds
Step 0 to load patterns from the reference file. The agent now
references the analysis-patterns.md knowledge base for all
domain-specific detection logic.

Part of #369"
```

---

### Task 3: Update processor dispatch prompt

Add the analysis patterns file path to the dispatch prompt so the analyzer knows where to find it.

**Files:**

- Modify: `.claude/skills/renovate-pr-processor/SKILL.md:67-73`

**Step 1: Update the dispatch prompt**

Replace the Phase 2 dispatch prompt block (lines 67-73) with:

```
For each PR, use Task tool with:
  subagent_type: "renovate-pr-analyzer"
  run_in_background: true
  prompt: "Analyze Renovate PR #<number> in anthony-spruyt/container-images for breaking changes.
           GitHub issue: #<tracking-issue-number>
           Repository: anthony-spruyt/container-images
           Analysis patterns: .claude/skills/renovate-pr-processor/references/analysis-patterns.md
           Return your analysis in the MANDATORY output format specified in your instructions."
```

**Step 2: Commit**

```bash
git add .claude/skills/renovate-pr-processor/SKILL.md
git commit -m "fix(skills): inject analysis patterns path into analyzer dispatch prompt

The processor now tells the analyzer where to find the reference
file, completing the feedback loop: Phase 5b writes patterns →
next run's analyzers read them.

Part of #369"
```

---

### Task 4: Update tracking issue in spruyt-labs repo

Post findings to the cross-repo issue so an agent can apply the same fix there.

**Files:** None (GitHub API only)

**Step 1: Post comment on spruyt-labs issue**

```bash
gh issue comment 537 --repo anthony-spruyt/spruyt-labs --body "<summary of changes and how to apply>"
```

**Step 2: Verify comment posted**

```bash
gh issue view 537 --repo anthony-spruyt/spruyt-labs --comments
```
