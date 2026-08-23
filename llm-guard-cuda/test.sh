#!/bin/bash
# Test script for llm-guard-cuda container.
# The image is byte-identical to llm-guard apart from the torch wheel, so the
# assertions live in llm-guard/test.sh and this only selects the cuda flavor.
# Usage: ./test.sh <image-ref>

set -euo pipefail

exec "$(dirname "$0")/../llm-guard/test.sh" "${1:?Usage: $0 <image-ref>}" cuda
