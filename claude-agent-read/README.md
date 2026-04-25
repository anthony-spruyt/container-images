# claude-agent-read

Read-only runtime container for Claude Code agent pods spawned by n8n.

## Purpose

Minimal runtime image for read-only Claude Code agents running as Kubernetes pods. Used for PR review, Renovate PR triage, and issue refinement. Each pod is spawned by n8n, performs a task, and terminates.

## Contents

| Component         | Purpose                    |
| ----------------- | -------------------------- |
| Node.js           | Claude Code CLI dependency |
| Python 3          | Scripting support          |
| git               | Repository operations      |
| jq                | JSON processing            |
| Claude Code CLI   | Core agent runtime         |
| Aikido safe-chain | npm supply chain security  |
| gh CLI            | GitHub API operations      |
| ripgrep           | Fast recursive code search |

## Build

```bash
docker build -t claude-agent-read claude-agent-read/
```
