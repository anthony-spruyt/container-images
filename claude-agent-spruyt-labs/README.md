# claude-agent-spruyt-labs

SRE investigation container for Claude Code agent pods spawned by n8n.

## Purpose

Runtime image for Claude Code agents that investigate Kubernetes cluster state in spruyt-labs. Investigation only — no write operations. Each pod is spawned by n8n, performs a task, and terminates.

## Contents

| Component         | Purpose                       |
| ----------------- | ----------------------------- |
| Node.js           | Claude Code CLI dependency    |
| Python 3          | Scripting support             |
| git               | Repository operations         |
| jq                | JSON processing               |
| Claude Code CLI   | Core agent runtime            |
| Aikido safe-chain | npm supply chain security     |
| gh CLI            | GitHub API operations         |
| ripgrep           | Fast recursive code search    |
| kubectl           | Kubernetes API operations     |
| kustomize         | Kustomize manifests           |
| helm              | Chart management              |
| helmfile          | Declarative helm management   |
| helm-diff         | Helm diff plugin              |
| helm-schema-gen   | Helm schema generation plugin |
| cilium            | Cilium CNI operations         |
| hubble            | Network observability         |
| talosctl          | Talos Linux node management   |
| flux              | GitOps toolkit                |
| velero            | Backup inspection             |
| cnpg plugin       | CloudNativePG operations      |
| falcoctl          | Falco security runtime        |

## Build

```bash
docker build -t claude-agent-spruyt-labs claude-agent-spruyt-labs/
```
