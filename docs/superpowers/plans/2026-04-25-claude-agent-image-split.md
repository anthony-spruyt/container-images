# Claude Agent Image Split Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create three independent container images (`claude-agent-read`, `claude-agent-write`, `claude-agent-spruyt-labs`) alongside the existing `claude-agent` image.

**Architecture:** Each image is built independently from `node:24-slim` with no cross-image dependencies. All share a common core (Claude CLI, safe-chain, git, jq, python3, gh CLI, ripgrep) and add role-specific tools. Existing `claude-agent` remains unchanged until retired after migration.

**Tech Stack:** Docker, Bash, Renovate annotations, GitHub Actions (existing CI auto-detects new image directories)

**Spec:** `docs/superpowers/specs/2026-04-25-claude-agent-image-split-design.md`

______________________________________________________________________

## File Structure

```text
claude-agent-read/
  Dockerfile          # Shared core tools only
  metadata.yaml       # version: "1.0", auto_patch: true
  test.sh             # Verify all core binaries
  .trivyignore        # Copy from claude-agent, adjust as needed
  README.md           # Image purpose and contents

claude-agent-write/
  Dockerfile          # Shared core + pre-commit + Go
  metadata.yaml       # version: "1.0", auto_patch: true
  test.sh             # Verify core + write-specific binaries
  .trivyignore        # Copy from claude-agent, adjust as needed
  README.md           # Image purpose and contents

claude-agent-spruyt-labs/
  Dockerfile          # Shared core + 14 infra CLIs
  metadata.yaml       # version: "1.0", auto_patch: true
  test.sh             # Verify core + all SRE binaries
  .trivyignore        # Copy from claude-agent, adjust as needed
  README.md           # Image purpose and contents
```

______________________________________________________________________

### Task 1: claude-agent-read — Dockerfile

**Files:**

- Create: `claude-agent-read/Dockerfile`

- [ ] **Step 1: Create the Dockerfile**

Base on existing `claude-agent/Dockerfile`, add `gh` CLI and `ripgrep`:

```dockerfile
FROM node:24-slim@sha256:dad1a61d4421f0e72068d9f864c73c1e2a617e2cdb23edc777dbc6fe2c90e720

# Ephemeral agent pod — lifespan managed by n8n spawner
HEALTHCHECK NONE

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
  ca-certificates curl git openssh-client jq python3 python3-pip \
  && rm -rf /var/lib/apt/lists/*

# GitHub CLI
# renovate: depName=cli/cli datasource=github-releases
ARG GH_VERSION="2.73.0"
RUN ARCH="$(dpkg --print-architecture)" \
  && curl -fsSL "https://github.com/cli/cli/releases/download/v${GH_VERSION}/gh_${GH_VERSION}_linux_${ARCH}.deb" -o /tmp/gh.deb \
  && dpkg -i /tmp/gh.deb \
  && rm /tmp/gh.deb

# ripgrep
# renovate: depName=BurntSushi/ripgrep datasource=github-releases
ARG RIPGREP_VERSION="14.1.1"
RUN ARCH="$(dpkg --print-architecture)" \
  && curl -fsSL "https://github.com/BurntSushi/ripgrep/releases/download/${RIPGREP_VERSION}/ripgrep_${RIPGREP_VERSION}-1_${ARCH}.deb" -o /tmp/rg.deb \
  && dpkg -i /tmp/rg.deb \
  && rm /tmp/rg.deb

# Aikido safe-chain (installed globally, then set up for node user)
# renovate: depName=@aikidosec/safe-chain datasource=npm
ARG SAFE_CHAIN_VERSION="1.4.9"
RUN npm install -g "@aikidosec/safe-chain@${SAFE_CHAIN_VERSION}"

# Set up safe-chain shims for node user before any npm/pip calls
USER 1000
RUN safe-chain setup && safe-chain setup-ci
ENV PATH="/home/node/.safe-chain/shims:${PATH}"

# Claude Code CLI (native binary — npm datasource tracks versions)
# renovate: depName=@anthropic-ai/claude-code datasource=npm
ARG CLAUDE_VERSION="2.1.109"
RUN curl -fsSL https://claude.ai/install.sh | bash -s -- "$CLAUDE_VERSION"
ENV PATH="/home/node/.local/bin:${PATH}"

# Working directory
WORKDIR /workspace
```

- [ ] **Step 2: Verify the gh and ripgrep version variables are valid**

Run:

```bash
curl -sI "https://github.com/cli/cli/releases/download/v2.73.0/gh_2.73.0_linux_amd64.deb" | head -1
curl -sI "https://github.com/BurntSushi/ripgrep/releases/download/14.1.1/ripgrep_14.1.1-1_amd64.deb" | head -1
```

Expected: `HTTP/2 302` (redirect to download) for both.

- [ ] **Step 3: Commit**

```bash
git add claude-agent-read/Dockerfile
git commit -m "feat(claude-agent-read): add Dockerfile with shared core + gh + ripgrep"
```

______________________________________________________________________

### Task 2: claude-agent-read — metadata, test, trivyignore, README

**Files:**

- Create: `claude-agent-read/metadata.yaml`

- Create: `claude-agent-read/test.sh`

- Create: `claude-agent-read/.trivyignore`

- Create: `claude-agent-read/README.md`

- [ ] **Step 1: Create metadata.yaml**

```yaml
---
version: "1.0"
auto_patch: true
```

- [ ] **Step 2: Create test.sh**

```bash
#!/bin/bash
set -euo pipefail

IMAGE="${1:?Usage: test.sh <image-ref>}"

echo "Testing claude-agent-read image..."

docker run --rm "$IMAGE" bash -c '
set -euo pipefail

for bin in claude node python3 git npm jq gh rg; do
  if ! command -v "$bin" &>/dev/null; then
    echo "FAIL: $bin not found"
    exit 1
  fi
  echo "OK: $bin found at $(which "$bin")"
done

claude --version
safe-chain --version
gh --version
rg --version

echo "All tests passed."
'
```

Make executable: `chmod +x claude-agent-read/test.sh`

- [ ] **Step 3: Create .trivyignore**

Copy from `claude-agent/.trivyignore` — same base image and shared tools produce the same vulnerabilities:

```bash
cp claude-agent/.trivyignore claude-agent-read/.trivyignore
```

- [ ] **Step 4: Create README.md**

```markdown
# claude-agent-read

Read-only runtime container for Claude Code agent pods spawned by n8n.

## Purpose

Minimal runtime image for read-only Claude Code agents running as Kubernetes pods. Used for PR review, Renovate PR triage, and issue refinement. Each pod is spawned by n8n, performs a task, and terminates.

## Contents

| Component       | Purpose                       |
| --------------- | ----------------------------- |
| Node.js         | Claude Code CLI dependency    |
| Python 3        | Scripting support             |
| git             | Repository operations         |
| jq              | JSON processing               |
| Claude Code CLI | Core agent runtime            |
| Aikido safe-chain | npm supply chain security   |
| gh CLI          | GitHub API operations         |
| ripgrep         | Fast recursive code search    |

## Build

\`\`\`bash
docker build -t claude-agent-read claude-agent-read/
\`\`\`
```

- [ ] **Step 5: Commit**

```bash
git add claude-agent-read/metadata.yaml claude-agent-read/test.sh claude-agent-read/.trivyignore claude-agent-read/README.md
git commit -m "feat(claude-agent-read): add metadata, test, trivyignore, and README"
```

______________________________________________________________________

### Task 3: claude-agent-write — Dockerfile

**Files:**

- Create: `claude-agent-write/Dockerfile`

- [ ] **Step 1: Create the Dockerfile**

Same shared core as read, plus pre-commit and Go:

```dockerfile
FROM node:24-slim@sha256:dad1a61d4421f0e72068d9f864c73c1e2a617e2cdb23edc777dbc6fe2c90e720

# Ephemeral agent pod — lifespan managed by n8n spawner
HEALTHCHECK NONE

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
  ca-certificates curl git openssh-client jq python3 python3-pip \
  && rm -rf /var/lib/apt/lists/*

# GitHub CLI
# renovate: depName=cli/cli datasource=github-releases
ARG GH_VERSION="2.73.0"
RUN ARCH="$(dpkg --print-architecture)" \
  && curl -fsSL "https://github.com/cli/cli/releases/download/v${GH_VERSION}/gh_${GH_VERSION}_linux_${ARCH}.deb" -o /tmp/gh.deb \
  && dpkg -i /tmp/gh.deb \
  && rm /tmp/gh.deb

# ripgrep
# renovate: depName=BurntSushi/ripgrep datasource=github-releases
ARG RIPGREP_VERSION="14.1.1"
RUN ARCH="$(dpkg --print-architecture)" \
  && curl -fsSL "https://github.com/BurntSushi/ripgrep/releases/download/${RIPGREP_VERSION}/ripgrep_${RIPGREP_VERSION}-1_${ARCH}.deb" -o /tmp/rg.deb \
  && dpkg -i /tmp/rg.deb \
  && rm /tmp/rg.deb

# Go
# renovate: depName=golang datasource=docker
ARG GO_VERSION="1.24.4"
RUN ARCH="$(dpkg --print-architecture)" \
  && curl -fsSL "https://go.dev/dl/go${GO_VERSION}.linux-${ARCH}.tar.gz" | tar -C /usr/local -xz
ENV PATH="/usr/local/go/bin:${PATH}"

# Aikido safe-chain (installed globally, then set up for node user)
# renovate: depName=@aikidosec/safe-chain datasource=npm
ARG SAFE_CHAIN_VERSION="1.4.9"
RUN npm install -g "@aikidosec/safe-chain@${SAFE_CHAIN_VERSION}"

# Set up safe-chain shims for node user before any npm/pip calls
USER 1000
RUN safe-chain setup && safe-chain setup-ci
ENV PATH="/home/node/.safe-chain/shims:${PATH}"

# pre-commit
RUN pip install --break-system-packages pre-commit
ENV PATH="/home/node/.local/bin:${PATH}"

# Claude Code CLI (native binary — npm datasource tracks versions)
# renovate: depName=@anthropic-ai/claude-code datasource=npm
ARG CLAUDE_VERSION="2.1.109"
RUN curl -fsSL https://claude.ai/install.sh | bash -s -- "$CLAUDE_VERSION"

# Working directory
WORKDIR /workspace
```

- [ ] **Step 2: Commit**

```bash
git add claude-agent-write/Dockerfile
git commit -m "feat(claude-agent-write): add Dockerfile with shared core + pre-commit + Go"
```

______________________________________________________________________

### Task 4: claude-agent-write — metadata, test, trivyignore, README

**Files:**

- Create: `claude-agent-write/metadata.yaml`

- Create: `claude-agent-write/test.sh`

- Create: `claude-agent-write/.trivyignore`

- Create: `claude-agent-write/README.md`

- [ ] **Step 1: Create metadata.yaml**

```yaml
---
version: "1.0"
auto_patch: true
```

- [ ] **Step 2: Create test.sh**

```bash
#!/bin/bash
set -euo pipefail

IMAGE="${1:?Usage: test.sh <image-ref>}"

echo "Testing claude-agent-write image..."

docker run --rm "$IMAGE" bash -c '
set -euo pipefail

for bin in claude node python3 git npm jq gh rg go pre-commit; do
  if ! command -v "$bin" &>/dev/null; then
    echo "FAIL: $bin not found"
    exit 1
  fi
  echo "OK: $bin found at $(which "$bin")"
done

claude --version
safe-chain --version
gh --version
rg --version
go version
pre-commit --version

echo "All tests passed."
'
```

Make executable: `chmod +x claude-agent-write/test.sh`

- [ ] **Step 3: Create .trivyignore**

```bash
cp claude-agent/.trivyignore claude-agent-write/.trivyignore
```

- [ ] **Step 4: Create README.md**

```markdown
# claude-agent-write

Write runtime container for Claude Code agent pods spawned by n8n.

## Purpose

Runtime image for Claude Code agents that implement issues, fix PRs, and commit code. Includes pre-commit for hook enforcement and Go for Go-based repos. Each pod is spawned by n8n, performs a task, and terminates.

## Contents

| Component       | Purpose                       |
| --------------- | ----------------------------- |
| Node.js         | Claude Code CLI dependency    |
| Python 3        | Scripting + pre-commit        |
| git             | Repository operations         |
| jq              | JSON processing               |
| Claude Code CLI | Core agent runtime            |
| Aikido safe-chain | npm supply chain security   |
| gh CLI          | GitHub API operations         |
| ripgrep         | Fast recursive code search    |
| pre-commit      | Git hook framework            |
| Go              | Go language support           |

## Build

\`\`\`bash
docker build -t claude-agent-write claude-agent-write/
\`\`\`
```

- [ ] **Step 5: Commit**

```bash
git add claude-agent-write/metadata.yaml claude-agent-write/test.sh claude-agent-write/.trivyignore claude-agent-write/README.md
git commit -m "feat(claude-agent-write): add metadata, test, trivyignore, and README"
```

______________________________________________________________________

### Task 5: claude-agent-spruyt-labs — Dockerfile

**Files:**

- Create: `claude-agent-spruyt-labs/Dockerfile`

- [ ] **Step 1: Create the Dockerfile**

Same shared core as read, plus all 14 SRE tools. All versions pinned with Renovate annotations. Tools installed as root before switching to node user:

```dockerfile
FROM node:24-slim@sha256:dad1a61d4421f0e72068d9f864c73c1e2a617e2cdb23edc777dbc6fe2c90e720

# Ephemeral agent pod — lifespan managed by n8n spawner
HEALTHCHECK NONE

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
  ca-certificates curl git openssh-client jq python3 python3-pip \
  && rm -rf /var/lib/apt/lists/*

# GitHub CLI
# renovate: depName=cli/cli datasource=github-releases
ARG GH_VERSION="2.73.0"
RUN ARCH="$(dpkg --print-architecture)" \
  && curl -fsSL "https://github.com/cli/cli/releases/download/v${GH_VERSION}/gh_${GH_VERSION}_linux_${ARCH}.deb" -o /tmp/gh.deb \
  && dpkg -i /tmp/gh.deb \
  && rm /tmp/gh.deb

# ripgrep
# renovate: depName=BurntSushi/ripgrep datasource=github-releases
ARG RIPGREP_VERSION="14.1.1"
RUN ARCH="$(dpkg --print-architecture)" \
  && curl -fsSL "https://github.com/BurntSushi/ripgrep/releases/download/${RIPGREP_VERSION}/ripgrep_${RIPGREP_VERSION}-1_${ARCH}.deb" -o /tmp/rg.deb \
  && dpkg -i /tmp/rg.deb \
  && rm /tmp/rg.deb

# kubectl
# renovate: depName=kubernetes/kubernetes datasource=github-releases
ARG KUBECTL_VERSION="v1.35.4"
RUN ARCH="$(dpkg --print-architecture)" \
  && curl -fsSL "https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/${ARCH}/kubectl" -o /usr/local/bin/kubectl \
  && chmod +x /usr/local/bin/kubectl

# kustomize
# renovate: depName=kubernetes-sigs/kustomize datasource=github-releases versioning=regex:^kustomize/v(?<major>\d+)\.(?<minor>\d+)\.(?<patch>\d+)$
ARG KUSTOMIZE_VERSION="v5.8.0"
RUN ARCH="$(dpkg --print-architecture)" \
  && curl -fsSL "https://github.com/kubernetes-sigs/kustomize/releases/download/kustomize%2F${KUSTOMIZE_VERSION}/kustomize_${KUSTOMIZE_VERSION}_linux_${ARCH}.tar.gz" \
  | tar -xz -C /usr/local/bin

# helm
# renovate: depName=helm/helm datasource=github-releases
ARG HELM_VERSION="v4.1.4"
RUN ARCH="$(dpkg --print-architecture)" \
  && curl -fsSL "https://get.helm.sh/helm-${HELM_VERSION}-linux-${ARCH}.tar.gz" \
  | tar -xz -C /tmp \
  && mv "/tmp/linux-${ARCH}/helm" /usr/local/bin/helm \
  && rm -rf /tmp/linux-*

# helmfile
# renovate: depName=helmfile/helmfile datasource=github-releases
ARG HELMFILE_VERSION="v1.4.4"
RUN ARCH="$(dpkg --print-architecture)" \
  && HELMFILE_VERSION_NUM="${HELMFILE_VERSION#v}" \
  && curl -fsSL "https://github.com/helmfile/helmfile/releases/download/${HELMFILE_VERSION}/helmfile_${HELMFILE_VERSION_NUM}_linux_${ARCH}.tar.gz" \
  | tar -xz -C /usr/local/bin helmfile

# cilium
# renovate: depName=cilium/cilium-cli datasource=github-releases
ARG CILIUM_VERSION="v0.19.2"
RUN ARCH="$(dpkg --print-architecture)" \
  && curl -fsSL "https://github.com/cilium/cilium-cli/releases/download/${CILIUM_VERSION}/cilium-linux-${ARCH}.tar.gz" \
  | tar -xz -C /usr/local/bin

# hubble
# renovate: depName=cilium/hubble datasource=github-releases
ARG HUBBLE_VERSION="v1.18.6"
RUN ARCH="$(dpkg --print-architecture)" \
  && curl -fsSL "https://github.com/cilium/hubble/releases/download/${HUBBLE_VERSION}/hubble-linux-${ARCH}.tar.gz" \
  | tar -xz -C /usr/local/bin

# talosctl
# renovate: depName=siderolabs/talos datasource=github-releases
ARG TALOSCTL_VERSION="v1.10.3"
RUN ARCH="$(dpkg --print-architecture)" \
  && curl -fsSL "https://github.com/siderolabs/talos/releases/download/${TALOSCTL_VERSION}/talosctl-linux-${ARCH}" -o /usr/local/bin/talosctl \
  && chmod +x /usr/local/bin/talosctl

# talhelper
# renovate: depName=budimanjojo/talhelper datasource=github-releases
ARG TALHELPER_VERSION="v3.0.32"
RUN ARCH="$(dpkg --print-architecture)" \
  && curl -fsSL "https://github.com/budimanjojo/talhelper/releases/download/${TALHELPER_VERSION}/talhelper_linux_${ARCH}.tar.gz" \
  | tar -xz -C /usr/local/bin talhelper

# flux
# renovate: depName=fluxcd/flux2 datasource=github-releases
ARG FLUX_VERSION="v2.6.1"
RUN ARCH="$(dpkg --print-architecture)" \
  && curl -fsSL "https://github.com/fluxcd/flux2/releases/download/${FLUX_VERSION}/flux_${FLUX_VERSION#v}_linux_${ARCH}.tar.gz" \
  | tar -xz -C /usr/local/bin

# velero
# renovate: depName=vmware-tanzu/velero datasource=github-releases
ARG VELERO_VERSION="v1.18.0"
RUN ARCH="$(dpkg --print-architecture)" \
  && curl -fsSL "https://github.com/vmware-tanzu/velero/releases/download/${VELERO_VERSION}/velero-${VELERO_VERSION}-linux-${ARCH}.tar.gz" \
  | tar -xz -C /tmp \
  && mv "/tmp/velero-${VELERO_VERSION}-linux-${ARCH}/velero" /usr/local/bin/velero \
  && rm -rf /tmp/velero-*

# cnpg kubectl plugin
# renovate: depName=cloudnative-pg/cloudnative-pg datasource=github-releases
ARG CNPG_VERSION="v1.26.3"
RUN ARCH="$(uname -m)" \
  && CNPG_VERSION_NUM="${CNPG_VERSION#v}" \
  && curl -fsSL "https://github.com/cloudnative-pg/cloudnative-pg/releases/download/${CNPG_VERSION}/kubectl-cnpg_${CNPG_VERSION_NUM}_linux_${ARCH}.tar.gz" \
  | tar -xz -C /usr/local/bin kubectl-cnpg

# falcoctl
# renovate: depName=falcosecurity/falcoctl datasource=github-releases
ARG FALCOCTL_VERSION="v0.12.2"
RUN ARCH="$(dpkg --print-architecture)" \
  && FALCOCTL_VERSION_NUM="${FALCOCTL_VERSION#v}" \
  && curl -fsSL "https://github.com/falcosecurity/falcoctl/releases/download/${FALCOCTL_VERSION}/falcoctl_${FALCOCTL_VERSION_NUM}_linux_${ARCH}.tar.gz" \
  | tar -xz -C /usr/local/bin falcoctl

# Aikido safe-chain (installed globally, then set up for node user)
# renovate: depName=@aikidosec/safe-chain datasource=npm
ARG SAFE_CHAIN_VERSION="1.4.9"
RUN npm install -g "@aikidosec/safe-chain@${SAFE_CHAIN_VERSION}"

# Set up safe-chain shims for node user before any npm/pip calls
USER 1000
RUN safe-chain setup && safe-chain setup-ci
ENV PATH="/home/node/.safe-chain/shims:${PATH}"

# Claude Code CLI (native binary — npm datasource tracks versions)
# renovate: depName=@anthropic-ai/claude-code datasource=npm
ARG CLAUDE_VERSION="2.1.109"
RUN curl -fsSL https://claude.ai/install.sh | bash -s -- "$CLAUDE_VERSION"
ENV PATH="/home/node/.local/bin:${PATH}"

# Helm plugins (installed as node user — helm stores plugins in $HOME)
# renovate: depName=databus23/helm-diff datasource=github-releases
ARG HELM_DIFF_VERSION="v4.1.5"
RUN helm plugin install https://github.com/databus23/helm-diff --version "${HELM_DIFF_VERSION}"

# renovate: depName=knechtionscoding/helm-schema-gen datasource=github-releases
ARG HELM_SCHEMA_GEN_VERSION="v0.0.6"
RUN helm plugin install https://github.com/knechtionscoding/helm-schema-gen --version "${HELM_SCHEMA_GEN_VERSION}"

# Working directory
WORKDIR /workspace
```

Note: cnpg uses `uname -m` (returns `x86_64`) instead of `dpkg --print-architecture` (returns `amd64`) because cnpg release filenames use `x86_64`.

- [ ] **Step 2: Verify pinned versions exist for currently-unpinned tools**

Check that the release tags exist for talosctl, talhelper, flux, and cnpg:

```bash
for repo_tag in "siderolabs/talos:v1.10.3" "budimanjojo/talhelper:v3.0.32" "fluxcd/flux2:v2.6.1" "cloudnative-pg/cloudnative-pg:v1.26.3"; do
  repo="${repo_tag%%:*}"
  tag="${repo_tag##*:}"
  status=$(curl -sI "https://github.com/${repo}/releases/tag/${tag}" | head -1)
  echo "${repo}@${tag}: ${status}"
done
```

Expected: `HTTP/2 200` for all. If any 404, check GitHub for latest release and update the ARG in the Dockerfile.

- [ ] **Step 3: Commit**

```bash
git add claude-agent-spruyt-labs/Dockerfile
git commit -m "feat(claude-agent-spruyt-labs): add Dockerfile with shared core + 14 infra CLIs"
```

______________________________________________________________________

### Task 6: claude-agent-spruyt-labs — metadata, test, trivyignore, README

**Files:**

- Create: `claude-agent-spruyt-labs/metadata.yaml`

- Create: `claude-agent-spruyt-labs/test.sh`

- Create: `claude-agent-spruyt-labs/.trivyignore`

- Create: `claude-agent-spruyt-labs/README.md`

- [ ] **Step 1: Create metadata.yaml**

```yaml
---
version: "1.0"
auto_patch: true
```

- [ ] **Step 2: Create test.sh**

```bash
#!/bin/bash
set -euo pipefail

IMAGE="${1:?Usage: test.sh <image-ref>}"

echo "Testing claude-agent-spruyt-labs image..."

docker run --rm "$IMAGE" bash -c '
set -euo pipefail

for bin in claude node python3 git npm jq gh rg \
           kubectl kustomize helm helmfile cilium hubble \
           talosctl talhelper flux velero kubectl-cnpg falcoctl; do
  if ! command -v "$bin" &>/dev/null; then
    echo "FAIL: $bin not found"
    exit 1
  fi
  echo "OK: $bin found at $(which "$bin")"
done

claude --version
safe-chain --version
gh --version
rg --version
kubectl version --client
helm version
flux --version

# Verify helm plugins
helm plugin list | grep -q diff || { echo "FAIL: helm-diff plugin not found"; exit 1; }
echo "OK: helm-diff plugin installed"
helm plugin list | grep -q schema-gen || { echo "FAIL: helm-schema-gen plugin not found"; exit 1; }
echo "OK: helm-schema-gen plugin installed"

echo "All tests passed."
'
```

Make executable: `chmod +x claude-agent-spruyt-labs/test.sh`

- [ ] **Step 3: Create .trivyignore**

```bash
cp claude-agent/.trivyignore claude-agent-spruyt-labs/.trivyignore
```

- [ ] **Step 4: Create README.md**

```markdown
# claude-agent-spruyt-labs

SRE investigation container for Claude Code agent pods spawned by n8n.

## Purpose

Runtime image for Claude Code agents that investigate Kubernetes cluster state in spruyt-labs. Investigation only — no write operations. Each pod is spawned by n8n, performs a task, and terminates.

## Contents

| Component       | Purpose                       |
| --------------- | ----------------------------- |
| Node.js         | Claude Code CLI dependency    |
| Python 3        | Scripting support             |
| git             | Repository operations         |
| jq              | JSON processing               |
| Claude Code CLI | Core agent runtime            |
| Aikido safe-chain | npm supply chain security   |
| gh CLI          | GitHub API operations         |
| ripgrep         | Fast recursive code search    |
| kubectl         | Kubernetes API operations     |
| kustomize       | Kustomize manifests           |
| helm            | Chart management              |
| helmfile        | Declarative helm management   |
| helm-diff       | Helm diff plugin              |
| helm-schema-gen | Helm schema generation plugin |
| cilium          | Cilium CNI operations         |
| hubble          | Network observability         |
| talosctl        | Talos Linux node management   |
| talhelper       | Talos configuration helper    |
| flux            | GitOps toolkit                |
| velero          | Backup inspection             |
| cnpg plugin     | CloudNativePG operations      |
| falcoctl        | Falco security runtime        |

## Build

\`\`\`bash
docker build -t claude-agent-spruyt-labs claude-agent-spruyt-labs/
\`\`\`
```

- [ ] **Step 5: Commit**

```bash
git add claude-agent-spruyt-labs/metadata.yaml claude-agent-spruyt-labs/test.sh claude-agent-spruyt-labs/.trivyignore claude-agent-spruyt-labs/README.md
git commit -m "feat(claude-agent-spruyt-labs): add metadata, test, trivyignore, and README"
```

______________________________________________________________________

### Task 7: Build verification

**Files:** None (verification only)

- [ ] **Step 1: Build claude-agent-read**

```bash
docker build -t claude-agent-read claude-agent-read/
```

Expected: successful build, no errors.

- [ ] **Step 2: Test claude-agent-read**

```bash
claude-agent-read/test.sh claude-agent-read
```

Expected: all binaries found, versions printed, "All tests passed."

- [ ] **Step 3: Build claude-agent-write**

```bash
docker build -t claude-agent-write claude-agent-write/
```

Expected: successful build, no errors.

- [ ] **Step 4: Test claude-agent-write**

```bash
claude-agent-write/test.sh claude-agent-write
```

Expected: all binaries found, versions printed, "All tests passed."

- [ ] **Step 5: Build claude-agent-spruyt-labs**

```bash
docker build -t claude-agent-spruyt-labs claude-agent-spruyt-labs/
```

Expected: successful build, no errors.

- [ ] **Step 6: Test claude-agent-spruyt-labs**

```bash
claude-agent-spruyt-labs/test.sh claude-agent-spruyt-labs
```

Expected: all binaries found, versions printed, "All tests passed."

- [ ] **Step 7: Fix any build or test failures, then commit fixes**

If any step failed, debug, fix the relevant Dockerfile or test.sh, and commit:

```bash
git add <fixed-files>
git commit -m "fix(<image-name>): <description of fix>"
```

______________________________________________________________________

### Task 8: Push branch and create PR

**Files:** None

- [ ] **Step 1: Push branch**

```bash
git push -u origin feat/claude-agent-image-split
```

- [ ] **Step 2: Create PR**

```bash
gh pr create --title "feat(claude-agent): add read, write, and SRE agent images" --body "$(cat <<'PREOF'
## Summary

- Add `claude-agent-read` — shared core (Claude CLI, safe-chain, git, jq, python3, gh CLI, ripgrep) for PR review, Renovate triage, issue refinement
- Add `claude-agent-write` — shared core + pre-commit + Go for implementing issues and fixing PRs
- Add `claude-agent-spruyt-labs` — shared core + 14 k8s/infra CLIs for spruyt-labs cluster investigation

All three images are independent (built from `node:24-slim`, no cross-dependencies). Existing `claude-agent` image is unchanged and will be retired after migration.

Closes #492

## Test plan

- [ ] CI builds all three images successfully
- [ ] CI test.sh passes for each image
- [ ] Trivy scan completes without new critical/high findings
- [ ] Verify all Renovate annotations are picked up (check Renovate dashboard after merge)

🤖 Generated with [Claude Code](https://claude.com/claude-code)
PREOF
)"
```
