#!/bin/bash
set -euo pipefail

# Implement custom devcontainer setup here. This is run after the devcontainer has been created.

# Python dependencies for megalinter-factory
pip install --quiet pyyaml jinja2
