#!/usr/bin/env bash
# Release gate: run the headless suite on EVERY supported Blender version and
# fail unless all of them were found AND genuinely passed. The Phase 0 target
# matrix is 4.2 LTS, 4.5 LTS, 5.0 and 5.2 LTS.
#
# A missing version is a gate FAILURE, not a skip. And a PASS is decided by
# tests/gate_check.py reading each run's log — NOT by Blender's process exit
# code. Blender exits 0 even after a Python SystemError (e.g. the 4.2.9 fluid
# ViewLayer.update() crash), so trusting the exit code let a crashed, half-run
# suite look green. The gate now requires the SUITE_DONE completion sentinel,
# zero failures, a consistent/above-floor test count, and no crash signature;
# it also requires all four versions to report the SAME total.
set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="${FAILSAFE_PYTHON:-python3}"
MIN_TOTAL="${FAILSAFE_MIN_TOTAL:-700}"
LOGDIR="$(mktemp -d "${TMPDIR:-/tmp}/failsafe_cert_logs.XXXXXX")"

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
TOTALS=()        # collected per-version SUITE_DONE total, for cross-version equality
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
  log="$LOGDIR/run_$ver.log"
  # Tee so the output is still visible live AND captured for the gate verdict.
  "$b" -b --factory-startup -P "$HERE/run_tests.py" 2>&1 | tee "$log"
  rc=${PIPESTATUS[0]}
  if "$PYTHON" "$HERE/gate_check.py" "$log" --exit-code "$rc" --min-total "$MIN_TOTAL"; then
    echo ">> OK on Blender $ver (gate verified completion + all-pass)"
    t=$(sed -n 's/.*SUITE_DONE .*total=\([0-9][0-9]*\).*/\1/p' "$log" | tail -1)
    TOTALS+=("$t")
  else
    echo ">> FAILED on Blender $ver (gate rejected the run; exit was $rc)"
    overall=1
  fi
done

if [[ $missing -ne 0 ]]; then
  echo ">> ERROR: one or more required Blender versions were not found."
  echo ">> The release gate requires a result for EVERY version: ${REQUIRED[*]}"
  echo ">> Logs: $LOGDIR"
  exit 2
fi
if [[ $overall -ne 0 ]]; then
  echo ">> Release gate: FAILED (a version did not genuinely pass)."
  echo ">> Logs: $LOGDIR"
  exit 1
fi
# Cross-version test-count equality: every version must run the SAME number of
# tests. A version silently running fewer (e.g. a whole group skipped) is an
# incomplete matrix, not a pass.
first="${TOTALS[0]}"
for t in "${TOTALS[@]}"; do
  if [[ "$t" != "$first" ]]; then
    echo ">> Release gate: FAILED — versions ran different test counts: ${TOTALS[*]}"
    echo ">> Logs: $LOGDIR"
    exit 1
  fi
done
echo "Release gate: PASS — all required versions (${REQUIRED[*]}) genuinely passed; each ran $first tests."
exit 0
