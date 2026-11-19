# Fluid (Mantaflow) & Geometry Nodes disk-cache layouts

Research for the next #27 sub-increment: extend baselined per-frame SHA-256 hash
verification from point caches (`.bphys`) to Fluid and Geometry Nodes disk caches.

**Method:** real headless bakes on Blender 4.2.9 / 4.5.9 / 5.0.1 / 5.2.3 (probe
`scratchpad/probe_fluid_gn.py`), inspecting the actual files on disk. Read-only
study; nothing here ships yet.

## Fluid (Mantaflow)

A fluid **domain** writes to `domain_settings.cache_directory` (its OWN absolute or
`//`-relative path — NOT the `blendcache_<file>` point-cache folder). The cache is
split into **per-stage subdirectories**, each holding **one file per frame**:

| Subdir       | Filename pattern            | When present                      | Format (default)          |
|--------------|-----------------------------|-----------------------------------|---------------------------|
| `config/`    | `config_%04d.uni`           | always (on any bake)              | `.uni`, gzip (magic 1f8b) |
| `data/`      | `fluid_data_%04d.vdb`       | always (data bake)                | OpenVDB (magic `20 42 44 56`) |
| `noise/`     | `fluid_noise_%04d.vdb`      | `use_noise` + noise bake          | OpenVDB                   |
| `mesh/`      | `fluid_mesh_%04d.bobj.gz` / `.obj` | `use_mesh` + mesh bake     | BOBJECT / OBJECT          |
| `particles/` | `fluid_particles_%04d.vdb`  | any `use_*_particles` + particle bake | OpenVDB (or UNI)      |
| `guiding/`   | `fluid_guiding_%04d.vdb`    | `use_guide`                       | OpenVDB                   |

Confirmed identical naming on 4.5.9 / 5.0.1 / 5.2.3. (4.2.9 shares the Mantaflow
scheme; my probe's headless `fluid.bake_data()` tripped a `ViewLayer.update()`
SystemError — a headless-context quirk of the probe, not the on-disk format.)

Key facts that shape verification:
- **Frame numbers are 4-digit zero-padded** (`_0001`) — DIFFERENT from `.bphys`'s
  6-digit `_000001_00`. A fluid enumerator needs its own filename builder.
- **The required frame range is the domain's own** `cache_frame_start ..
  cache_frame_end` (default **1..250**), INDEPENDENT of the scene frame range. Do
  not use the scene range (a trap: we'd miss or over-count frames).
- **Which stages exist on disk depends on which bake steps ran AND the stage
  flags.** `config` and `data` are the baseline; `noise`/`mesh`/`particles`/
  `guiding` appear only when their flag is on and that stage was baked. A stage
  flag that is ON but whose files are absent = an incomplete/!baked stage →
  "Couldn't verify" that stage, never a false PASS.
- **Formats vary** (`.vdb`, `.uni`, `.bobj.gz`). Hashing is format-agnostic (we
  SHA-256 the bytes), so this doesn't block change-detection — but the enumerator
  must read `cache_*_format` to build the right extension per stage, or just glob
  the stage subdir by frame number.
- **"Replay" cache type** (`cache_type == 'REPLAY'`) is a playback cache, not a
  bake — treat like the existing Fluid "Replay" rule: WARNING/NA, never PASS.

Proposed identity scheme (relocation-stable, mirrors the point-cache one):
`Scene::Owner::Fluid::<modifier_name>/<stage>` — one sim-verify entry per stage so
a changed noise stage is distinct from a changed data stage.

## Geometry Nodes simulation zones

- The GN modifier's bake **defaults to `bake_target == 'PACKED'`** (4.5/5.0/5.2) —
  packed INTO the `.blend`, leaving NO on-disk trace. This is exactly the case
  Failsafe already reports as **"Couldn't verify"** for GN packed bakes (#17/#19),
  and it is the common default. Nothing on disk to hash → stays "Couldn't verify".
- A **DISK** bake (`bake_target='DISK'`, `bake_directory=<dir>`) writes, per bake:
  `<bake_directory>/<bake_id>/meta/%05d_%05d.json` (+ a `blobs/` dir for large
  attribute data; a trivial passthrough sim stored everything inline in the JSON,
  so no `blobs/` appeared). **Frame numbers are 5-digit** (`00001_00000.json` =
  `<frame:05d>_<subframe:05d>`), and `<bake_id>` is a per-bake integer folder.
  JSON magic `7b 22 76 65 72 73 69...` = `{"versio…`.
- 4.2.9's modifier API has **no `bake_target`** attribute (older); its disk bakes
  land in a default `blendcache_<file>`-style location. GN disk-bake support is
  therefore version-sensitive and rarer than fluid.

Implication: GN disk-cache hashing is lower priority than fluid (packed is the
default and already handled). When we do it, enumerate `<bake_dir>/<id>/meta/*.json`
(and `blobs/*`) as the per-frame files; a packed target stays "Couldn't verify".

## Blender 4.2 bake: the "gap" was a probe artifact (RESOLVED)

The first standalone probe's headless `fluid.bake_data()` failed on 4.2.9 with a
`Scene.frame_set()` SystemError. Investigating: that failure came from the probe's
own setup (a GAS domain with an explicit `scene.frame_set(1)` before baking), NOT
from Mantaflow baking per se. The project's real fixture (`fixtures._make_fluid_blend`
— a LIQUID domain, `bpy.ops.fluid.bake_all()` with a `selected_objects` override)
**bakes successfully headless on 4.2.9** (verified: config/data/mesh = 4/4/4 files,
identical to 5.2.3). The certified four-version matrix exercises real fluid bakes on
4.2 via the "HS fluid" tests. So fluid verification is tested on genuine 4.2 bakes,
not extrapolated from newer versions.

## SHIPPED (2026-11-18): fluid cache hash coverage

`cache_inspect.iter_fluid_cache_files` yields one record per domain STAGE (config,
data, and each enabled optional stage), discovering the actual files by the
verified per-stage filename patterns (`_FLUID_COMPONENT_RE`) rather than assuming
extensions. `iter_hashable_cache_files` chains point caches + fluid so capture and
verify share one source. Each manifest frame now also stores its frame NUMBER
(fluid filenames lack the point-cache `_NNNNNN_II` token). All B1–B7 protections
apply unchanged (per-stage independence, S_BAD_REF, missing/uncovered floors,
honest "unchanged ≠ valid"). Tested on real bakes across all four versions
(`hash_fluid_tests`): unchanged→PASS, changed-data→CHANGED (siblings PASS), deleted
mesh frame→blocking, relocation→unchanged, corrupted digest→BAD_REF, phantom
ref→missing+floor, cancellation→writes nothing.

## Build plan (GN — next)

1. `cache_inspect.iter_fluid_cache_files(scenes)` → one record per domain stage,
   with the stage's present files `(frame, abspath)` and `required` = domain
   cache range. Honest flags: stage-on-but-absent → uncovered/incomplete.
2. Fold fluid records into `cachehash.capture` / `verify` alongside point caches
   (shared SimVerify contract; same honest states, incl. S_INCOMPLETE_REF for a
   stage flag that's on but unbaked).
3. Explicit "unsupported"/"packed"/"replay" → UNKNOWN, never PASS.
4. Fixtures: a baked fluid domain (data+noise), corruption, a missing stage frame,
   multi-scene, relocation, cancellation. Then the four-version matrix + Windows CI.
5. GN disk bakes as a following step (packed stays "Couldn't verify").
