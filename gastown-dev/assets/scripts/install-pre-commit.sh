#!/bin/bash
set -euo pipefail

# Install pre-commit via pip
pip install --no-cache-dir pre-commit

# Verify installation
if command -v pre-commit &> /dev/null; then
  echo "✅ pre-commit is ready: $(pre-commit --version)"
else
  echo "❌ pre-commit installation failed"
  exit 1
fi
