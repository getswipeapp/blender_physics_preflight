# SPDX-License-Identifier: GPL-3.0-or-later
"""REAL multi-process batch proof (not the fake-runner unit test).

Run as the PARENT under Blender; it spawns actual child Blender processes via
failsafe.batch.run_isolated_batch and proves, end to end:
  * a good .blend is scanned cleanly in its own process (exit 0),
  * a corrupt .blend is an ACTUAL failed worker, isolated as a per-file error,
  * partial recovery: the good file's result survives the bad one,
  * a REAL timeout kills a genuinely hanging child process.

Usage:
  blender -b --factory-startup -P certification/render_proof/real_batch_proof.py
"""
import json
import os
import shutil
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO)

import bpy
from failsafe import batch

BIN = bpy.app.binary_path
print("Parent Blender:", BIN)
print("Blender version:", bpy.app.version_string)

fails = []

# ---- Part 1: real good + corrupt workers, partial recovery ----------------
d = tempfile.mkdtemp(prefix="failsafe_realbatch_")
bpy.ops.wm.read_factory_settings(use_empty=True)
good = os.path.join(d, "good.blend")
bpy.ops.wm.save_as_mainfile(filepath=good)
with open(os.path.join(d, "corrupt.blend"), "wb") as fh:
    fh.write(b"this is not a blend file" * 50)

print("\n=== REAL batch: good.blend + corrupt.blend (timeout 180s) ===")
agg, txt = batch.run_isolated_batch(
    d, {"format": "json"}, blender_bin=BIN, timeout=180, source_root=REPO)
print(txt)
print("overall_exit =", agg)
data = json.loads(txt)
by = {os.path.basename(f["file"]): f for f in data["files"]}
g, c = by.get("good.blend", {}), by.get("corrupt.blend", {})
if not (g.get("exit") == 0 and "error" not in g):
    fails.append("good.blend not clean: %s" % g)
if "error" not in c:
    fails.append("corrupt.blend not recorded as an error: %s" % c)
if agg != 3:
    fails.append("overall exit should be 3 (error present), got %s" % agg)
print("partial-recovery:", "OK" if not fails else "FAIL",
      "- good scanned, corrupt isolated")

# ---- Part 2: a REAL hanging child, killed at the timeout ------------------
print("\n=== REAL timeout: a child that sleeps 60s, timeout=3s ===")
d2 = tempfile.mkdtemp(prefix="failsafe_realto_")
shutil.copy(good, os.path.join(d2, "hang.blend"))
orig = batch.build_child_argv
try:
    # Spawn a genuinely hanging child (real process) so the timeout path kills a
    # real subprocess, not a simulated one.
    batch.build_child_argv = lambda b, f, **k: [
        b, "-b", "--factory-startup", "--python-expr", "import time; time.sleep(60)"]
    agg2, txt2 = batch.run_isolated_batch(
        d2, {"format": "json"}, blender_bin=BIN, timeout=3, source_root=REPO)
finally:
    batch.build_child_argv = orig
print(txt2)
data2 = json.loads(txt2)
err = (data2["files"][0].get("error") or "") if data2.get("files") else ""
if "timed out" not in err:
    fails.append("real hang not reported as a timeout: %r" % err)
if agg2 != 3:
    fails.append("timeout overall exit should be 3, got %s" % agg2)
print("real-timeout:", "OK" if "timed out" in err else "FAIL", "-", err)

print("\n" + "=" * 60)
if fails:
    print("REAL BATCH PROOF: FAILED")
    for f in fails:
        print("  -", f)
    sys.exit(1)
print("REAL BATCH PROOF: ALL CHECKS PASSED (real subprocesses)")
sys.exit(0)
