#!/usr/bin/env bash
# Run the Physics Preflight headless suite on every certified Blender build and
# capture the pass/fail summary line per version.
set -u
ROOT="/Users/ralph/Downloads/blender_physics_preflight"
APPS="/Users/ralph/Downloads/blender_runtime_certification/apps"
RESULTS="/Users/ralph/Downloads/blender_runtime_certification/results"
mkdir -p "$RESULTS"

declare -a BINS=(
  "5.2|/Applications/Blender.app/Contents/MacOS/Blender"
  "4.2|$APPS/4.2/Blender.app/Contents/MacOS/Blender"
  "4.5|$APPS/4.5/Blender.app/Contents/MacOS/Blender"
  "5.0|$APPS/5.0/Blender.app/Contents/MacOS/Blender"
)

echo "VERSION | VERSION_STRING | RESULT"
for entry in "${BINS[@]}"; do
  ver="${entry%%|*}"; bin="${entry##*|}"
  if [[ ! -x "$bin" ]]; then echo "$ver | (binary not found) | SKIP"; continue; fi
  log="$RESULTS/run_$ver.log"
  vs=$("$bin" --version 2>/dev/null | head -1)
  "$bin" -b --factory-startup -P "$ROOT/tests/run_tests.py" >"$log" 2>&1
  rc=$?
  summary=$(grep -E "passed, .* failed, .* total" "$log" | tail -1)
  echo "$ver | $vs | rc=$rc | $summary"
done
