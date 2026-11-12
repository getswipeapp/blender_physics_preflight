#!/usr/bin/env bash
# Release gate: run the headless suite on EVERY supported Blender version and
# fail unless all of them were found AND passed. The Phase 0 target matrix is
# 4.2 LTS, 4.5 LTS, 5.0 and 5.2 LTS.
#
# A missing version is a gate FAILURE, not a skip — otherwise a half-tested
# matrix looks green. Point each entry at an official Blender binary.
set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Required versions and where to find them. Override any path via the matching
# FAILSAFE_BLENDER_<ver> environment variable (e.g. FAILSAFE_BLENDER_4_2=/path/Blender).
#
# NOTE: indexed array + indirect expansion only — no `declare -A`, so this runs
# on macOS's default Bash 3.2. Each entry is "version|override-var|default-path".
CERT="/Users/ralph/Downloads/blender_runtime_certification/apps"
ENTRIES=(
  "4.2|FAILSAFE_BLENDER_4_2|$CERT/4.2/Blender.app/Contents/MacOS/Blender"
  "4.5|FAILSAFE_BLENDER_4_5|$CERT/4.5/Blender.app/Contents/MacOS/Blender"
  "5.0|FAILSAFE_BLENDER_5_0|$CERT/5.0/Blender.app/Contents/MacOS/Blender"
  "5.2|FAILSAFE_BLENDER_5_2|/Applications/Blender.app/Contents/MacOS/Blender"
)

overall=0
missing=0
REQUIRED=()
for entry in "${ENTRIES[@]}"; do
  IFS='|' read -r ver envvar default <<<"$entry"
  REQUIRED+=("$ver")
  b="${!envvar:-$default}"
  echo "======================================================================"
  if [[ ! -x "$b" ]]; then
    echo ">> MISSING required Blender $ver at: $b"
    missing=1
    continue
  fi
  echo "Running tests with Blender $ver: $b"
  "$b" --version | head -1
  "$b" -b --factory-startup -P "$HERE/run_tests.py"
  rc=$?
  if [[ $rc -ne 0 ]]; then
    echo ">> FAILED on Blender $ver (exit $rc)"
    overall=1
  else
    echo ">> OK on Blender $ver"
  fi
done

if [[ $missing -ne 0 ]]; then
  echo ">> ERROR: one or more required Blender versions were not found."
  echo ">> The release gate requires a result for EVERY version: ${REQUIRED[*]}"
  exit 2
fi
if [[ $overall -ne 0 ]]; then
  echo ">> Release gate: FAILED (a version did not pass)."
  exit 1
fi
echo "Release gate: PASS — all required versions (${REQUIRED[*]}) passed."
exit 0
