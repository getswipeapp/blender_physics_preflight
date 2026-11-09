#!/bin/bash
# usage: run_binary.sh <version>  -- runs all probes with the official Blender binary in background mode
V=$1; S=/tmp/claude-0/-home-user/d07daa23-3244-5bea-a7a5-9eff86fcaf36/scratchpad
BL=$S/blender/blender-$V-linux-x64/blender; O=$S/outbin/$V
rm -rf "$O"; mkdir -p "$O"
for c in cloth_memory cloth_disk softbody_memory softbody_disk rigid fluid_bake fluid_inspect fluid_after_delete particles geometry_nodes; do
  FLUID_CACHE_TYPE=ALL timeout 900 $BL -b --factory-startup -noaudio --python-exit-code 1 -P $S/probe/probe.py -- $O $c > $O/log_$c.txt 2>&1; echo "$V $c rc=$?"
done
$BL -b --factory-startup -noaudio -P $S/probe/setup_probe.py 2>&1 | grep SETUPJSON > $O/setup_probe.txt
$BL -b --factory-startup -noaudio -P $S/probe/gn_packed.py -- $O/gnp 2>&1 | grep GNJSON > $O/gn_packed.txt
$BL -b --factory-startup -noaudio -P $S/probe/extra_api.py 2>&1 | grep EXTRAJSON > $O/extra_api.txt
