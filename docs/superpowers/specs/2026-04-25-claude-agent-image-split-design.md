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
node:24-slim ──┬── claude-agent-read    (read)
               ├── claude-agent-write   (write)
               └── claude-agent-spruyt-labs     (investigate)
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

### claude-agent-read

**Purpose:** Read-only agent for PR review, Renovate triage, issue refinement.

**Contents:** Shared core only. No additional tools.

**Directory:** `claude-agent-read/` (new, alongside existing `claude-agent/`)

### claude-agent-write

**Purpose:** Write agent for implementing issues, fixing PRs. Commits and pushes code with pre-commit hook enforcement.

**Contents:** Shared core plus:

| Tool       | Purpose                                |
| ---------- | -------------------------------------- |
| pre-commit | Git hook framework for code quality    |
| Go         | Go language support for Go-based repos |

**Directory:** `claude-agent-write/` (new)

### claude-agent-spruyt-labs

**Purpose:** Investigation-only agent for spruyt-labs k8s cluster. No write operations.

**Contents:** Shared core plus:

| Tool                   | Version | Source                             | Renovate                              |
| ---------------------- | ------- | ---------------------------------- | ------------------------------------- |
| kubectl                | v1.35.4 | `kubernetes/kubernetes`            | `github-releases`                     |
| kustomize              | v5.8.0  | `kubernetes-sigs/kustomize`        | `github-releases` (custom versioning) |
| helm                   | v4.1.4  | `helm/helm`                        | `github-releases`                     |
| helmfile               | v1.4.4  | `helmfile/helmfile`                | `github-releases`                     |
| helm-diff plugin       | pinned  | `databus23/helm-diff`              | `github-releases`                     |
| helm-schema-gen plugin | pinned  | `knechtionscoding/helm-schema-gen` | `github-releases`                     |
| cilium                 | v0.19.2 | `cilium/cilium-cli`                | `github-releases`                     |
| hubble                 | v1.18.6 | `cilium/hubble`                    | `github-releases`                     |
| talosctl               | pinned  | `siderolabs/talos`                 | `github-releases`                     |
| talhelper              | pinned  | `budimanjojo/talhelper`            | `github-releases`                     |
| flux                   | pinned  | `fluxcd/flux2`                     | `github-releases`                     |
| velero                 | v1.18.0 | `vmware-tanzu/velero`              | `github-releases`                     |
| cnpg plugin            | pinned  | `cloudnative-pg/cloudnative-pg`    | `github-releases`                     |
| falcoctl               | v0.12.2 | `falcosecurity/falcoctl`           | `github-releases`                     |

Note: tools marked "pinned" are currently installed via latest-fetching scripts in spruyt-labs. Dockerfile will pin explicit versions with Renovate annotations for reproducibility.

**Directory:** `claude-agent-spruyt-labs/` (new)

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

### claude-agent-read, claude-agent-write, and claude-agent-spruyt-labs

All start at:

```yaml
version: "1.0"
auto_patch: true
```

The existing `claude-agent` image remains unchanged and will be retired after migration to the new images.

## Integration

- CLAUDE.md and `.claude/` skills synced to all repos via xfg/repo-operator — agent behavior and standards are repo-driven, not image-driven
- n8n workflows select image based on task type (read/write/sre)
- Kyverno policies in spruyt-labs configure pod injection per agent type

## Related Issues

- [#492](https://github.com/anthony-spruyt/container-images/issues/492) — add pre-commit (absorbed into claude-agent-write)
- [spruyt-labs#1034](https://github.com/anthony-spruyt/spruyt-labs/issues/1034) — Kyverno write rule pre-commit install
