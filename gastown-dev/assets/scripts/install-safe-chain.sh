#!/bin/bash
set -euo pipefail

npm install -g @aikidosec/safe-chain
safe-chain setup        # Shell aliases for interactive terminals
safe-chain setup-ci     # Executable shims for scripts/CI

echo "✅ safe-chain installed and configured"
