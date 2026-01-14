#!/bin/bash
set -euo pipefail

# Install Python development tools via pipx (isolated venvs)
# Then patch each venv to fix known vulnerabilities

echo "Installing pipx..."
pip install --no-cache-dir pipx
pipx ensurepath

# Tools to install (based on devcontainer feature defaults + pre-commit)
TOOLS=(
  "pre-commit"
  "virtualenv"
  "black"
  "flake8"
  "mypy"
  "pytest"
  "pylint"
  "autopep8"
  "yapf"
  "pydocstyle"
  "pycodestyle"
  "bandit"
)

echo "Installing Python tools via pipx..."
for tool in "${TOOLS[@]}"; do
  echo "  Installing ${tool}..."
  pipx install "${tool}"
done

# Patch venvs to fix GHSA-58pv-8j8x-9vj2 (jaraco.context path traversal)
# Only virtualenv pulls in jaraco.context, but we patch all venvs defensively
echo "Patching venvs for security fixes..."
PIPX_HOME="${PIPX_HOME:-/root/.local/pipx}"
for venv_dir in "${PIPX_HOME}/venvs"/*; do
  if [ -d "${venv_dir}" ]; then
    venv_name=$(basename "${venv_dir}")
    venv_pip="${venv_dir}/bin/pip"
    if [ -x "${venv_pip}" ]; then
      # Check if jaraco.context is installed in this venv
      if "${venv_pip}" show jaraco.context &>/dev/null; then
        echo "  Upgrading jaraco.context in ${venv_name}..."
        "${venv_pip}" install --no-cache-dir --upgrade "jaraco.context>=6.1.0"
      fi
    fi
  fi
done

echo "Verifying installations..."
for tool in "${TOOLS[@]}"; do
  if command -v "${tool}" &>/dev/null; then
    echo "  ✅ ${tool} installed"
  else
    echo "  ❌ ${tool} not found in PATH"
    exit 1
  fi
done

echo "✅ Python tools installed and patched successfully."
