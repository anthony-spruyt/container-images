---
name: renovate-pr-processor
description: Use when reviewing, merging, or batch-processing open Renovate dependency update PRs. Triggers on "review renovate PRs", "merge renovate", "process renovate", "batch renovate", "handle renovate PRs", "check renovate PRs", or "/renovate".
---

# Renovate PR Processor

Batch-process all open Renovate PRs: analyze each for breaking changes in parallel, present findings for user confirmation, and merge safe ones sequentially.

## Quick Reference

| Item             | Value                                           |
| ---------------- | ----------------------------------------------- |
| Analysis agent   | `renovate-pr-analyzer` (dispatched per PR)      |
| Merge strategy   | Squash via `gh pr merge --squash`               |
| Merge order      | patch → minor → major → unlabeled               |
| Failure handling | Revert merge commit, ask user to push, continue |

## Workflow

### Phase 1: DISCOVER

Fetch all open Renovate PRs and sort by risk level.

```bash
gh pr list --repo anthony-spruyt/container-images --author "renovate[bot]" \
  --json number,title,labels,headRefName --limit 50
```

Sort PRs by risk level. Parse version change from PR title/branch:

1. Patch updates — lowest risk (title contains "patch" or branch contains "patch")
2. Minor updates — medium risk
3. Major updates — highest risk
4. Unknown — treat as unknown risk, process last

If no PRs found, report "No open Renovate PRs" and exit.

### Phase 2: ANALYZE (parallel)

Create a GitHub tracking issue for the batch run. Build the PR list from the discovered PRs before creating the issue:

```bash
# Build the PR list (construct this dynamically from discovered PRs)
# Format each PR as: - #<number> <title>
# Sorted by risk order (patch → minor → major → unknown)

gh issue create --repo anthony-spruyt/container-images \
  --title "chore(deps): batch renovate PR processing $(date +%Y-%m-%d)" \
  --label "chore" \
  --body "$(cat <<'ISSUE_EOF'
## PRs

- #<number> <title>
- #<number> <title>
...

## Affected Area
- Container images and CI/CD
ISSUE_EOF
)"
```

Dispatch `renovate-pr-analyzer` agent for EACH PR in parallel using the Task tool:

```
For each PR, use Task tool with:
  subagent_type: "renovate-pr-analyzer"
  run_in_background: true
  prompt: "Analyze Renovate PR #<number> in anthony-spruyt/container-images for breaking changes.
           GitHub issue: #<tracking-issue-number>
           Repository: anthony-spruyt/container-images
           Return your analysis in the MANDATORY output format specified in your instructions."
```

Wait for all analysis agents to complete. Collect their verdicts.

### Phase 3: REPORT & CONFIRM

Present a summary table to the user:

```
## Renovate PR Analysis Results

### SAFE (will merge)
| PR | Title | Version Change | Reasoning |
|----|-------|---------------|-----------|
| #N | ...   | X → Y (patch) | No breaking changes found |

### RISKY (will skip)
| PR | Title | Version Change | Reasoning |
|----|-------|---------------|-----------|
| #N | ...   | X → Y (major) | CLI flag changes detected |

### UNKNOWN (will skip)
| PR | Title | Reasoning |
|----|-------|-----------|
| #N | ...   | Could not find upstream changelog |

Proceed with merging N SAFE PRs? (You can override any verdict)
```

Wait for user confirmation. The user may:

- Approve as-is
- Promote RISKY/UNKNOWN → merge (override)
- Demote SAFE → skip (override)

### Phase 4: MERGE (sequential)

For each confirmed PR, in risk order (patch → minor → major):

#### Step 4.1: Check merge eligibility

```bash
gh pr view <number> --repo anthony-spruyt/container-images --json mergeable,mergeStateStatus
```

If not mergeable (conflicts), skip with comment and continue.

#### Step 4.2: Merge

```bash
gh pr merge <number> --squash --repo anthony-spruyt/container-images
```

#### Step 4.3: Wait for CI

After merging, check if CI passes on the resulting main branch commit. The CI pipeline runs MegaLinter and image builds.

```bash
# Wait briefly for checks to register, then monitor
sleep 10
gh run list --repo anthony-spruyt/container-images --branch main --limit 3 \
  --json databaseId,status,conclusion,name,headSha

# Watch the most recent run
gh run watch <run-id> --repo anthony-spruyt/container-images
```

If CI passes, continue to next PR. If CI fails, follow the failure handling below.

#### Step 4.4: Handle CI failure

**On CI FAILURE:**

1. Revert the merge commit locally:
   ```bash
   git pull origin main
   git revert HEAD --no-edit
   ```
2. Ask user to push the revert (branch protection prevents direct push)
3. Post comment on the PR explaining the failure and revert
4. Continue to next PR

### Phase 5: SUMMARY

Print final report and post to tracking issue:

```
## Renovate Batch Processing Complete

### Merged Successfully
| PR | Title | Version Change | CI Status |
|----|-------|---------------|-----------|
| #N | ...   | X → Y         | Passed / Pending |

### Skipped (RISKY/UNKNOWN)
| PR | Title | Reason |
|----|-------|--------|
| #N | ...   | Breaking changes: CLI flag removed |

### Reverted (failed CI)
| PR | Title | Failure Reason |
|----|-------|----------------|
| #N | ...   | MegaLinter failed on new version |

### Summary
- Total PRs: N
- Merged: N
- Skipped: N
- Reverted: N
- Tracking issue: #<number>
```

Post this summary as a comment on the tracking issue. If all PRs were processed successfully (none reverted), close the tracking issue.

### Phase 5b: SELF-IMPROVEMENT

Collect all `### Suggested Improvements` sections from the analyzer agents' outputs. If any suggestions were made:

1. Present them to the user grouped by type:

   ```
   ## Suggested Improvements from This Run

   ### Missing Upstream Repo Mappings
   - <image-name> → <github-org/repo>

   ### New Changelog Patterns Discovered
   - <description>

   ### Analysis Pattern Gaps
   - <description>

   Apply these improvements to the reference files? (Y/N)
   ```

2. If user approves, apply the improvements:
   - **Repo mappings** → add to `references/analysis-patterns.md` under "Upstream Repo Discovery"
   - **Changelog patterns** → add to `references/analysis-patterns.md` under "GitHub Release Notes Patterns"
   - **New breaking change signals** → add to `references/analysis-patterns.md` under appropriate dep type section
   - **False positives** → add to "Common NO_IMPACT Scenarios" table

3. Commit improvements with message: `fix(skills): update analysis patterns from renovate batch run <date>`

This feedback loop means the analyzer gets smarter with every batch run.

## Edge Cases

| Scenario                            | Handling                                                                                 |
| ----------------------------------- | ---------------------------------------------------------------------------------------- |
| No open Renovate PRs                | Report and exit                                                                          |
| All PRs RISKY/UNKNOWN               | Report findings, skip merges, exit                                                       |
| PR has merge conflicts              | Skip with comment, continue to next                                                      |
| CI times out                        | Treat as failure, follow revert path                                                     |
| Upstream repo not found by analyzer | Verdict is UNKNOWN, skip unless user overrides                                           |
| Multiple PRs touch same component   | Process sequentially; second PR may conflict after first merges — check mergeable state  |
| Grouped Renovate PR (multiple deps) | Analyzer assesses each dep in the group; overall verdict is the worst individual verdict |

## Additional Resources

### Reference Files

- **`references/analysis-patterns.md`** — Breaking change detection patterns by dependency type (upstream sources, Docker base images, GitHub Actions, script deps, pre-commit hooks), upstream repo discovery, changelog parsing heuristics, and scoring logic
