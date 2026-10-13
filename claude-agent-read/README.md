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

## Runtime configuration

- `/etc/claude-code/managed-settings.json`: agent policy. `bypassPermissions` default mode, `/workspace/pr` as an extra directory, `Read(//proc/**)` denied, updates and nonessential traffic off.
- `claude-plugins-bootstrap <workspace-dir>`: init-container script that installs the plugins named in the user, project and local Claude Code settings of that checkout, at user scope into `$HOME/.claude`. Plugin and marketplace values that start with `-` or `/` are skipped with a warning.
- `CLAUDE_PLUGINS_STRICT=1`: pod mode for `claude-plugins-bootstrap`. Any failure (missing `claude` or `jq`, invalid settings JSON, a marketplace add or plugin install that fails, a skipped value) exits non-zero, and only the user and project settings are read, matching `--setting-sources user,project`; `.claude/settings.local.json` is ignored. Unset, failures only warn and the script exits 0.
- `ap-mcp-headers [server]`: MCP `headersHelper` that prints the auth headers of `agentplatform` or `litellm` (the server named by `CLAUDE_CODE_MCP_SERVER_NAME`) as JSON, from `AP_MCP_SESSION_KEY` or `AP_LITELLM_API_KEY`.

`claude-plugins-bootstrap` is a copy of `devcontainer-common/assets/claude-plugins-bootstrap.sh`; `test.sh` fails when they differ.

## Build

```bash
docker build -t claude-agent-read claude-agent-read/
```
