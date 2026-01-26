#!/bin/bash
set -euo pipefail

# renovate: datasource=github-releases depName=go-task/task
TASK_VERSION="v3.48.0"

# Download from GitHub releases (more reliable than taskfile.dev)
curl -sSfL "https://github.com/go-task/task/releases/download/${TASK_VERSION}/task_linux_amd64.tar.gz" -o /tmp/task.tar.gz
tar -xzf /tmp/task.tar.gz -C /usr/local/bin task
rm /tmp/task.tar.gz
chmod +x /usr/local/bin/task

echo "✅ Task ${TASK_VERSION} installed successfully."
