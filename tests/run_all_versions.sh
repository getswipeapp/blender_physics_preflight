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
for b in "${BLENDERS[@]}"; do
  if [[ ! -x "$b" ]]; then
    echo "SKIP (not found): $b"
    continue
  fi
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

exit $overall
