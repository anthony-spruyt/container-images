#!/bin/bash
set -euo pipefail

npm install -g "@aikidosec/safe-chain@${SAFE_CHAIN_VERSION:?SAFE_CHAIN_VERSION must be set}"
safe-chain setup
safe-chain setup-ci

echo "safe-chain ${SAFE_CHAIN_VERSION} installed and configured"
