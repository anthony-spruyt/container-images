# Claude Agent Image Split

Split the single `claude-agent` container image into three independent, role-specific images for read, write, and SRE investigation workloads.

## Motivation

The orchestration platform on the k8s cluster (n8n + BullMQ + GitHub webhooks) drives three distinct agent workload types:

1. **Read** — PR review, Renovate PR triage, issue refinement. No code changes.
1. **Write** — fix bad PRs, implement issues. Commits and pushes code.
1. **SRE** — investigate cluster state in spruyt-labs. No code changes, no cluster mutations.

Each workload has different tooling requirements. A single image either bloats with unused tools or lacks role-specific ones. Independent images keep each lean and purpose-built.

## Architecture

Three independent images, all built from `node:24-slim`. No cross-image dependencies. No build ordering.

```text
node:24-slim ──┬── claude-agent         (read)
               ├── claude-agent-write   (write)
               └── claude-agent-sre     (investigate)
```

## Shared Core (all 3 images)

Installed in every image:

| Tool              | Purpose                    |
| ----------------- | -------------------------- |
| Claude Code CLI   | Agent runtime              |
| Aikido safe-chain | npm supply chain security  |
| git               | Repository operations      |
| jq                | JSON processing            |
| python3 + pip     | Scripting support          |
| gh CLI            | GitHub API operations      |
| ripgrep           | Fast recursive code search |

## Image Specifications

### claude-agent (read)

**Purpose:** Read-only agent for PR review, Renovate triage, issue refinement.

**Contents:** Shared core only. No additional tools.

**Changes from current image:**

- Add `gh` CLI
- Add `ripgrep`
- Update `test.sh` to verify new binaries
- Update `README.md`

**Directory:** `claude-agent/` (existing)

### claude-agent-write

**Purpose:** Write agent for implementing issues, fixing PRs. Commits and pushes code with pre-commit hook enforcement.

**Contents:** Shared core plus:

| Tool       | Purpose                                |
| ---------- | -------------------------------------- |
| pre-commit | Git hook framework for code quality    |
| Go         | Go language support for Go-based repos |

**Directory:** `claude-agent-write/` (new)

### claude-agent-sre

**Purpose:** Investigation-only agent for spruyt-labs k8s cluster. No write operations.

**Contents:** Shared core plus:

| Tool         | Purpose                           |
| ------------ | --------------------------------- |
| kubectl      | Kubernetes API operations         |
| kustomize    | Kustomize manifests               |
| helm         | Chart management                  |
| helmfile     | Declarative helm chart management |
| helm plugins | Additional helm functionality     |
| cilium       | Cilium CNI operations             |
| hubble       | Network observability             |
| talosctl     | Talos Linux node management       |
| talhelper    | Talos configuration helper        |
| flux         | GitOps toolkit                    |
| velero       | Backup inspection                 |
| cnpg plugin  | CloudNativePG operations          |
| falcoctl     | Falco security runtime            |

**Directory:** `claude-agent-sre/` (new)

## Per-Image Files

Each image directory contains:

| File            | Purpose                                                 |
| --------------- | ------------------------------------------------------- |
| `Dockerfile`    | Self-contained, all installs inline                     |
| `metadata.yaml` | Version config with `auto_patch: true`                  |
| `test.sh`       | Verify all expected binaries are present and functional |
| `.trivyignore`  | Per-image vulnerability ignores as needed               |
| `README.md`     | Image purpose and contents                              |

## Version Management

- Every tool version annotated with `# renovate:` comments
- All 3 images update independently via separate Renovate PRs
- Shared tools (Claude CLI, safe-chain) tracked separately per image
- Base image (`node:24-slim`) tracked separately per image

## Metadata

### claude-agent

Keep current version scheme (`version: "1.1"`, `auto_patch: true`).

### claude-agent-write and claude-agent-sre

New images start at:

```yaml
version: "1.0"
auto_patch: true
```

## Integration

- CLAUDE.md and `.claude/` skills synced to all repos via xfg/repo-operator — agent behavior and standards are repo-driven, not image-driven
- n8n workflows select image based on task type (read/write/sre)
- Kyverno policies in spruyt-labs configure pod injection per agent type

## Related Issues

- [#492](https://github.com/anthony-spruyt/container-images/issues/492) — add pre-commit (absorbed into claude-agent-write)
- [spruyt-labs#1034](https://github.com/anthony-spruyt/spruyt-labs/issues/1034) — Kyverno write rule pre-commit install
