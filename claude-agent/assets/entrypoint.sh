#!/bin/bash
set -euo pipefail

# Bootstrap: fetch config from K8s API
NAMESPACE=$(cat /var/run/secrets/kubernetes.io/serviceaccount/namespace)

# Auth: static setup token (1-year lifetime, no refresh needed)
CLAUDE_CODE_OAUTH_TOKEN=$(kubectl get secret claude-credentials \
  -n "$NAMESPACE" -o jsonpath='{.data.oauth-token}' | base64 -d)
export CLAUDE_CODE_OAUTH_TOKEN

# MCP and settings config
mkdir -p ~/.claude
kubectl get configmap claude-mcp-config -n "$NAMESPACE" \
  -o jsonpath='{.data.mcp\.json}' >/workspace/.mcp.json

kubectl get configmap claude-settings -n "$NAMESPACE" \
  -o jsonpath='{.data.settings\.json}' >~/.claude/settings.json

# Remove kubectl from PATH — agent must use MCP for K8s operations
# Can't rm from /usr/local/bin as non-root; shadow it with a no-op instead
mkdir -p /home/node/.local/bin
ln -sf /usr/bin/false /home/node/.local/bin/kubectl
export PATH="/home/node/.local/bin:${PATH}"

exec claude "$@"
