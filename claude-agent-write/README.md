# claude-agent-write

Write runtime container for Claude Code agent pods spawned by n8n.

## Purpose

Runtime image for Claude Code agents that implement issues, fix PRs, and commit code. Includes pre-commit for hook enforcement and Go for Go-based repos. Each pod is spawned by n8n, performs a task, and terminates.

## Base image

Builds on [`claude-agent-read`](../claude-agent-read) (see its docs for the full inherited toolset, e.g. Node.js), adding only the write-specific delta.

## Contents (added on top of claude-agent-read)

| Component  | Purpose             |
| ---------- | ------------------- |
| Go         | Go language support |
| pre-commit | Git hook framework  |

## Build

`claude-agent-write` is `FROM ghcr.io/anthony-spruyt/claude-agent-read`, so a published `claude-agent-read` image is required.

```bash
docker build -t claude-agent-write claude-agent-write/
```
