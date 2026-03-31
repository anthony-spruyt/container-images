# claude-agent

Runtime container for ephemeral Claude Code agent pods spawned by n8n.

## Purpose

Minimal runtime image for Claude Code agents running as ephemeral Kubernetes pods. Each pod is spawned by the n8n community node `n8n-nodes-claude-code-cli`, performs a task, and terminates. See [spruyt-labs#823](https://github.com/anthony-spruyt/spruyt-labs/issues/823) for the full design.

## Contents

| Component         | Purpose                                                    |
| ----------------- | ---------------------------------------------------------- |
| Node.js           | Claude Code CLI runtime dependency                         |
| Python 3          | Scripting support for agent tasks                          |
| git               | Repository operations                                      |
| Claude Code CLI   | Core agent runtime                                         |
| Aikido safe-chain | npm supply chain security shims                            |
| .mcp.json         | Baked-in MCP server config (kubectl-mcp, victoriametrics)  |

## Build

```bash
docker build -t claude-agent claude-agent/
```

## Related

- [spruyt-labs#823](https://github.com/anthony-spruyt/spruyt-labs/issues/823) — n8n ephemeral Claude Code agent pods design
