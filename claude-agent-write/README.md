# claude-agent-write

Write runtime container for Claude Code agent pods spawned by n8n.

## Purpose

Runtime image for Claude Code agents that implement issues, fix PRs, and commit code. Includes pre-commit for hook enforcement and Go for Go-based repos. Each pod is spawned by n8n, performs a task, and terminates.

## Contents

| Component         | Purpose                    |
| ----------------- | -------------------------- |
| Node.js           | Claude Code CLI dependency |
| Python 3          | Scripting + pre-commit     |
| git               | Repository operations      |
| jq                | JSON processing            |
| Claude Code CLI   | Core agent runtime         |
| Aikido safe-chain | npm supply chain security  |
| gh CLI            | GitHub API operations      |
| ripgrep           | Fast recursive code search |
| pre-commit        | Git hook framework         |
| Go                | Go language support        |

## Build

```bash
docker build -t claude-agent-write claude-agent-write/
```
