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

# Helper: run a mock-based push-templates test inside the container.
# Usage: run_mock_test <test_label> <template_name> <mock_script> <expected_grep> <ok_message>
run_mock_test() {
  local label="$1" tpl_name="$2" mock_body="$3" expected="$4" ok_msg="$5"
  echo "${label}"
  local mockfile testfile
  mockfile=$(mktemp)
  testfile=$(mktemp)
  printf '%s\n' "${mock_body}" >"${mockfile}"
  cat >"${testfile}" <<'TESTSCRIPT'
#!/bin/bash
set -euo pipefail
export CODER_URL=http://fake CODER_SESSION_TOKEN=fake
export TEMPLATES_DIR=$(mktemp -d)
mkdir -p "${TEMPLATES_DIR}/__TPL__"
echo "resource {}" > "${TEMPLATES_DIR}/__TPL__/main.tf"
cp /mock-coder.sh /tmp/coder
chmod +x /tmp/coder
export PATH="/tmp:$PATH"
output=$(/usr/local/bin/push-templates.sh 2>&1)
if echo "$output" | grep -q "__EXPECTED__"; then
  echo "  __OK_MSG__"
else
  echo "  ERROR: expected '__EXPECTED__' in output"
  echo "  output: $output"
  exit 1
fi
TESTSCRIPT
  sed -i "s|__TPL__|${tpl_name}|g; s|__EXPECTED__|${expected}|g; s|__OK_MSG__|${ok_msg}|g" "${testfile}"
  chmod 644 "${testfile}" "${mockfile}"
  docker run --rm --tmpfs /tmp:rw,exec,size=16m \
    -v "${testfile}:/test-diff.sh:ro" \
    -v "${mockfile}:/mock-coder.sh:ro" \
    --entrypoint bash "$IMAGE_REF" -c "bash /test-diff.sh"
  rm -f "${testfile}" "${mockfile}"
}

# Test 7: push-templates.sh skips unchanged templates (diff logic)
# shellcheck disable=SC2016 # mock scripts use single quotes intentionally
run_mock_test "Test 7: diff-based skip logic..." "mytemplate" \
  '#!/bin/bash
if [ "$1" = "templates" ] && [ "$2" = "pull" ]; then
  cp -a "${TEMPLATES_DIR}/$3/." "$4/"
  exit 0
elif [ "$1" = "templates" ] && [ "$2" = "push" ]; then
  echo "UNEXPECTED_PUSH" >&2
  exit 1
fi' \
  "SKIP: mytemplate" "skip-unchanged ok"

# Test 8: push-templates.sh pushes changed templates
# shellcheck disable=SC2016
run_mock_test "Test 8: diff-based push on change..." "mytemplate" \
  '#!/bin/bash
if [ "$1" = "templates" ] && [ "$2" = "pull" ]; then
  echo "old content" > "$4/main.tf"
  exit 0
elif [ "$1" = "templates" ] && [ "$2" = "push" ]; then
  echo "pushed"
  exit 0
fi' \
  "CHANGED: mytemplate" "push-changed ok"

# Test 9: push-templates.sh creates new templates (pull fails)
# shellcheck disable=SC2016
run_mock_test "Test 9: new template creation..." "newtemplate" \
  '#!/bin/bash
if [ "$1" = "templates" ] && [ "$2" = "pull" ]; then
  echo "template \"newtemplate\" not found" >&2
  exit 1
elif [ "$1" = "templates" ] && [ "$2" = "push" ]; then
  echo "pushed"
  exit 0
fi' \
  "NEW: newtemplate" "new-template ok"

# Test 10: pull failure reason appears in log output
# shellcheck disable=SC2016
run_mock_test "Test 10: pull failure reason logged..." "failtemplate" \
  '#!/bin/bash
if [ "$1" = "templates" ] && [ "$2" = "pull" ]; then
  echo "auth token expired" >&2
  exit 1
elif [ "$1" = "templates" ] && [ "$2" = "push" ]; then
  echo "pushed"
  exit 0
fi' \
  "pull failed (auth token expired)" "pull-failure-reason ok"

echo ""
echo "=== All tests passed ==="
