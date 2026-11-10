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
# PHYSPF_BLENDER_<ver> environment variable (e.g. PHYSPF_BLENDER_4_2=/path/Blender).
CERT="/Users/ralph/Downloads/blender_runtime_certification/apps"
declare -A BINS=(
  ["4.2"]="${PHYSPF_BLENDER_4_2:-$CERT/4.2/Blender.app/Contents/MacOS/Blender}"
  ["4.5"]="${PHYSPF_BLENDER_4_5:-$CERT/4.5/Blender.app/Contents/MacOS/Blender}"
  ["5.0"]="${PHYSPF_BLENDER_5_0:-$CERT/5.0/Blender.app/Contents/MacOS/Blender}"
  ["5.2"]="${PHYSPF_BLENDER_5_2:-/Applications/Blender.app/Contents/MacOS/Blender}"
)
REQUIRED=("4.2" "4.5" "5.0" "5.2")

overall=0
missing=0
for ver in "${REQUIRED[@]}"; do
  b="${BINS[$ver]}"
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
