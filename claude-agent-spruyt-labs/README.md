# claude-agent-spruyt-labs

Full read-write runtime container for Claude Code agent pods spawned by n8n to operate on the spruyt-labs cluster repo.

## Purpose

Runtime image for Claude Code agents working on the spruyt-labs GitOps homelab. These agents both **investigate** cluster state and **make changes** — implement issues, fix and open PRs, commit code, run pre-commit hooks, and operate the Kubernetes/GitOps toolchain (kubectl, helm, flux, talosctl, etc.). Each pod is spawned by n8n, performs a task, and terminates.

It is not investigation-only: it inherits the full write toolchain (Go, pre-commit) from `claude-agent-write` and adds the SRE/GitOps CLIs on top.

## Base image

Built on [`claude-agent-write`](../claude-agent-write) (itself `FROM` [`claude-agent-read`](../claude-agent-read)). The Ubuntu base, Node.js, Python 3, git, jq, gh, ripgrep, safe-chain, agentmemory, Claude Code CLI, Go, and pre-commit all come from that chain. This image adds only the cluster tooling delta.

## Contents (added on top of claude-agent-write)

Cluster/GitOps tooling such as kubectl, helm, and flux. See the [Dockerfile](./Dockerfile) for the complete installed list.

## Build

`claude-agent-spruyt-labs` is `FROM ghcr.io/anthony-spruyt/claude-agent-write`, so a published `claude-agent-write` image is required.

```bash
docker build -t claude-agent-spruyt-labs claude-agent-spruyt-labs/
```
