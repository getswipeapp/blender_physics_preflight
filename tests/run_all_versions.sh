#!/usr/bin/env bash
# Run the headless test harness on every installed Blender binary.
# Edit BLENDERS to point at the binaries you want to certify. The Phase 0 target
# matrix is 4.2 LTS, 4.5 LTS, 5.0, 5.2 LTS.
set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$HERE")"

# macOS default install. Add more entries, one per line, for other versions.
BLENDERS=(
  "/Applications/Blender.app/Contents/MacOS/Blender"
  # "/Applications/Blender 4.2/Blender.app/Contents/MacOS/Blender"
  # "/Applications/Blender 4.5/Blender.app/Contents/MacOS/Blender"
  # "/Applications/Blender 5.0/Blender.app/Contents/MacOS/Blender"
)

overall=0
tested=0
for b in "${BLENDERS[@]}"; do
  if [[ ! -x "$b" ]]; then
    echo "SKIP (not found): $b"
    continue
  fi
  tested=$((tested + 1))
  echo "======================================================================"
  echo "Running tests with: $b"
  "$b" --version | head -1
  "$b" -b --factory-startup -P "$HERE/run_tests.py"
  rc=$?
  if [[ $rc -ne 0 ]]; then
    echo ">> FAILED on $b (exit $rc)"
    overall=1
  else
    echo ">> OK on $b"
  fi
done

# A run that tested zero binaries is a FAILURE, not a pass — otherwise an empty
# matrix looks green. The release gate should require a result per supported
# version (currently 4.2, 4.5, 5.0, 5.2).
if [[ $tested -eq 0 ]]; then
  echo ">> ERROR: no Blender binaries found — nothing was tested."
  exit 2
fi
echo "Tested $tested Blender binary/binaries."
exit $overall
