# Development Environment

This repository uses a VS Code devcontainer for a consistent development experience.

## Prerequisites

- [VS Code](https://code.visualstudio.com/) with the [Dev Containers extension](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers)
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) or Docker Engine
- SSH agent running with keys loaded (see [SSH Agent Setup](#ssh-agent-setup))
- GitHub token in `~/.secrets/.env` (for GitHub CLI operations)

## Host Directory Structure

The devcontainer expects these directories on your host machine:

```text
~/.secrets/
├── .env                    # Environment variables (loaded via --env-file)
└── ...                     # Other secrets as needed

~/.claude/                  # Claude Code settings and memory
```

Create the required structure:

```bash
mkdir -p ~/.claude
touch ~/.secrets/.env
```

The `.env` file sets environment variables and paths to secrets:

```bash
GH_TOKEN=<github-token>
CONTEXT7_API_KEY=<context7-key>
```

## SSH Agent Setup

The devcontainer uses SSH agent forwarding via socket mount. Your private keys stay on
the host and are never copied into the container.

The devcontainer also mounts your `~/.gitconfig` (read-only) for git identity and commit signing. To enable SSH commit signing on your host:

```bash
git config --global gpg.format ssh
git config --global user.signingkey "$(cat ~/.ssh/id_ed25519.pub)"
git config --global commit.gpgsign true
```

**Linux/WSL:**

```bash
eval "$(ssh-agent -s)"
ssh-add ~/.ssh/id_ed25519  # or your key path
```

For passphrase-protected keys, use `keychain` to persist across sessions:

```bash
# Install: sudo apt install keychain
# Add to ~/.bashrc or ~/.zshrc:
eval "$(keychain --eval --agents ssh id_ed25519)"

# Create stable symlink for devcontainer (required for reboot persistence)
export SSH_AUTH_SOCK_LINK="$HOME/.ssh/agent.sock"
if [ -S "$SSH_AUTH_SOCK" ]; then
  ln -sf "$SSH_AUTH_SOCK" "$SSH_AUTH_SOCK_LINK"
  export SSH_AUTH_SOCK="$SSH_AUTH_SOCK_LINK"
fi
```

`keychain` prompts for your passphrase once per reboot and reuses the agent across terminals. The symlink ensures the devcontainer can mount a consistent SSH agent path across reboots.

**macOS:**

```bash
ssh-add --apple-use-keychain ~/.ssh/id_ed25519
```

Keys added with `--apple-use-keychain` persist across restarts.

**Windows (Git Bash):**

```bash
eval "$(ssh-agent -s)"
ssh-add ~/.ssh/id_ed25519
```

Or enable the OpenSSH Authentication Agent service in Windows Services.

## Troubleshooting

### Devcontainer fails to start after reboot with mount error

**Error**: `error mounting "..." to rootfs at "/ssh-agent": not a directory`

**Cause**: The SSH agent socket path changed after reboot, but your devcontainer was created with the old path.

**Solution**:

1. Verify the fixed symlink is configured in your `~/.bashrc` (see keychain setup above)
2. Restart your terminal or run: `source ~/.bashrc`
3. Verify the symlink exists: `ls -la ~/.ssh/agent.sock`
4. **Rebuild the devcontainer one final time**: Command Palette → "Dev Containers: Rebuild Container"
5. After this rebuild, reboots will no longer require rebuilds

If the symlink is missing or broken after reboot, ensure the keychain configuration is in `~/.bashrc` (not just set in the current terminal session).

## GitHub CLI Setup

The devcontainer loads environment variables from `~/.secrets/.env` on your host. Create this file with a GitHub token for CLI operations:

```bash
mkdir -p ~/.secrets
chmod 700 ~/.secrets
echo "GH_TOKEN=ghp_your_token_here" > ~/.secrets/.env
chmod 600 ~/.secrets/.env
```

Create a token at [GitHub Settings > Developer settings > Personal access tokens](https://github.com/settings/tokens) with `repo` and `workflow` scopes.

## Opening the Devcontainer

1. Clone the repository
2. Open the folder in VS Code
3. When prompted, click "Reopen in Container" (or run `Dev Containers: Reopen in Container` from the command palette)

## Included Tools

- **Docker-in-Docker** - Build and test container images
- **Pre-commit hooks** - Automatic linting on commit (gitleaks, prettier, yamllint)
- **MegaLinter** - Run `./lint.sh` for comprehensive linting (returns non-zero on failure, results in `.output/`)
- **GitHub CLI** - `gh` command for GitHub operations
- **Safe-chain** - Supply chain attack protection for npm/pip

## Verify Setup

After opening the devcontainer, verify everything is working:

```bash
./.devcontainer/verify-setup.sh
```

This checks Docker-in-Docker, pre-commit hooks, safe-chain protection, GitHub CLI, and SSH agent forwarding.
