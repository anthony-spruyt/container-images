#!/bin/bash
# Test coder-gitops image: required tooling, non-root user, scripts present,
# read-only rootfs compatible.
# Usage: ./test.sh <image-ref>

set -euo pipefail

IMAGE_REF="${1:?Usage: $0 <image-ref>}"

echo "=== coder-gitops image tests ==="
echo "Image: $IMAGE_REF"

# Test 1: required binaries present
echo "Test 1: required binaries..."
for bin in coder kubectl curl jq bash; do
  if ! docker run --rm --entrypoint sh "$IMAGE_REF" -c "command -v $bin >/dev/null"; then
    echo "  ERROR: missing binary: $bin"
    exit 1
  fi
  echo "  found: $bin"
done

# Test 2: runs as non-root UID 1000
echo "Test 2: non-root user..."
UID_OUT=$(docker run --rm --entrypoint id "$IMAGE_REF" -u)
if [ "$UID_OUT" != "1000" ]; then
  echo "  ERROR: expected UID 1000, got $UID_OUT"
  exit 1
fi
echo "  UID=1000 ok"

# Test 3: scripts present and executable
echo "Test 3: scripts..."
for script in push-templates.sh rotate-token.sh; do
  if ! docker run --rm --entrypoint sh "$IMAGE_REF" -c "test -x /usr/local/bin/$script"; then
    echo "  ERROR: /usr/local/bin/$script missing or not executable"
    exit 1
  fi
  echo "  found: $script"
done

# Test 4: script syntax valid
echo "Test 4: script syntax check..."
for script in push-templates.sh rotate-token.sh; do
  if ! docker run --rm --entrypoint bash "$IMAGE_REF" -n "/usr/local/bin/$script"; then
    echo "  ERROR: $script has syntax errors"
    exit 1
  fi
done
echo "  syntax ok"

# Test 5: kubectl + coder run (--client / --version)
echo "Test 5: kubectl + coder version..."
docker run --rm --entrypoint kubectl "$IMAGE_REF" version --client >/dev/null
docker run --rm --entrypoint coder "$IMAGE_REF" version >/dev/null
echo "  versions ok"

# Test 6: read-only root filesystem compatible (PSA restricted)
echo "Test 6: read-only rootfs + tmpfs /tmp..."
if ! docker run --rm \
  --read-only \
  --tmpfs /tmp:rw,size=16m \
  --entrypoint sh "$IMAGE_REF" \
  -c "kubectl version --client >/dev/null && coder version >/dev/null"; then
  echo "  ERROR: binaries failed under read-only rootfs"
  exit 1
fi
echo "  read-only rootfs ok"

# Test 7: push-templates.sh skips unchanged templates (diff logic)
echo "Test 7: diff-based skip logic..."
TEST7=$(mktemp)
cat >"$TEST7" <<'TESTSCRIPT'
#!/bin/bash
set -euo pipefail
export CODER_URL=http://fake CODER_SESSION_TOKEN=fake
export TEMPLATES_DIR=$(mktemp -d)
mkdir -p "${TEMPLATES_DIR}/mytemplate"
echo "resource {}" > "${TEMPLATES_DIR}/mytemplate/main.tf"

cat > /tmp/coder <<'MOCK'
#!/bin/bash
if [ "$1" = "templates" ] && [ "$2" = "pull" ]; then
  cp -a "${TEMPLATES_DIR}/$3/." "$4/"
  exit 0
elif [ "$1" = "templates" ] && [ "$2" = "push" ]; then
  echo "UNEXPECTED_PUSH" >&2
  exit 1
fi
MOCK
chmod +x /tmp/coder
export PATH="/tmp:$PATH"

output=$(/usr/local/bin/push-templates.sh 2>&1)
if echo "$output" | grep -q "SKIP: mytemplate"; then
  echo "  skip-unchanged ok"
else
  echo "  ERROR: expected SKIP for unchanged template"
  echo "  output: $output"
  exit 1
fi
TESTSCRIPT
chmod 644 "$TEST7"
docker run --rm --tmpfs /tmp:rw,exec,size=16m \
  -v "$TEST7:/test-diff.sh:ro" \
  --entrypoint bash "$IMAGE_REF" -c "bash /test-diff.sh"
rm -f "$TEST7"

# Test 8: push-templates.sh pushes changed templates
echo "Test 8: diff-based push on change..."
TEST8=$(mktemp)
cat >"$TEST8" <<'TESTSCRIPT'
#!/bin/bash
set -euo pipefail
export CODER_URL=http://fake CODER_SESSION_TOKEN=fake
export TEMPLATES_DIR=$(mktemp -d)
mkdir -p "${TEMPLATES_DIR}/mytemplate"
echo "resource {}" > "${TEMPLATES_DIR}/mytemplate/main.tf"

cat > /tmp/coder <<'MOCK'
#!/bin/bash
if [ "$1" = "templates" ] && [ "$2" = "pull" ]; then
  echo "old content" > "$4/main.tf"
  exit 0
elif [ "$1" = "templates" ] && [ "$2" = "push" ]; then
  echo "pushed"
  exit 0
fi
MOCK
chmod +x /tmp/coder
export PATH="/tmp:$PATH"

output=$(/usr/local/bin/push-templates.sh 2>&1)
if echo "$output" | grep -q "CHANGED: mytemplate"; then
  echo "  push-changed ok"
else
  echo "  ERROR: expected CHANGED for modified template"
  echo "  output: $output"
  exit 1
fi
TESTSCRIPT
chmod 644 "$TEST8"
docker run --rm --tmpfs /tmp:rw,exec,size=16m \
  -v "$TEST8:/test-diff.sh:ro" \
  --entrypoint bash "$IMAGE_REF" -c "bash /test-diff.sh"
rm -f "$TEST8"

# Test 9: push-templates.sh creates new templates (pull fails)
echo "Test 9: new template creation..."
TEST9=$(mktemp)
cat >"$TEST9" <<'TESTSCRIPT'
#!/bin/bash
set -euo pipefail
export CODER_URL=http://fake CODER_SESSION_TOKEN=fake
export TEMPLATES_DIR=$(mktemp -d)
mkdir -p "${TEMPLATES_DIR}/newtemplate"
echo "resource {}" > "${TEMPLATES_DIR}/newtemplate/main.tf"

cat > /tmp/coder <<'MOCK'
#!/bin/bash
if [ "$1" = "templates" ] && [ "$2" = "pull" ]; then
  exit 1
elif [ "$1" = "templates" ] && [ "$2" = "push" ]; then
  echo "pushed"
  exit 0
fi
MOCK
chmod +x /tmp/coder
export PATH="/tmp:$PATH"

output=$(/usr/local/bin/push-templates.sh 2>&1)
if echo "$output" | grep -q "NEW: newtemplate"; then
  echo "  new-template ok"
else
  echo "  ERROR: expected NEW for non-existent template"
  echo "  output: $output"
  exit 1
fi
TESTSCRIPT
chmod 644 "$TEST9"
docker run --rm --tmpfs /tmp:rw,exec,size=16m \
  -v "$TEST9:/test-diff.sh:ro" \
  --entrypoint bash "$IMAGE_REF" -c "bash /test-diff.sh"
rm -f "$TEST9"

echo ""
echo "=== All tests passed ==="
