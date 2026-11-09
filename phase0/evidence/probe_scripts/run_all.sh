#!/bin/bash
# usage: run_all.sh <version>
V=$1; S=/tmp/claude-0/-home-user/d07daa23-3244-5bea-a7a5-9eff86fcaf36/scratchpad
rm -rf $S/out/$V; mkdir -p $S/out/$V
for c in cloth_memory cloth_disk softbody_memory softbody_disk rigid fluid_bake fluid_inspect fluid_after_delete particles geometry_nodes; do
  timeout 600 $S/venvs/bpy$V/bin/python -I $S/probe/probe.py $S/out/$V $c > $S/out/$V/log_$c.txt 2>&1
  echo "$V $c rc=$?"
done
