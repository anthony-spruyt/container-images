#!/bin/bash
set -euo pipefail

# Install pre-commit via pip
pip install --no-cache-dir pre-commit

# Upgrade jaraco.context to fix GHSA-58pv-8j8x-9vj2 (path traversal vulnerability)
pip install --no-cache-dir --upgrade "jaraco.context>=6.1.0"

# Verify installation
if command -v pre-commit &> /dev/null; then
  echo "✅ pre-commit is ready: $(pre-commit --version)"
else
  echo "❌ pre-commit installation failed"
  exit 1
fi
