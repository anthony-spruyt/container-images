# claude-agent

Runtime container for ephemeral Claude Code agent pods spawned by n8n.

## Purpose

This image provides a minimal, secure runtime for Claude Code agents running as ephemeral Kubernetes pods. Each pod is spawned by n8n, performs a task using the Claude Code CLI, and terminates. See [spruyt-labs#823](https://github.com/anthony-spruyt/spruyt-labs/issues/823) for the full design.

## Contents

| Component | Purpose |
|-----------|---------|
| Node.js 20 | Claude Code CLI runtime |
| Python 3 | Scripting support for agent tasks |
| git | Repository operations |
| kubectl | Bootstrap only — removed before agent starts |
| Claude Code CLI | Core agent runtime |
| Aikido safe-chain | npm supply chain security shims |

## Entrypoint

On startup, `entrypoint.sh`:

1. Reads the pod's service account namespace from the projected token path
2. Fetches `claude-credentials` secret to obtain `CLAUDE_CODE_OAUTH_TOKEN`
3. Fetches `claude-mcp-config` ConfigMap and writes `/workspace/.mcp.json`
4. Fetches `claude-settings` ConfigMap and writes `~/.claude/settings.json`
5. Removes `kubectl` — the agent must use MCP tools for all Kubernetes operations
6. Execs `claude` with any arguments passed to the container

## Build

```bash
docker build -t claude-agent claude-agent/
```

## Related

- [spruyt-labs#823](https://github.com/anthony-spruyt/spruyt-labs/issues/823) — n8n ephemeral Claude Code agent pods design
