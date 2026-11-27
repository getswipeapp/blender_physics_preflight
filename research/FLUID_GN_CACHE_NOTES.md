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
- **Formats are now matched to the domain's configured setting (R9-1, 2026-11-21).**
  Established by real bakes (5.2.3): the `cache_data_format` setter accepts only
  `UNI`/`OPENVDB` (RAW is rejected — the `enum_items` introspection misleadingly lists
  `['UNI','OPENVDB','RAW']` for every `cache_*_format` prop, but the real accepted values
  differ per prop). OPENVDB data → `fluid_data_NNNN.vdb`; a UNI *liquid* data cache writes
  `pVel_NNNN.uni` and particle siblings — NOT `fluid_data_*.uni`. Mesh: `BOBJECT` →
  `.bobj.gz`, `OBJECT` → `.obj`. `cache_data_format`/`cache_mesh_format` exist on all four
  versions (default OPENVDB/BOBJECT). So `_fluid_component_re(stage, ds)` now builds the
  pattern from the configured format (`_FLUID_VOL_FMT_EXT`/`_FLUID_MESH_FMT_EXT`), falling
  back to the format-agnostic union when a format value is missing/unrecognised (never
  over-reject). A wrong-format file (a renamed `.vdb`→`.uni` on an OpenVDB domain) can no
  longer be counted as the required frame.
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
- 4.2.9's modifier API has **no `bake_target`** attribute — because **packed
  storage for simulation zones did not exist until Blender 4.3**. On 4.2 a GN sim
  bake is therefore **always written to disk**, driven by `mod.bake_directory`
  alone (the attribute exists on 4.2). Verified by real 4.2.9 bakes (probe
  `scratchpad/probe_gn_v3.py`): setting `mod.bake_directory = "//pbake"` and baking
  writes `//pbake/<bake_id>/meta/NNNNN_IIIII.json` + `blobs/NNNNN_IIIII.blob` —
  **byte-for-byte the same layout as 4.5/5.0/5.2**. So GN disk hashing applies on
  all four versions; it is NOT 4.2-excluded (review B2, 2026-11-20).

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

### Fluid review round 2 (2026-11-19) — B1/B2/M1, certified 4 versions

- **B1 — a configured stage with no files AND no baseline was silently skipped.**
  The verify loop's `saved is None and not cur` short-circuit `continue`'d, so an
  enabled-but-unbaked, never-baselined stage vanished from the report and the
  remaining stages could read as a complete verification. Now it reports
  `S_INCOMPLETE_REF` (every required frame uncovered → "Couldn't verify", never a
  PASS, and `verify_floor` floors the exit).
- **B2 — a fluid regression assertion contained `or True`** (always passed). Replaced
  with discriminating per-stage checks: the changed `data` stage finding is WARNING
  (never PASS) AND the `config` stage finding is still PASS (independence proven).
- **M1 — a FLUID-ONLY scene didn't show the #27 guidance.** `_has_disk_point_caches`
  only counted point caches, so on a scene with only a fluid bake the quick scan
  stayed silent instead of saying "hasn't been run / click Verify Cache Hashes".
  Renamed to `_has_hashable_disk_caches` (point OR non-replay fluid disk cache).

## SHIPPED (2026-11-19): Geometry Nodes disk-bake hash coverage

`cache_inspect.iter_gn_cache_files` yields, per GN **disk** bake, a `meta` record
(the `<frame>_<idx>.json` files, frame-indexed) and — only when the bake wrote blob
data — a `blobs` record (content files, `required=[]`). Added to
`iter_hashable_cache_files` and `_has_hashable_disk_caches`. Reuses the verified
`inspect_gn_bakes` logic (`_resolve_gn_target`, `bake_id`, the `<id>/meta/` +
`<id>/blobs/` layout).

Version handling (real bakes on all four):
- **PACKED (4.3+ default)** is NEVER hashed (no disk files) — it stays the existing
  honest "Couldn't verify"; a test asserts `iter_gn_cache_files` yields nothing for
  a packed bake, so packed is never mistaken for a missing disk cache.
- **4.5 / 5.0 / 5.2** expose `modifier.bake_target`; a DISK bake is detected
  (`_resolve_gn_target` follows INHERIT) and its meta/blobs are hashed.
- **4.2** has NO `modifier.bake_target` and no packed storage, so a sim bake is
  always disk and is hashed here like any other version (not excluded).

Gotcha found and handled: a simulation-zone bake item reports `bake_mode='STILL'`
with `frame_end=100` — those fields describe *Bake nodes*, not sim zones (the zone
bakes the scene range). So `_gn_bake_range` can't give the expected set for a sim
zone. #27 therefore uses the **contiguous span** of the frames present on disk as
the meta record's `required` (a sim bake runs contiguously from its start, so a
hole inside that span is a genuine missing frame); coverage beyond the observed
span stays #19/#20's job.

### GN review round 2 (2026-11-20) — B1/B2/M1, certified 4 versions

- **B1 — incomplete coverage could read as a clean PASS.** `required` was set to
  the frames *present on disk*, so a frame missing before baseline capture was
  simply never expected → an unqualified PASS. Fixed two ways: (1) `required` is now
  the **contiguous span** `min(present)..max(present)`, so an interior hole
  (frames 1,2,4 with 3 gone) is uncovered → `S_INCOMPLETE_REF` → "Couldn't verify"
  and floors a requested verify; (2) a disk bake with an **empty/missing meta
  directory** (or an unresolved directory) is no longer silently dropped — it is
  yielded with no coverage so a verify can't read clean.
- **B2 — Blender 4.2 disk bakes were wrongly excluded.** The code required
  `_resolve_gn_target == "DISK"`, which is never true on 4.2 (no `bake_target`), so
  all 4.2 GN hashing was disabled. Packed storage is a 4.3+ feature, so on 4.2 a sim
  bake is always disk. New `_gn_disk_status()` returns `'disk'` when no
  `bake_target` exists, so 4.2 disk bakes are detected and hashed (identical layout,
  verified by real 4.2 bakes).
- **M1 — real blob dependencies.** The old blob test injected a fabricated file.
  The fixture now bakes a **moving** sim (Set Position offset in the zone) so Blender
  writes genuine `blobs/NNNNN_IIIII.blob`. Real bakes reveal a dependency: the
  **first frame's blob holds the static topology/UVs** and every later frame's meta
  references it. #27 now derives the blob record from the **blob names the present
  meta actually reference** (`_gn_referenced_blob_names`), so deleting the shared
  first-frame blob surfaces as a missing dependency (floor), not a silent pass.

Tests (`hash_gn_tests`, real bakes, all four versions incl. 4.2): packed→not hashed
(where packable), disk bake produced, meta+blob records enumerated, unchanged→PASS,
changed meta→CHANGED, deleted meta frame→missing+floor, interior hole before
baseline→INCOMPLETE_REF (#27 UNKNOWN)+floor, empty meta dir→still enumerated,
changed real blob→CHANGED, missing first-frame dependency blob→missing+floor,
relocation→unchanged, cancellation→writes nothing.

### GN review round 3 (2026-11-20) — B3/B4, certified 4 versions

Two remaining coverage blockers after round 2, both about COMPLETENESS of
verification (not the SHA-256 maths):

- **B4 — a reliable expected frame range (head/tail completeness).** Round 2 used
  the **contiguous present span** `min(present)..max(present)`, which cannot see a
  first or last frame that was already absent when the baseline was captured (only
  3..6 present → span 3..6 → clean). **Research result (real bakes, all four
  versions):** the sim-zone range IS reliably recoverable — it is the **custom
  simulation frame range** when `use_custom_simulation_frame_range` is set, else the
  **scene frame range** (scene (3,8) baked frames 3..8; custom (2,4) baked 2..4). The
  misleading field is only `bake_mode`/`frame_end` (reports `STILL`/100 for a sim
  zone). The bake item's **`node.bl_idname`** reliably says which kind it is
  (`GeometryNodeSimulationOutput` vs `GeometryNodeBake`), so `_gn_expected_range()`
  honours `bake_mode` only for a real Bake node and uses custom-or-scene range for a
  sim zone. #27's `required` is now that range, so a missing HEAD or TAIL frame is
  uncovered → `S_INCOMPLETE_REF` → UNKNOWN + floor. `inspect_gn_bakes` (#19/#20) uses
  the same helper, so the structural checks no longer rely on the unreliable fields.
  When the range genuinely can't be established (an unknown future bake-node kind),
  it falls back to the present span and does not imply head/tail coverage.
- **B3 — blob identity collision.** Round 2 reduced required blob coverage to the
  bare **frame number** (`req_blobs.add(frame)`), so two blobs sharing a frame
  (`00001_00000.blob` + `00001_00001.blob`) collapsed to one; a sibling absent before
  baseline could hide behind a present same-frame blob and read as PASS. **Real bakes
  (all four versions) write exactly one blob per frame (index 0)** — every attribute
  is packed into it at byte offsets — but the filename scheme `(<frame>_<index>)`
  ALLOWS siblings, so coverage must be per exact file. `_gn_blob_coverage_key(frame,
  index)` now encodes the pair into one int (index 0 → the plain frame for natural
  display; index > 0 → a distinct key above the Blender frame ceiling), and `required`
  holds those keys. An adversarial fixture (a real bake whose first meta is edited to
  reference an absent `_00001` sibling) proves it: the present `_00000` blob matches,
  yet the absent sibling stays uncovered → `INCOMPLETE_REF` → floor.

### GN review round 3 CORRECTION (2026-11-20, re-review) — B4a/B3/paths, certified 4 versions

The re-review of the above found the round-3 fix incomplete. Verified every claim
with REAL bakes on all four versions before changing code:

- **B4a — scene-wide custom simulation range was ignored.** Blender ALSO has a
  **scene-level** `scene.use_custom_simulation_range` (+ `simulation_frame_start` /
  `simulation_frame_end`) that OVERRIDES the scene frame range for sim zones.
  **Verified real bake:** scene range 1–6 + scene sim range 1–8 → disk frames **1–8**
  (on 4.2/4.5/5.0/5.2). The old helper used only the scene range, so a tail frame
  beyond it (frame 8) could be deleted before baseline and still read PASS. Fixed
  precedence (`_scene_sim_range` + `_gn_expected_range`): **per-bake custom sim range >
  scene-wide custom sim range > scene range** (precedence also verified: per-bake 3–5
  wins over scene-sim 2–9 → frames 3–5). Discriminating test deletes frame 8.
- **B3 — the packed-int key still collided at frame 0.** `frame*10⁷+idx` mapped
  `00000_00001.blob` (0·10⁷+1 = 1) and `00001_00000.blob` (1) to the SAME key, so a
  present frame-1 blob could cover an absent frame-0 sibling. Replaced the int key with
  the blob's **exact filename STEM** (`"00000_00001"`) — a real per-file identity that
  can never collide, is JSON-safe, sorts stably, and displays meaningfully.
  `_frame_num` passes a str identity through for set-membership coverage. Discriminating
  test: inject an absent `00000_00001.blob` reference while `00001_00000.blob` is
  present → the sibling stays uncovered (`['00000_00001']`), present blob matched.
- **Bake nodes vs sim zones.** A STILL Bake node stores the **current frame at bake
  time**, NOT `frame_start` (verified: current 7, `frame_start` stayed 1), and it isn't
  in any readable property. So #27 now hashes **simulation zones only**; Bake nodes are
  skipped (never a false PASS) and surfaced by structural #17/#19. `_gn_expected_range`
  returns None for a STILL bake node and for unknown kinds.
- **Custom bake path layout.** A per-bake `use_custom_path` + `directory` writes files
  **directly** under it (`<dir>/meta`, NO `<bake_id>` subfolder — verified real bake);
  only the shared modifier `bake_directory` uses `<bake_dir>/<bake_id>/`. Both the
  hashing path and `inspect_gn_bakes` now resolve via `_gn_bake_cache_dir`, so a
  custom-path cache is read in the right place (was read as empty → false UNKNOWN).
  Discriminating test: a full custom-path bake verifies UNCHANGED → #27 PASS.

All four versions: 537 passed, 0 failed (4.2.9 / 4.5.9 / 5.0.1 / 5.2.3).

### GN review round 4 (2026-11-20, re-review of b6d9731) — R4-1 + hardening, certified 4 versions

Re-review confirmed B3/B4a/custom-path/bake-node closed and found one more coverage
path plus two hardening items:

- **R4-1 — JSON-escaped blob reference could be missed.** `_gn_referenced_blob_names`
  regexed the RAW meta text for `(\d{5,}_\d+)\.blob`. A reference written with a JSON
  Unicode escape (`"00004_00000.blob"`, which **decodes** to `00004_00000.blob`)
  would not match the literal `.blob`, so an absent escaped dependency could be dropped
  from the required set → false PASS. Real Blender writes literal `.blob` (verified), so
  this is adversarial/hand-edited metadata, but the fix is strictly safer: **parse the
  meta as JSON and read blob names from the DECODED string values** (blob refs live in
  `...data.name` fields — confirmed by a real meta dump), with a raw-text fallback only
  when the JSON won't parse (and the meta is separately flagged unreadable). Discriminating
  test injects an absent blob ref via `.` → enumerated → uncovered → UNKNOWN + floor.
- **Hardening — no optimistic present-span fallback.** When a sim zone's expected range
  can't be established (None, or an inverted custom range start>end), the enumerator no
  longer falls back to `min(present)..max(present)` (which could hide a head/tail gap);
  it yields NO coverage → "Couldn't verify", never a clean pass.
- **Hardening — custom-path test fails, not skips.** The custom-path capability exists on
  all four certified versions, so a bake producing no files is now a cert FAILURE, not a
  vacuous skip.

All four versions: 543 passed, 0 failed (4.2.9 / 4.5.9 / 5.0.1 / 5.2.3).

## History

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

## Round-10 fluid filename facts (verified on REAL bakes, 4.2.9 + 5.2.3)

Established by headless bakes (scratch probes probe_r10*.py) BEFORE coding, to fix
reviews R10-1 (mesh ext) and R10-2 (UNI data scheme) and the format hardening:

- **data OPENVDB** → one packed `fluid_data_NNNN.vdb` per frame.
- **data UNI** → SEVERAL per-grid files, NEVER `fluid_data_*.uni`:
  - LIQUID: `pVel_NNNN.uni`, `pp_NNNN.uni`, `vel_NNNN.uni`
  - GAS:    `density_NNNN.uni`, `flame_NNNN.uni`, `heat_NNNN.uni`, `shadow_NNNN.uni`, `vel_NNNN.uni`
  (the `cache_data_format` setter accepts only UNI / OPENVDB — RAW is rejected.)
- **mesh BOBJECT** → `fluid_mesh_NNNN.bobj.gz` ONLY (bare `.bobj` is never written).
- **mesh OBJECT**  → `fluid_mesh_NNNN.obj`. The mesh-format enum is only
  ('BOBJECT','OBJECT') — **STL is not a valid fluid mesh format** (setter rejects it).
- **noise** → ALWAYS `fluid_noise_NNNN.vdb`. `cache_noise_format` can be SET to UNI
  but DOES NOT change the files on disk (still VDB). So noise is format-independent.
- **particles** → ALWAYS `fluid_particles_NNNN.vdb`. `cache_particle_format`'s enum
  is only ('UNI',), it DEFAULTS TO '' (matches no enum), and it likewise does not
  change the files. So particles is format-independent too.
- **guiding** → packed `fluid_guiding_NNNN.vdb`. **config** → `config_NNNN.uni`.
- All extensions are written LOWER-CASE, deterministically.

Design consequences (cache_inspect._fluid_component_re):
- Only **data** and **mesh** consult a format property; config/noise/particles/guiding
  use FIXED patterns. (Consulting cache_particle_format was wrong — it defaults to ''
  and drove a permissive union fallback: the R10 hardening gap.)
- UNI data matches a bare Mantaflow grid name and EXCLUDES the reserved
  `fluid_<stage>_` prefixes, so a planted `fluid_data_NNNN.uni` (a renamed OpenVDB
  frame) can never count as UNI data coverage (R10-2).
- Patterns are now CASE-SENSITIVE (dropped re.IGNORECASE): an upper-case `.VDB` on a
  case-sensitive filesystem is not a real bake output and must not be counted.
- An UNRECOGNISED format value → NO matcher (matches nothing) → required frames read
  as uncovered → UNKNOWN, never a permissive guess (UNKNOWN-over-false-PASS).

All four versions after the fix: 636 passed, 0 failed (4.2.9 / 4.5.9 / 5.0.1 / 5.2.3).

## Round-11 UNI data per-grid coverage (verified on REAL bakes, all four versions)

UNI data is MULTI-FILE: each frame is SEVERAL per-grid `.uni` files, and WHICH grids a
genuine bake writes is fixed by the domain type. Enumerated on real headless bakes of
4.2.9 / 4.5.9 / 5.0.1 / 5.2.3, IDENTICAL across minimal / secondary-particles / mesh /
smoke / fire configs:

- **LIQUID** data grids = `pVel_NNNN.uni`, `pp_NNNN.uni`, `vel_NNNN.uni` (exactly these
  three in every tested config; secondary particles add a separate `particles/` stage,
  not data grids; `mesh` is its own stage).
- **GAS** data grids = `density_NNNN.uni`, `flame_NNNN.uni`, `heat_NNNN.uni`,
  `shadow_NNNN.uni`, `vel_NNNN.uni` (identical for smoke-only AND fire — the domain
  allocates flame/heat regardless of the flow type).

Design consequence (review R11-1):
- Coverage keyed on the bare integer frame let a surviving sibling grid (pp/vel) — or a
  planted `junk_NNNN.uni` — stand in for a DELETED required grid (pVel) and read as a
  clean PASS. The fix mirrors the GN-blob B3 pattern: a per-`(frame, grid)` string
  coverage token (`"0003/pVel"`) that never collapses.
- `required` for a UNI data stage is the PRODUCT `frames × core-grids` (every core grid
  per frame), so a missing core grid is `uncovered` → `S_INCOMPLETE_REF` → #27 UNKNOWN,
  even though its siblings still match.
- The matcher counts ONLY a KNOWN core grid for the domain type; a foreign name
  (`junk_0003.uni`) is not matched at all, so it can neither cover a required grid nor be
  captured. An uncharacterised domain type → a lone unbaselinable sentinel in `required`
  → UNKNOWN, never an optimistic PASS.
- A genuine untouched UNI bake has every core grid per frame → PASS (control test).

All four versions after the fix: 658 passed, 0 failed (4.2.9 / 4.5.9 / 5.0.1 / 5.2.3).

## Round-12 UNI data OPTIONAL grids: colored smoke + resumable (verified on REAL bakes, all four versions)

Review R12-1: the R11 per-grid coverage required only the FIXED core grids, and the
matcher's grid-name class `[A-Za-z0-9]*` REJECTED any underscore name. So two kinds of
real grid were invisible to capture AND verification — a deleted one read as a clean PASS:

- **Colored smoke** (a SMOKE flow with a non-default `smoke_color`) writes THREE extra
  data grids every frame: `color_r_NNNN.uni`, `color_g_NNNN.uni`, `color_b_NNNN.uni`.
  Plain smoke and fire-only write NONE of them. Identical on 4.2.9 / 4.5.9 / 5.0.1 / 5.2.3.
- **Resumable cache** (`ds.cache_resumable = True`) writes a larger restart-state family
  every frame: `densityIn, emission, flags, fuel, fuelIn, heatIn, phiIn, phiObs, phiOut,
  react, reactIn, velTmp` (GAS) / `flags, phi, phiIn, phiObs, phiOut, phiParts, phiTmp,
  velTmp` (LIQUID), plus `color_*_in` when also colored. Absent when resumable is off.

Design consequence (config/version-robust, no hardcoded optional-grid whitelist):
- The grid-name regex now allows underscores (`[A-Za-z][A-Za-z0-9_]*`), so color_r /
  color_r_in / densityIn files are captured and hashed. Reserved-prefix masquerades
  (`fluid_<stage>_`) stay rejected by the negative lookahead (R10-2).
- The required set = MANDATORY core (per domain type) UNION the OPTIONAL grids the bake
  ACTUALLY wrote (observed in the data dir, union across frames), each required at EVERY
  frame. Deriving the optional requirement from the bake itself catches a deleted optional
  grid WITHOUT forcing UNKNOWN on a bake that simply has none of them (plain smoke PASSES).
- Color is required as a SET: present any of color_r/g/b and all three are required, so a
  single deleted channel can't hide behind its two siblings.
- The coverage token is still per-(frame, grid) (`0003/color_r`), so a sibling/foreign/
  cross-domain file can only ever cover its OWN identity, never a required grid (R11-1).
- Residual (documented, not a false PASS): deleting an ENTIRE optional family (all of
  color_r/g/b, or all restart grids) across ALL frames BEFORE baseline is indistinguishable
  from a bake that never had it — the mandatory core still verifies. The single-file
  deletion attack (the review's scenario) is caught.

Tests added (real bakes, all four versions): plain-smoke control (#27 PASS, no false
UNKNOWN); untouched colored control (#27 PASS); delete color_r_0003 before baseline →
`0003/color_r` uncovered, siblings matched, #27 UNKNOWN, requested-verify floor 2;
untouched resumable control (#27 PASS); delete one restart grid frame → uncovered → UNKNOWN.

All four versions after the fix: 681 passed, 0 failed (4.2.9 / 4.5.9 / 5.0.1 / 5.2.3).

## Round-13 UNI data: ENTIRE optional family deleted before baseline (config anchor, all four versions)

Review R13-1: the R12 observed-from-disk union catches a SINGLE deleted optional file
(siblings survive to mark the family present), but deleting an ENTIRE optional family
across ALL frames BEFORE baseline leaves no on-disk evidence, so the union required only
the core grids -> #27 PASS. Fixed by anchoring the required set to DOMAIN CONFIG (which
deleting cache files can't erase), established from real bakes on all four versions:

- **Colour has NO domain-level flag.** The only signal is the FLOW: a SMOKE or BOTH flow
  writes color_r/g/b IFF its `smoke_color` != the default grey `(0.7, 0.7, 0.7)` (ANY
  deviation turns colour on; exactly the default does not — identical on 4.2.9 / 4.5.9 /
  5.0.1 / 5.2.3). `_scene_has_colored_smoke_flow(scene)` reports this SCENE-WIDE: flows
  aren't linked in RNA to a domain, so it can only OVER-report colour (a safe false
  UNKNOWN on a mixed multi-domain scene), NEVER under-report (which would reintroduce the
  false PASS). Colour is required (gas only) as the full {r,g,b} SET whenever the scene
  configures colour — so even all-colour-deleted reads UNKNOWN. Fire-only flows don't
  emit colour, so only SMOKE/BOTH count.
- **Resumable** is a clean per-domain boolean (`ds.cache_resumable`). A genuine resumable
  bake always writes restart-state grids; we DON'T enumerate them (version-fragile).
  Instead, if resumable is on but NO restart grid (observed − core − colour) is on disk,
  the family was wiped -> a lone unbaselinable sentinel `?/resumable-restart-wiped` forces
  UNKNOWN.

False-UNKNOWN guard: a plain bake (no coloured flow, not resumable) expects neither
family, so it still PASSES. Colour is gas-only (never required on a liquid domain). A
genuine colored/resumable bake has the families present -> PASS.

Tests added (real bakes, all four versions): delete ALL color_r/g/b before baseline ->
colour tokens uncovered, #27 UNKNOWN, floor 2; delete the ENTIRE restart family before
baseline -> restart sentinel uncovered, #27 UNKNOWN, floor 2; untouched plain / colored /
resumable bakes still PASS; plus matcher-unit assertions for expects_color (gas-only) and
the resumable sentinel.

All four versions after the fix: 695 passed, 0 failed (4.2.9 / 4.5.9 / 5.0.1 / 5.2.3).

## Round 14 — restart family required by name; colour trigger re-verified (R14-1 / R14-2)

Independent review of `c0e864b` raised two source-level claims. Both were taken back to
REAL bakes on all four versions (4.2.9 / 4.5.9 / 5.0.1 / 5.2.3) before any code change.

### R14-1 — "domain `flame_smoke_color` / fire activates colour grids" — NOT REPRODUCED
Probed every plausible colour-activation path on all four versions. Only a SMOKE or BOTH
FLOW with a non-default `smoke_color` writes `color_r/g/b`:

| config                                                        | color grids? |
| ------------------------------------------------------------- | ------------ |
| SMOKE flow, default grey (0.7,0.7,0.7)                        | no           |
| SMOKE flow, non-default smoke_color                          | **yes**      |
| BOTH flow, non-default smoke_color                          | **yes**      |
| FIRE flow only                                               | no           |
| FIRE flow + domain `flame_smoke_color` changed              | **no**       |
| FIRE flow with its OWN non-default `smoke_color`            | **no**       |

`flame_smoke_color` exists on the domain on all four versions but is a flame-shading
colour, NOT a transported colour field — it writes no `color_*` grids. So the existing
`_scene_has_colored_smoke_flow` (keys on SMOKE/BOTH `smoke_color`) is already complete for
the real trigger; requiring colour for fire/flame would be a false UNKNOWN. R14-1 is a
false finding. Pinned by matcher-unit tests (fire / flame / default grey -> not colour;
SMOKE / BOTH non-default -> colour).

### R14-2 — a planted file could pose as restart evidence — CONFIRMED, FIXED
The round-13 check treated "any observed grid outside core+colour" as proof the restart
family exists, so a planted `junk_NNNN.uni` (or a single surviving restart grid) hid a
wiped family and read PASS.

Fix: require the restart family BY NAME. The restart-state grids a resumable bake writes
are IDENTICAL on all four versions, so they can be required as a fixed set per domain:
- GAS: densityIn, emission, flags, fuel, fuelIn, heatIn, phiIn, phiObs, phiOut, react,
  reactIn, velTmp
- LIQUID: flags, phi, phiIn, phiObs, phiOut, phiParts, phiTmp, velTmp

When `cache_resumable` is on, `_fluid_stage_required` adds the whole named set to the
required per-(frame,grid) tokens (`_FLUID_UNI_RESTART_GRIDS` / `_uni_restart_grids`). An
entire family wiped -> all uncovered -> UNKNOWN; a planted junk grid is not in the set, so
it's ignored as evidence; a family wiped down to one surviving grid still leaves the rest
uncovered -> UNKNOWN. A genuine resumable bake has every restart grid on disk -> covered ->
PASS (no false UNKNOWN). The gas+colour restart grids color_*_in are driven by the colour
config, so a wiped colour family is still caught by the colour requirement. The old
`?/resumable-restart-wiped` sentinel remains only as a fallback for an uncharacterised
domain (never reached by GAS/LIQUID).

Tests added (real bakes): junk-spoof (delete the whole restart family, plant junk for every
frame) -> named restart tokens uncovered, #27 UNKNOWN, floor 2; keep-one (delete all restart
grids except velTmp) -> the rest uncovered, #27 UNKNOWN; the round-13 whole-family-wipe test
now asserts named restart tokens (not the retired sentinel); untouched resumable still PASS.

All four versions after the fix: 708 passed, 0 failed (4.2.9 / 4.5.9 / 5.0.1 / 5.2.3).

## Round 15 — flame-triggered colour (R14-1, now real) + colour-restart grids (R15-1)

Re-review of b804b28 pressed on two points. Both taken back to REAL bakes on all four
versions (4.2.9 / 4.5.9 / 5.0.1 / 5.2.3) before coding.

### R14-1 — fire + non-default domain flame_smoke_color DOES write colour — CONFIRMED, FIXED
Round 14 dismissed R14-1 after probing fire-ONLY configs (no smoke flow), which write no
colour. The reviewer asked for the precise combination the earlier probes missed: a smoke
flow PRESENT + fire + a non-default domain `flame_smoke_color`. That combination DOES write
color_r/g/b on all four versions:

| config                                                              | color grids? |
| ------------------------------------------------------------------- | ------------ |
| default-grey SMOKE flow + FIRE flow, domain flame default           | no           |
| default-grey SMOKE flow + FIRE flow, domain flame NON-default       | **yes**      |
| single BOTH flow (default smoke_color), domain flame NON-default     | **yes** (all 4, incl. 4.2.9) |
| FIRE flow ALONE (no smoke flow), domain flame NON-default           | no           |

Mechanism: the burnt smoke carries the flame colour; when a smoke source is also present and
the flame colour differs, the domain holds two distinct smoke colours and Mantaflow writes
the colour grids. Fire alone (one uniform colour) writes none.

Fix: `_scene_has_colored_smoke_flow` -> `_scene_expects_fluid_color`. Colour is expected when
EITHER a SMOKE/BOTH flow has a non-default smoke_color, OR (a smoke source exists AND fire
exists AND a GAS domain's flame_smoke_color is non-default). Still scene-wide and
over-report-only (never under-report). Verified by a real BOTH-flow + flame bake (bakes
reliably headless on 4.2.9, unlike two separate smoke+fire flows) and by matcher-unit tests
covering every row above plus the no-fire and flame-default negatives.

### R15-1 — colour-restart grids color_*_in — CONFIRMED, FIXED
A cache that is BOTH coloured AND resumable writes color_r_in/color_g_in/color_b_in
(verified all four versions). Round 14 left them out of the mandatory sets, so deleting the
whole _in family before baseline (keeping color_r/g/b and the base restart grids) read PASS.

Fix: `_FLUID_UNI_COLOR_RESTART_GRIDS = (color_r_in, color_g_in, color_b_in)`. In
`_fluid_stage_required`, when a gas domain is resumable AND colour is expected (or any colour
/ colour-restart grid is observed), require the whole _in SET. A wiped _in family -> uncovered
-> UNKNOWN; a genuine coloured+resumable bake has them -> PASS; a plain resumable or a
non-resumable coloured bake never requires them (no false UNKNOWN).

Tests added (real bakes): fire+flame colour bake -> wipe colour -> #27 UNKNOWN, floor 2,
untouched control PASS; coloured+resumable bake -> wipe ALL color_*_in -> #27 UNKNOWN, floor
2, untouched control PASS; matcher-unit colour-restart and flame-path assertions.

All four versions after the fix: 728 passed, 0 failed (4.2.9 / 4.5.9 / 5.0.1 / 5.2.3).

## Round 16 — float32 colour comparison (R16-1)

Re-review of e0404df accepted R14-1 and R15-1 and raised a precision gap.

### R16-1 — small colour changes evaded detection — CONFIRMED, FIXED
`_color_is_noncat` rounded each RGB component to 4 decimals before comparing to the default
grey, but Blender compares colours in float32 exactly. Verified on REAL bakes, all four
versions (4.2.9 / 4.5.9 / 5.0.1 / 5.2.3):

| colour source                                   | writes colour? | old detector |
| ----------------------------------------------- | -------------- | ------------ |
| flame_smoke_color = (0.70001, 0.7, 0.7) + fire  | **yes**        | saw default (false PASS) |
| smoke_color       = (0.70001, 0.7, 0.7)         | **yes**        | saw default (false PASS) |
| flame/smoke = exact default (0.7, 0.7, 0.7)     | no             | default      |

Precision facts (identical on all four versions): the stored default reads back as
float32(0.7) = 0.699999988079071 (NOT Python's 0.7); 0.70001 stores as 0.7000100016593933,
a distinct float32. A float64 `!= 0.7` comparison would therefore flag EVERY genuine default
bake as colour -> false UNKNOWN (the trap the reviewer flagged).

Fix: `_f32(x)` rounds to the 32-bit representation (via struct pack/unpack), and
`_color_is_noncat` returns True iff any component's float32 differs from
`_FLUID_SMOKE_COLOR_DEFAULT_F32 = float32(0.7)`. Because RNA already returns the stored
float32 (promoted to float64), `_f32` round-trips it idempotently, so the detector now makes
EXACTLY the comparison Blender makes: 0.70001 -> colour required; the genuine default ->
not. No rounding, no false UNKNOWN.

Tests added (real bakes): a flame bake one float32 step off default (0.70001) -> colour
written, wipe colour -> #27 UNKNOWN, floor 2, untouched control PASS; a genuine default bake
-> #27 PASS (float32 default not flagged). Matcher-unit: 0.70001 non-default; exact default
and stored-float32(0.7) NOT flagged; 0.5 non-default; tiny-deviation scene detector cases.

All four versions after the fix: 741 passed, 0 failed (4.2.9 / 4.5.9 / 5.0.1 / 5.2.3).

================================================================================
ROUND 17 — CERTIFICATION GATE INTEGRITY (false-green on Blender 4.2.9)
================================================================================

DISCOVERY (while verifying the R16-1 boundary-test note). The "all four versions
pass" claim was FALSE for Blender 4.2.9 — on BOTH macOS-local and Windows CI. The
headless suite aborted inside hash_fluid_tests() at the first fluid fixture
(build_fluid_uni_gas_plain -> _make_gas_uni_blend -> wm.save_as_mainfile), with:

    AttributeError: 'NoneType' object has no attribute 'getDataPointer'
    SystemError: <bpy_func ViewLayer.update()> returned a result with an exception set

Blender then EXITED CODE 0 despite the traceback. Both gates trusted that exit
code (run_all_versions.sh printed ">> OK on Blender 4.2"; windows-cert.yml logged
"Suite exit code: 0"), so a crashed, half-run suite was scored as a pass. No
"Blender 4.2.9 LTS | N passed" summary line was ever printed on 4.2.9. Confirmed
on clean committed HEAD (1c0bb02/5834203), i.e. pre-existing — NOT caused by the
R16-1 boundary tests. Consequence: the fluid hardening R12-1..R16-1 had never
actually executed on 4.2.9 anywhere; 4.5.9/5.0.1/5.2.3 genuinely reached their
summaries. Owner decision: fix the certification system properly (Option 1).

ROOT CAUSE of the 4.2.9 crash. Saving a .blend whose FLUID domain has not been
depsgraph-evaluated triggers a null-pointer deref in the save-time
ViewLayer.update() on Blender 4.2.x headless. FIX: force one depsgraph
evaluation before the save. New fixtures._save_fluid_mainfile(blend) calls
bpy.context.evaluated_depsgraph_get() then wm.save_as_mainfile; applied to every
fluid-domain save site (_make_fluid_blend, _make_gas_uni_blend,
_make_gas_uni_flame_blend, _make_fluid_guide_blend, build_22_fail, build_21_fail).

EVIDENCE — strategy probe on 4.2.9, each run as the sole/first bake in a fresh
process (the crash is first-bake sensitive):
    strategy     outcome
    none         0/3  OK   (3/3 crash)            <- current behaviour
    view_layer.update() before save   1/3 OK      (flaky)
    evaluated_depsgraph_get() before save  3/3 OK  <- chosen
    both (vlupdate+depsgraph)         1/3 OK       (flaky)
    retry-6x around whole build       2/3 OK       (flaky; can exhaust)
Confirmation at higher N with the depsgraph fix: 10/10 OK (SMOKE, 20 files) and
6/6 OK (BOTH flow + non-default flame, 32 files incl. colour grids) = 19/19 clean,
0 crashes. Harmless on 4.5/5.0/5.2.

SECOND BUG (source-confirmed by the reviewer). run_tests.py main() called every
test-group function a SECOND time just to compute `total` (len(...)), re-running —
and re-baking — hash_fluid_tests()/hash_gn_tests() etc. FIX: assemble each group's
results exactly ONCE into `unit_results`; total = len(CASES)+len(CACHE_REGRESSION)
+len(unit_results). Each group is now wrapped so an exception becomes a single
recorded FAILURE (never a silent abort, never a double run).

GATE HARDENING (fail-closed, both platforms). run_tests.py now prints a
machine-readable completion sentinel ONLY if main() runs to the end:
    SUITE_DONE version=<x.y.z> passed=N failed=M total=T consistent=yes|no ok=yes|no
(version token is the numeric tuple, space-free, so it parses). New shared
checker tests/gate_check.py (evaluate_log + CLI) returns PASS only if: the
sentinel is present, failed==0, passed+failed==total, total>=floor, no crash
signature ("Traceback (most recent call last)", "getDataPointer",
"ViewLayer.update()> returned a result with an exception" — all verified ABSENT
from clean passing runs), the human "N passed, M failed, T total" summary line is
present, and the process exit code (when supplied) is 0. Both gates now call it
instead of trusting the exit code; run_all_versions.sh additionally requires all
four versions to report the SAME total (catches a silently short/incomplete run).

FAIL-CLOSED REGRESSION (gate_selfcheck_tests, runs on all four versions): proves
gate_check REJECTS a crash-that-exited-0, a missing sentinel, a crash signature
over a passing sentinel, a recorded failure, an inconsistent count, a short count
below the floor, a nonzero exit code, and a missing summary line — and ACCEPTS a
genuine complete all-pass log. Also verified live: the hardened gate rejects the
real pre-fix 4.2.9 crash log (rc=1).

RESULT. First genuine completion on 4.2.9 of the fluid tests. All four versions
now reach their summary AND sentinel: 754 passed, 0 failed, 754 total
(4.2.9 / 4.5.9 / 5.0.1 / 5.2.3); counts equal; gate verified completion, not exit
codes. (754 = 745 after the R16-1 boundary tests + 9 gate_selfcheck assertions.)
Prior rounds' "4.2.9 verified" claims are retroactively INVALID and must not be
relied on; 4.2.9 fluid coverage is validated for the first time here.

ROUND 18 — CERTIFICATION GATE INTEGRITY, PART 2 (independent review of 53c8b3d)
==============================================================================
The independent re-review of the R17 commit (53c8b3d) returned PARTIAL PASS: the
historical crash-with-exit-0 loophole and the duplicate-execution bug were
accepted as fixed, but three certification safeguards were still missing. All
three are source-confirmed and are fixed here.

R18-1 — Incomplete tests could still pass.
  Before: the gate accepted any completed, internally consistent run whose total
  was merely >= a 700 floor. If a group silently shrank or vanished (the review's
  example: the nine gate_selfcheck assertions disappearing -> 745/745), the run
  still passed, and all four versions sharing the same reduced count did not
  reveal it.
  Fix: run_tests.py now declares an INDEPENDENT inventory as fixed literals —
  EXPECTED_CASES (82), EXPECTED_CACHE_REGRESSION (8), and a per-group
  EXPECTED_GROUP_COUNTS manifest (25 groups) — never derived from the live run.
  main() prints GROUP_COUNT per group and an INVENTORY line, and fails closed if
  any group's count, the CASES/CACHE_REGRESSION lengths, or the grand total
  disagree with the declaration. The declared total is emitted in the sentinel as
  `expected=`, and gate_check.evaluate_log independently rejects total!=expected
  and passed!=expected — so a complete-but-short run is caught both by the suite
  and, defensively, by the gate reading the log. bpy.app.version gates no test
  count, so every version must produce exactly these numbers; a version that
  differs fails closed and names the offending group. Re-baseline after an
  intended change with FAILSAFE_MEASURE=1 (prints the numbers without enforcing).

R18-2 — Blender version identity was not enforced.
  gate_check supported --version but neither gate passed it, so a matrix slot
  could run the wrong Blender build and still pass.
  Fix: tests/run_all_versions.sh carries the exact expected full version per slot
  (4.2.9 / 4.5.9 / 5.0.1 / 5.2.3) and passes --version; windows-cert.yml passes
  --version "${{ matrix.version }}" on the headless step. The sentinel version
  token must match or the slot fails.

R18-3 — The Windows proof steps still trusted the process exit code.
  The REAL multi-process batch proof (and the functional acceptance step) gated
  only on Blender's exit code, which is 0 even after a Python crash — so a script
  that crashed before printing its verdict could pass.
  Fix: gate_check gained require_marker(text, marker, forbidden, exit_code): PASS
  only if the exact success marker is present, no crash signature or forbidden
  marker appears, and the exit code is 0. windows-cert.yml routes the real-batch
  step through it (--marker "REAL BATCH PROOF: ALL CHECKS PASSED"
  --forbid "REAL BATCH PROOF: FAILED") and the acceptance step through it
  (--marker ", 0 failed," --forbid "FAIL -").

Deliberate fail-closed regressions (owner directive, carried from R17): the
in-suite gate_selfcheck_tests group grew from 9 to 18 assertions, adding live
proofs that gate_check REJECTS a short inventory (745 vs declared 754/763-style),
ACCEPTS/REJECTS on version match/mismatch, and — via require_marker — ACCEPTS a
genuine proof marker while REJECTING a crash-before-marker (exit 0), a FAILED
marker, a good marker with nonzero exit, and a missing marker. These 18 run on
all four versions as part of the suite.

RESULT: hardened suite + gates. Mac matrix: 4.2.9 / 4.5.9 / 5.0.1 / 5.2.3 each
763 passed, 0 failed, total=763, expected=763, consistent=yes, ok=yes; versions
enforced; counts equal; GATE PASS per version; release gate PASS. (763 = 754 +
9 new gate_selfcheck assertions.) Clean per-version gate proofs on the real
4.2.9 log: correct version -> GATE PASS; a fabricated short inventory
(750 vs expected 763) -> GATE FAIL; version 9.9.9 -> GATE FAIL. Windows CI:
pending re-run on this commit. Independent review of the corrected commit is
still required before certification is claimed restored. No merge, publication,
or spending.

ROUND 19 — CERTIFICATION GATE INTEGRITY, PART 3 (independent review of d5bec36)
==============================================================================
The independent re-review of d5bec36 returned PARTIAL PASS: R18-1/2/3 accepted in
normal mode, but two residual ways to certify a shortened run were found. Both
are source-confirmed and fixed here.

R19-1 — Measurement mode could disable certification.
  Before: FAILSAFE_MEASURE=1 printed a SUITE_DONE WITHOUT expected=, and
  gate_check accepted a sentinel with no expected= (backward-compat). So a short
  measurement run above the 700 floor could be read as a pass.
  Fix: (a) measurement mode no longer emits SUITE_DONE at all — it prints
  SUITE_MEASURE_ONLY with an explicit "NOT certifiable" note; (b) gate_check now
  REQUIRES expected= on any certifiable sentinel (a missing declaration is fatal)
  AND rejects outright on any MEASURE_MARKERS ("SUITE_MEASURE_ONLY"/
  "ACCEPT_MEASURE_ONLY"). Measurement stays possible for re-baselining; it simply
  cannot certify. Proven on a REAL 5.2.3 measurement run: emits
  SUITE_MEASURE_ONLY -> GATE FAIL; and on a real 4.2.9 log with expected= stripped
  -> GATE FAIL ("no expected= inventory declaration").

R19-2 — Windows acceptance could pass with missing tests.
  Before: the acceptance step gated only on the ", 0 failed," marker, so a
  "0 passed, 0 failed, 0 total" run (e.g. an early-return) with exit 0 satisfied
  it. Acceptance had no independent expected count.
  Fix: certification/ci/win_acceptance.py declares EXPECTED_ACCEPT_CHECKS=25 (its
  success-path check count) and emits an ACCEPT_DONE sentinel with expected=;
  _finish() sets ok=no unless failed==0, the count is consistent, and
  total==25. windows-cert.yml gates the acceptance step with
  gate_check.py --sentinel ACCEPT_DONE --min-total 25 --version 5.2.3 (same
  fixed-inventory verdict as the main suite). A 0/0/0 or short acceptance run is
  rejected.

Regressions: gate_selfcheck_tests grew 18 -> 24, adding live proofs that
gate_check REJECTS a missing expected=, REJECTS measurement-mode output, lets a
measurement marker void an otherwise-good sentinel, ACCEPTS a genuine 25/25
acceptance run (ACCEPT_DONE), and REJECTS a 0/0/0 and a 1-of-25 acceptance run.
These 24 run on all four versions. Also updated the crafted REJECT strings to
carry expected= so each is rejected for its specific defect, not merely for the
new missing-expected rule.

RESULT: Mac matrix 4.2.9/4.5.9/5.0.1/5.2.3 each 769 passed, 0 failed, total=769,
expected=769, consistent=yes, ok=yes; versions enforced; counts equal; GATE PASS
per version; release gate PASS. (769 = 763 + 6 new gate_selfcheck assertions.)
Real-log proofs: control 4.2.9 -> GATE PASS; measurement-mode 5.2.3 ->
GATE FAIL; expected= stripped -> GATE FAIL; acceptance 0/0/0 -> GATE FAIL.
Windows CI: pending re-run on this commit (also exercises the live ACCEPT_DONE
count on Windows). Independent review of the corrected commit still required
before certification is claimed restored. No merge, publication, or spending.

ROUND 20 — CERTIFICATION GATE INTEGRITY, PART 4 (independent review of e5c7ca6)
==============================================================================
The independent re-review of e5c7ca6 returned PARTIAL PASS: R19-1/R19-2 accepted,
but one more exit-code-trusting gap remained — inside a Windows acceptance test.

R20-1 — A failed CLI scan child could count as a successful test.
  Source: certification/ci/win_acceptance.py. The clean-scan acceptance check was
  `cli_exit(["--text"]) == 0` — it trusted ONLY the child Blender's exit code,
  never whether the child produced a real report. REPRODUCED on real Blender
  (5.2.3, macOS): `blender -b --factory-startup --python-expr "raise
  RuntimeError('boom')"` EXITS 0, and a child that merely `sys.exit(0)` without
  scanning also exits 0. So a crashed/short CLI child would have scored the check
  PASS, all 26 acceptance checks could pass, and ACCEPT_DONE ok=yes would be
  emitted — the same exit-0-after-crash class this whole effort began with.
  Fix:
  * tests/gate_check.py gains valid_cli_report(returncode, text,
    expected_checks=27): PASS only if exit==0 AND the output is a complete, valid
    Failsafe JSON report — rejects empty output, any crash signature, a "Failsafe
    internal error" report, malformed JSON, a wrong check count (incomplete), a
    missing summary, or an error-carrying report.
  * win_acceptance.py now runs the scanner in a real child with `--json`, captures
    the report (and the CLI's own exit code) to a file, and gates it with
    valid_cli_report instead of the bare exit code. It also adds a REAL
    child-failure repro: a child that exits 0 with no report, asserted REJECTED by
    the same gate. EXPECTED_ACCEPT_CHECKS 25 -> 26.
  * 8 validator regressions added to gate_selfcheck_tests (run on all four
    versions): a genuine 27-check exit-0 report ACCEPTED; exit!=0, empty,
    traceback, "internal error", malformed JSON, 26-check incomplete, and
    no-summary each REJECTED.

The CLI's own run() is already defensive (its except returns EXIT_USAGE + an
error report, not exit 0), so the real exposure was a child crashing OUTSIDE
run() (Blender-level) while exiting 0; content validation defeats that regardless
of the exit code.

RESULT: Mac matrix 4.2.9/4.5.9/5.0.1/5.2.3 each 777 passed, 0 failed, total=777,
expected=777, ok=yes; versions enforced; equal; GATE PASS; release gate PASS.
(777 = 769 + 8 new gate_selfcheck assertions.) Real repro: a raising / no-report
--python-expr child exits 0, and valid_cli_report rejects it while accepting a
genuine 27-check scan. Windows CI: pending re-run on this commit (exercises the
live 26-check acceptance incl. the real CLI child-failure repro). Independent
review of the corrected commit still required before certification is claimed
restored. No merge, publication, or spending.

================================================================================
ROUND 21 — independent review of commit 1f746a8 (branch failsafe-expanded-hardening)
================================================================================
Verdict returned: PARTIAL PASS. R20-1 (empty/missing report) accepted; the
777-test and 26-check inventories intact; Windows CI 45292144064 SUCCESS. Two new
source-traced blockers, both confirmed against the real source and reproduced on
real Blender before fixing.

R21-1 — cli_json_child() discarded the child's REAL process result.
  In win_acceptance.py the clean-scan helper read back only the child-WRITTEN
  report + ".code" sidecar and ignored subprocess.run()'s returncode, stdout and
  stderr. A child that writes a valid report + code=0 and then raises leaves a
  traceback ONLY on stderr; Blender still exits 0. REPRODUCED on real Blender
  5.2.3: such a child has real returncode 0 AND stderr contains
  "Traceback (most recent call last)". The sidecar-only check accepted it.
  Fix:
  * cli_json_child now captures subprocess.run()'s real returncode and combined
    stdout+stderr and returns them; the clean-scan gate is fed the REAL exit code
    (not the sidecar), the sidecar is cross-checked for AGREEMENT with it, and
    gate_check scans the child's stderr for crash signatures too.
  * gate_check.valid_cli_report gains child_stderr= and declared_code=: a crash
    signature in stderr, or a child-declared code that disagrees with the real
    process exit, is a hard rejection.
  * New acceptance repro: a child that writes a valid report + code=0 then raises
    is asserted REJECTED (caught on the stderr traceback), proving the sidecar can
    no longer stand in for the real outcome.

R21-2 — "27 listed checks" never proved "27 checks executed".
  report.build_json_report() iterates the 27 REGISTERED check metas and emits one
  entry each regardless of results; a check with no result is "NOT APPLICABLE".
  So engine.run_all() returning [] yields a 27-entry, all-"NOT APPLICABLE",
  exit-0 report. REPRODUCED on real Blender: monkeypatching run_all->[] produces
  exactly that (overall PASS, exit 0). Critically, the OLD acceptance "clean scan"
  scanned the empty default startup scene, which is ALSO all-N/A — so it carried
  ZERO execution evidence and was indistinguishable from the attack.
  Fix:
  * valid_cli_report now requires >= min_executed (default 1) checks with a real
    (non-"NOT APPLICABLE") verdict, and cross-checks that the summary's non-N/A
    tally matches the checks array (a forged summary cannot fake execution).
    Legitimate individual N/A results are preserved; only the all-N/A case fails.
  * The acceptance clean-scan now OPENS the real saved cloth fixture before
    scanning, so checks genuinely execute (observed: 6 executed / 7 findings,
    verdict WARNING=exit 2). A defined scan verdict (0/1/2) with execution
    evidence + a complete report + no crash signature is the proof; the exit code
    is only a cross-check. EXPECTED_ACCEPT_CHECKS 26 -> 28.
  * New acceptance repro: a child with run_all->[] (all-N/A, exit 0) is asserted
    REJECTED for lack of execution evidence.

A _safe() scrubber in win_acceptance redacts crash-signature substrings from the
printed diagnostics, so a PASSING crash-regression (which must report that it
found a traceback) can no longer plant that substring in the acceptance log where
the gate's own log-level crash scan would then falsely reject the run.

In-suite: 6 new gate_selfcheck_tests regressions (run on all four versions) cover
all-N/A rejection, single-executed acceptance, the forged-summary integrity
cross-check, declared-vs-real exit disagreement, a stderr-only traceback, and an
executed nonzero verdict accepted. gate_selfcheck_tests 32 -> 38; suite total
777 -> 783 (= 769 + 14 CLI-report regressions across R20+R21).

RESULT (R21): Mac matrix 4.2.9/4.5.9/5.0.1/5.2.3 each 783 passed, 0 failed,
total=783, expected=783, ok=yes; versions enforced; equal; GATE PASS; release
gate PASS. win_acceptance.py run end-to-end on real Blender 5.2.3 (installed
extension): 28/28, ACCEPT_DONE expected=28 ok=yes, gate PASS, with the real
fixture scan ACCEPTED (executed=6, findings=7, verdict exit 2) and all three
adversarial children (no-report, crash-after-write, run_all->[]) REJECTED.
Windows CI: pending re-run on this commit. Independent review of the corrected
commit still required before certification is claimed restored. No merge,
publication, or spending.

======================================================================
ROUND 22 — PARTIAL-SCAN + INTERNAL-CHECK-ERROR HARDENING (commit pending)
======================================================================
The 5th independent review of 1f746a8/5d54b73 returned PARTIAL PASS: R21-1
(real subprocess result/stderr) and R21-2 (zero-result all-N/A) ACCEPTED; two
new source-traced blockers:

R22-1  A PARTIALLY executed scan still certifies.
  valid_cli_report required only min_executed=1. A scan that ran ONE of 27
  checks (engine.run_all returning a single Result) yields a 27-entry report
  with 1 non-N/A + 26 N/A, a matching summary and a defined exit code — and was
  ACCEPTED. "27 listed" never proved "27 ran".

R22 (internal error)  A registered check that RAISES still certifies.
  engine.run_all converts a check exception into one UNKNOWN finding
  "This check could not run (internal error). Please report it." with
  hint=traceback.format_exc()[-400:]. Overall is non-clean (exit 2, allowed),
  the report still has 27 checks with execution evidence, and the gate's
  internal-error string was "Failsafe internal error" (the WHOLE-CLI wrapper
  message, cli.py), NOT this per-check message — so it was not rejected. The
  400-char tail also drops the "Traceback (most recent call last)" header on a
  long traceback, so a traceback-only detector could miss it too.

REPRODUCED ON REAL BLENDER 5.2.3 (installed extension), before coding:
  * run_all()[:1] -> report non-N/A ids [1]; CURRENT valid_cli_report(
    min_executed=1) ACCEPTS it (ok=True). 
  * one check raising -> report carries "This check could not run (internal
    error)" = True, "Traceback (most recent call last)" = False (header
    truncated), overall non-clean, exit 2; CURRENT gate ACCEPTS at exit 2.
  * Authoritative CLI-child scan of the saved cloth fixture executes check ids
    {1, 7, 8, 9, 17, 26} (rc=2, executed=6, findings=7) — matches R21.

CHECK NAMES (relevant): 1 Scale/rotation applied; 7 Cloth/soft body has a
collider; 8 No negative/inherited scale; 9 Object sizes realistic; 17
Simulation is baked; 26 Tracked settings vs baseline.

FIX
  tests/gate_check.py
    * New constant CHECK_INTERNAL_ERROR = "This check could not run (internal
      error)". valid_cli_report now REJECTS any report/stderr carrying it — a
      real per-check execution failure, distinct from a legitimate "Couldn't
      verify" UNKNOWN (which is preserved). Anchored on the stable MESSAGE, not
      the truncatable traceback, so a long traceback can't hide it.
    * valid_cli_report(..., required_ids=None): when given, EVERY one of those
      registered check ids must have EXECUTED (non-N/A). A count floor only
      proves SOME check ran; requiring the fixture's structural SET rejects a
      scan that ran fewer (the missing ids are still N/A).
  failsafe/engine.py
    * Promoted the per-check message to module constant CHECK_INTERNAL_ERROR_MSG
      so the gate marker stays a substring of it (an in-suite regression asserts
      the lockstep). Behaviour unchanged.
  certification/ci/win_acceptance.py
    * CLOTH_REQUIRED_IDS = {1, 7, 8, 26} — the structurally-forced subset of the
      cloth fixture's executed set (grounded in the real 5.2.3 child scan;
      #1/#8 run for every object, #7 because of the CLOTH modifier, #26 always).
    * The real-fixture clean scan now passes required_ids=CLOTH_REQUIRED_IDS.
    * Two new adversarial child regressions: a PARTIAL scan (run_all[:1]) is
      REJECTED (missing required ids); a scan where a check RAISES (internal
      error) is REJECTED (marker). EXPECTED_ACCEPT_CHECKS 28 -> 30.
  tests/run_tests.py
    * 7 new gate_selfcheck regressions (R22-1 required-set accept/reject, the
      1-of-27 partial reject, the min_executed-alone-accepts documentation case,
      the internal-error reject, the legitimate-UNKNOWN-preserved accept, and
      the engine/gate marker lockstep). gate_selfcheck 38 -> 45; grand total
      783 -> 790.

RESULT
  Plain-Python valid_cli_report cases: all pass. Mac matrix 4.2.9/4.5.9/5.0.1/
  5.2.3 each 790 passed / 0 failed, SUITE_DONE expected=790 ok=yes, GATE PASS
  version-enforced, equal totals, release gate PASS. win_acceptance on the real
  5.2.3 INSTALLED extension: 30/30, ACCEPT_DONE expected=30 ok=yes, gate PASS,
  0 raw crash signatures; the real-fixture scan ACCEPTED (executed=6, missing=[],
  rc=2) and all four adversarial children (no-report, crash-after-write,
  run_all->[], run_all[:1] partial) + the internal-error child REJECTED.
  Windows CI run 45412455563 (headSha f95be99 = c5144de + push-trigger toggle;
  branch tip 0312605 identical) genuinely PASS, verified in logs: 4x SUITE_DONE
  expected=790 ok=yes + GATE PASS version-enforced; ACCEPT_DONE 30/30 expected=30
  ok=yes + GATE PASS; the live fixture scan ACCEPTED (rc=2 executed=6 missing=[])
  and all five adversarial children (no-report, crash-after-write, run_all->[],
  run_all[:1] partial missing [7,8,26], internal-error marker=True) REJECTED;
  real-batch marker GATE PASS; 0 raw crash signatures (1 redacted token).
  Independent review of the corrected commit still required before certification
  is claimed restored. No merge, publication, or spending.

======================================================================
ROUND 23 — PROVE THE WHOLE CHECK REGISTRY WAS INVOKED (commit pending)
======================================================================
The 6th independent review of c5144de returned PARTIAL PASS: R22-1 (partial
scan) and R22 (internal-error) CLOSED, no regression. One remaining gap:

R23-1  The required_ids SET proves only that {1,7,8,26} returned non-N/A — NOT
  that all 27 registered check FUNCTIONS ran. A report's N/A is ambiguous: it
  means "the check ran and nothing was applicable" OR "the check never ran".
  So a scan returning results for only {1,7,8,26} and NONE for the other 23
  still satisfies required_ids + the summary integrity + the 27 listed entries.

REPRODUCED ON REAL BLENDER 5.2.3 (installed extension), before coding:
  * A report built from run_all() results filtered to {1,7,8,26} (23 results
    dropped -> they appear as N/A) is ACCEPTED by valid_cli_report(required_ids=
    {1,7,8,26}) (ok=True) — confirms the gap.
  * Independent instrumentation: wrap every registered check fn with a recorder,
    run a real scan -> invoked = all 27, unique 27, once each; 19-20 of those
    invoked checks returned N/A (no results) — PROVING a function that returns
    N/A still counts as invoked, so invocation distinguishes "ran and N/A" from
    "skipped".
  * A crippled run_all that iterates only CHECKS[:4] invokes [1,2,3,4] -> the
    invocation proof rejects it (missing 5..27).

FIX (close the CLASS, not another subset — the reviewer's recommendation)
  tests/gate_check.py
    * New valid_invocations(invoked_ids, expected_ids): requires EXACTLY the
      expected ids, once each — missing (skipped), duplicate, or unexpected ids
      are hard failures. Independent of the report; counts invocation not
      results, so N/A-returning checks count. Once every function is proven to
      have run, a report N/A is unambiguously "ran and nothing applicable".
  certification/ci/win_acceptance.py
    * Independent invocation proof: wrap every registered check function with a
      recorder, run a real in-process scan, require valid_invocations to confirm
      all 27 invoked once each AND that >0 of them returned N/A (so the proof
      demonstrably counts N/A-returning checks as invoked). Originals restored in
      a finally.
    * Omitted-invocation repro: temporarily shrink the registry so run_all
      iterates only the first 4 checks; assert valid_invocations REJECTS the
      result (the skipped functions never fired their recorder). Registry
      restored after. EXPECTED_ACCEPT_CHECKS 30 -> 32.
  tests/run_tests.py
    * 5 new gate_selfcheck regressions for valid_invocations (all-27 incl. N/A
      accepted; a skipped check rejected; the required subset {1,7,8,26} alone
      rejected; a duplicate call rejected; an unexpected id rejected).
      gate_selfcheck 45 -> 50; grand total 790 -> 795.
  (failsafe/engine.py unchanged this round.)

BOUNDARY (stated honestly): the invocation proof closes the missing-EXECUTION
class — a check that is skipped / never invoked. The reviewer's exact "wrap
run_all and drop 23 results" scenario genuinely CALLS the real run_all, so all
27 functions ARE invoked (the proof confirms 27) and that specific report is
still accepted — it is result-SUPPRESSION by an already-compromised run_all, a
different class that no report inspection can defeat (in production run_all is
not monkeypatched). The invocation proof catches the real risk: a run_all BUG
or reimplementation that skips checks.

RESULT
  Plain-Python valid_invocations cases: all pass. Mac matrix 4.2.9/4.5.9/5.0.1/
  5.2.3 each 795 passed / 0 failed, SUITE_DONE expected=795 ok=yes, GATE PASS
  version-enforced, equal totals, release gate PASS. win_acceptance on the real
  5.2.3 INSTALLED extension: 32/32, ACCEPT_DONE expected=32 ok=yes, gate PASS,
  0 raw crash signatures; the invocation proof logged invoked=27 unique=27
  na_but_invoked=20, and the skip repro was REJECTED (missing 5..27).
  Windows CI run 45420448793 (headSha 7ec0bc1 = aa224d3 + toggle; branch tip
  18cf03d identical) genuinely PASS, verified in logs: 4x SUITE_DONE expected=795
  ok=yes + GATE PASS version-enforced; ACCEPT_DONE 32/32 expected=32 ok=yes +
  GATE PASS; invocation proof invoked=27 unique=27 na_but_invoked=20 (PASS) and
  the skip repro REJECTED; real-batch marker GATE PASS; 0 raw crash signatures.
  Independent review of the corrected commit still required before certification
  is claimed restored. No merge, publication, or spending.

======================================================================
ROUND 24 — TIE THE INVOCATION PROOF TO THE CERTIFIED CHILD (commit pending)
======================================================================
The 7th independent review of aa224d3 returned PARTIAL PASS: R23's invocation
recorder works, but it ran in the PARENT acceptance process while the certified
JSON report comes from a separate CLI CHILD.

R24-1  The proof watched a different scan. win_acceptance certified the CLI
  child via valid_cli_report(required_ids=...) but separately ran eng.run_all()
  with all 27 wrapped INSIDE THE PARENT. Proving the parent ran all 27 does not
  prove the child did.

REPRODUCED ON REAL BLENDER 5.2.3 (the child self-records, before coding):
  * normal   child -> invoked=27, report findings match returns, ACCEPTED.
  * reduced  child (its run_all invokes only {1,7,8,26}) -> the child's OWN
    record shows invoked=4 -> REJECTED (R24-1). Its 27-entry report + required
    ids would otherwise look fine.
  * suppress child (invokes all 27 via the real run_all, then drops 23 results)
    -> invoked=27 but the per-check returned-findings cross-check flags ids
    [9,17,18] whose findings the report dropped -> REJECTED (also closes the
    result-SUPPRESSION boundary left open in R23).

FIX (instrument the ACTUAL child; validate its own evidence with its report)
  certification/ci/win_acceptance.py
    * instrumented_expr(attack=""): the CLI child, before running the scan, wraps
      every registered check function with a recorder that notes (a) the check
      was invoked and (b) how many findings it returned; after the scan it writes
      {invoked:[...], returns:{id:n}} to a <report>.inv sidecar. cli_json_child
      now clears+reads that sidecar and returns it (5-tuple).
    * The clean scan is certified by gate_check.valid_cli_scan on the SAME
      child's report + its .inv evidence (+ real exit, declared code, required
      ids). Two attack regressions: a child whose run_all invokes only {1,7,8,26}
      (REJECTED on invocation) and one that invokes all 27 then drops 23 results
      (REJECTED on the suppression cross-check). EXPECTED_ACCEPT_CHECKS 32 -> 34.
    * The R23 parent-process invocation proof + omitted-invocation repro are kept
      as additional in-process regressions, but they are no longer the
      certification evidence for the child.
  tests/gate_check.py
    * New valid_cli_scan(returncode, text, invoked_ids, returned_counts,
      expected_ids, ...): combines valid_cli_report (report validity/execution/
      exit) + valid_invocations (THAT child invoked every registered check once)
      + a result-faithfulness cross-check (report findings count per id == what
      the check returned inside the child). The invocation ids and returned
      counts MUST come from inside the same child that wrote the report.
  tests/run_tests.py
    * 4 new gate_selfcheck regressions for valid_cli_scan (full invocation +
      matching report accepted; invoked-only-subset rejected; a dropped result /
      suppression rejected; complete evidence but a bad exit rejected).
      gate_selfcheck 50 -> 54; grand total 795 -> 799.
  (failsafe/engine.py unchanged this round.)

RESULT
  Plain-Python valid_cli_scan cases: all pass. Mac matrix 4.2.9/4.5.9/5.0.1/
  5.2.3 each 799 passed / 0 failed, SUITE_DONE expected=799 ok=yes, GATE PASS
  version-enforced, equal totals, release gate PASS. win_acceptance on the real
  5.2.3 INSTALLED extension: 34/34, ACCEPT_DONE expected=34 ok=yes, gate PASS,
  0 raw crash signatures; the certified child logged invoked=27 executed=6
  findings=7 missing=[] suppressed=[], the reduced child REJECTED (invoked=4) and
  the suppress child REJECTED (suppressed=[9,17,18]).
  Windows CI run 45443330080 (headSha 07ea159 = 09212b8 + toggle; branch tip
  55aaf87 identical) genuinely PASS, verified in logs: 4x SUITE_DONE expected=799
  ok=yes + GATE PASS version-enforced; ACCEPT_DONE 34/34 expected=34 ok=yes +
  GATE PASS; certified child invoked=27 suppressed=[] (PASS), reduced child
  REJECTED (invoked=4), suppress child REJECTED (suppressed=[9,17,18]);
  real-batch marker GATE PASS; 0 raw crash signatures.
  Independent review of the corrected commit still required before certification
  is claimed restored. No merge, publication, or spending.

======================================================================
ROUND 25 — EXACT FINDING FAITHFULNESS, NOT JUST COUNTS (commit pending)
======================================================================
The 8th independent review of 09212b8 returned PARTIAL PASS: R24-1 CLOSED. One
remaining blocker:

R25-1  valid_cli_scan compared the NUMBER of findings per check, not their
  statuses/contents. Two holes: (A) it iterated the recorded counts, so a
  MISSING per-id entry was never required — incomplete evidence slipped by; and
  (B) a genuine UNKNOWN/FAIL finding could be swapped to PASS with the same count
  and the same check_id, and the count still matched.

REPRODUCED ON REAL BLENDER 5.2.3 (child records exact findings), before coding:
  * normal  -> per-id findings match the report exactly -> ACCEPT.
  * subst   -> run_all flips every WARNING result to PASS AFTER the function
    returned; the recorder captured the real WARNINGs so the report disagrees on
    ids [7,17] -> REJECT (B).
  * missing -> child drops its recorded evidence for 23 ids (still invoked all
    27) -> incomplete per-id evidence [2,3,..] -> REJECT (A).

FIX (prove the report tells the truth about findings, not just how many)
  certification/ci/win_acceptance.py
    * instrumented_expr now records, per check, the EXACT findings it returned
      ([status, object, message, hint] rows), not a count, into the <report>.inv
      sidecar ({invoked, findings:{id: rows}}). Added a ``post`` hook so a
      regression can tamper with the recorded evidence after the scan.
    * Replaced the count-based suppress regression with two exact-findings ones:
      a child that SWAPS a WARNING finding to PASS (same count) is REJECTED on the
      content mismatch; a child that records findings for only {1,7,8,26} is
      REJECTED for incomplete per-id evidence. EXPECTED_ACCEPT_CHECKS 34 -> 35.
  tests/gate_check.py
    * valid_cli_scan now takes ``returned_findings`` {id: [[status,object,message,
      hint],...]} and (a) requires a recorded entry for EVERY expected id (missing
      evidence is a hard failure, not silently skipped) and (b) compares the
      report's per-id findings to the recorded rows EXACTLY, order-independent
      (_norm_findings). A dropped or status-swapped finding is caught even when the
      count is unchanged. Legitimate N/A (empty rows) and UNKNOWN are preserved.
  tests/run_tests.py
    * Reworked the gate_selfcheck valid_cli_scan regressions to exact rows and
      added R25 cases (incomplete evidence rejected; swapped finding rejected;
      same-count different-status rejected). gate_selfcheck 54 -> 56; grand total
      799 -> 801.
  (failsafe/engine.py unchanged this round.)

RESULT
  Plain-Python valid_cli_scan cases: all pass. Mac matrix 4.2.9/4.5.9/5.0.1/
  5.2.3 each 801 passed / 0 failed, SUITE_DONE expected=801 ok=yes, GATE PASS
  version-enforced, equal totals, release gate PASS. win_acceptance on the real
  5.2.3 INSTALLED extension: 35/35, ACCEPT_DONE expected=35 ok=yes, gate PASS,
  0 raw crash signatures; certified child invoked=27 missing_ev=[] mismatch=[],
  the reduced child REJECTED (invoked=4), the status-swap child REJECTED
  (mismatch=[7,17]), the incomplete-evidence child REJECTED (missing 23 ids).
  Windows CI run 45473530097 (headSha c6b1a61 = d90bc0e + toggle; branch tip
  51b2c60 identical) genuinely PASS, verified in logs: 4x SUITE_DONE expected=801
  ok=yes + GATE PASS version-enforced; ACCEPT_DONE 35/35 expected=35 ok=yes +
  GATE PASS; certified child invoked=27 missing_ev=[] mismatch=[] (PASS), reduced
  REJECTED (invoked=4), swap REJECTED (mismatch=[7,17]), incomplete-evidence
  REJECTED (missing 23); real-batch marker GATE PASS; 0 raw crash signatures.
  Independent review of the corrected commit still required before certification
  is claimed restored. No merge, publication, or spending.

======================================================================
ROUND 26 — THE REPORT'S OWN VERDICTS MUST AGREE WITH ITS FINDINGS (commit pending)
======================================================================
The 9th independent review of d90bc0e returned PARTIAL PASS: R25-1 CLOSED. One
remaining blocker:

R26-1  valid_cli_scan compared the findings exactly, but never checked that the
  report's TOP-LEVEL verdicts agreed with them: a check's per-check `status`, the
  `summary` distribution, and `overall` could all lie while the findings stayed
  intact, so the R25 comparison still passed. (valid_cli_report only checked the
  TOTAL non-N/A count, not the per-status distribution.)

REPRODUCED ON REAL BLENDER 5.2.3 (findings + evidence intact, verdicts tampered),
before coding — the committed valid_cli_scan ACCEPTED all three:
  * overall_lie: report `overall` rewritten WARNING -> PASS -> accepted.
  * status_lie: every WARNING check `status` flipped to PASS (findings intact) ->
    accepted.
  * summary_lie: summary WARNING count moved into PASS (total non-N/A unchanged,
    so it even slipped past valid_cli_report's non-N/A-total integrity: 6==6) ->
    accepted.

FIX (derive the verdicts from the findings and require the report to match)
  tests/gate_check.py
    * _FINDING_SEVERITY (mirrors engine.SEVERITY) + _derived_status(rows) (worst
      finding by severity, NOT APPLICABLE when none — mirrors engine.check_status)
      + _derived_overall(statuses) (worst that occurred; NA/PASS -> PASS — mirrors
      build_json_report).
    * valid_cli_scan now, with complete evidence, DERIVES from the child's recorded
      findings: each check's expected status, the exact summary distribution, and
      overall; it requires the report's per-check `status`, `summary` buckets and
      `overall` to match. A report that keeps real WARNING/UNKNOWN/FAIL findings
      but declares a rosier status/summary/overall is rejected. Legitimate N/A and
      UNKNOWN are preserved (they must match on both sides).
  certification/ci/win_acceptance.py
    * Three new verdict-lie regressions via the child `post` hook (rewrite only the
      report's overall / a check's status / the summary distribution, findings +
      evidence intact): each REJECTED. EXPECTED_ACCEPT_CHECKS 35 -> 38.
  tests/run_tests.py
    * 4 new gate_selfcheck regressions (a verdict-consistent report accepted; a
      false overall, a per-check status lie, and a faked summary distribution each
      rejected). gate_selfcheck 56 -> 60; grand total 801 -> 805.
  (failsafe/engine.py unchanged this round.)

RESULT
  Plain-Python valid_cli_scan cases: all pass. Mac matrix 4.2.9/4.5.9/5.0.1/
  5.2.3 each 805 passed / 0 failed, SUITE_DONE expected=805 ok=yes, GATE PASS
  version-enforced, equal totals, release gate PASS. win_acceptance on the real
  5.2.3 INSTALLED extension: 38/38, ACCEPT_DONE expected=38 ok=yes, gate PASS,
  0 raw crash signatures; certified child invoked=27 missing_ev=[] mismatch=[],
  and the overall / per-check-status / summary verdict lies each REJECTED.
  Windows CI run 45476157670 (headSha 1ddb1cf = 5a4165c + toggle; branch tip
  8a6ece0 identical) genuinely PASS, verified in logs: 4x SUITE_DONE expected=805
  ok=yes + GATE PASS version-enforced; ACCEPT_DONE 38/38 expected=38 ok=yes +
  GATE PASS; certified child invoked=27 missing_ev=[] mismatch=[] (PASS), the
  overall / per-check-status / summary verdict lies each REJECTED; real-batch
  marker GATE PASS; 0 raw crash signatures.
  Independent review of the corrected commit still required before certification
  is claimed restored. No merge, publication, or spending.

======================================================================
ROUND 27 — THE CUSTOMER-FACING DISPLAY MUST MATCH THE REGISTRY (commit pending)
======================================================================
The 10th independent review of 5a4165c returned PARTIAL PASS: R26-1 CLOSED. One
remaining blocker:

R27-1  valid_cli_scan verified the machine status/summary/overall but never the
  customer-facing `display` field. A check with a genuine UNKNOWN/WARNING/FAIL
  result could show "Everything verified -- ready to render." while findings,
  status, summary and overall stayed consistent, so the gate accepted it.

REPRODUCED ON REAL BLENDER 5.2.3 (findings/status/summary/overall + evidence
intact; only `display` rewritten), before coding: check #26 (UNKNOWN) display
rewritten to "Everything verified -- ready to render." vs the registry canonical
display_name(meta, UNKNOWN) = "Couldn't compare against a settings baseline";
the committed valid_cli_scan ACCEPTED it.

FIX (tie the display + metadata to the registry's canonical wording)
  certification/ci/win_acceptance.py
    * The instrumented child now also records, per check, the registry's CANONICAL
      metadata: display_name(meta, derived_status) plus the check's name and
      group, straight from the engine, into the .inv sidecar ({..., meta:{id:
      {display,name,group}}, schema:1}). _evidence returns it; every valid_cli_scan
      call passes report_meta.
    * New display-lie regression (rewrite a non-PASS check's `display` to a
      reassuring message, findings/verdicts intact) -> REJECTED.
      EXPECTED_ACCEPT_CHECKS 38 -> 39.
  tests/gate_check.py
    * valid_cli_scan gains report_meta: when given, each check's report `display`
      must equal the registry's display_name(meta, status) and its name/group must
      match; also check ids must be unique and exactly the registry set, `schema`
      must be the known value (1), and `summary` must carry no unexpected buckets.
      A relabelled check, a reassuring display on a non-PASS check, a duplicate id,
      a wrong schema or a stray summary key is rejected.
  tests/run_tests.py
    * 6 new gate_selfcheck regressions (registry-matching report accepted; a
      reassuring display, a relabelled name, a duplicate id, a wrong schema, and a
      stray summary bucket each rejected). gate_selfcheck 60 -> 66; grand total
      805 -> 811.
  (failsafe/engine.py and report.py unchanged this round.)

RESULT
  Plain-Python valid_cli_scan cases: all pass. Mac matrix 4.2.9/4.5.9/5.0.1/
  5.2.3 each 811 passed / 0 failed, SUITE_DONE expected=811 ok=yes, GATE PASS
  version-enforced, equal totals, release gate PASS. win_acceptance on the real
  5.2.3 INSTALLED extension: 39/39, ACCEPT_DONE expected=39 ok=yes, gate PASS,
  0 raw crash signatures; certified child invoked=27 missing_ev=[] mismatch=[],
  and the display-lie child REJECTED (meta_mismatch=[(7,'display')]).
  Windows CI run 45485042370 (headSha 5610c82 = 2383e79 + toggle; branch tip
  08047e1 identical) genuinely PASS, verified in logs: 4x SUITE_DONE expected=811
  ok=yes + GATE PASS version-enforced; ACCEPT_DONE 39/39 expected=39 ok=yes +
  GATE PASS; certified child invoked=27 missing_ev=[] mismatch=[] (PASS), the
  display-lie child REJECTED (meta_mismatch=[(7,'display')]); real-batch marker
  GATE PASS; 0 raw crash signatures.
  Independent review of the corrected commit still required before certification
  is claimed restored. No merge, publication, or spending.

======================================================================
ROUND 28 — METADATA FAIL-CLOSED + REPORT PROVENANCE (commit pending)
======================================================================
The 11th independent review of 2383e79 returned PARTIAL PASS: R27-1 CLOSED. Two
remaining blockers:

R28-1  The metadata check FAILED OPEN: valid_cli_scan used `if report_meta:`, so
  an absent/empty metadata dict skipped the display/name/group check entirely;
  it also tolerated missing name/group fields.
R28-2  Report PROVENANCE was never verified: the report's `blender` and `file`
  fields were not checked against the child, so a report could claim it scanned a
  different Blender version or .blend file.

REPRODUCED ON REAL BLENDER 5.2.3 (against the committed R27 validator), before
coding: with report_meta={} a display lie was ACCEPTED (fail-open); a report with
blender='9.9.9' was ACCEPTED; a report with file='/evil/other.blend' was ACCEPTED.

FIX
  certification/ci/win_acceptance.py
    * The instrumented child now also records its ACTUAL provenance
      (bpy.app.version_string + bpy.data.filepath) in the .inv sidecar. A
      _certify() helper runs every CLI-child check in FULL certification mode:
      require_meta=True, provenance=<child's>, expected_blender=bpy.app.version_
      string, expected_file=<the fixture>. New repros: dropped canonical metadata
      (REJECTED, not skipped), a report omitting a per-check field (REJECTED), a
      blender-version lie (REJECTED), a .blend-file lie (REJECTED).
      EXPECTED_ACCEPT_CHECKS 39 -> 43.
  tests/gate_check.py
    * valid_cli_scan gains require_meta, provenance, expected_blender,
      expected_file. With require_meta the canonical metadata must be COMPLETE for
      all 27 ids and present on every report check (fail-closed). Provenance:
      report blender/file must equal the child's actual values, the version must
      equal expected, and the fixture basename must match. cache_disk_usage totals
      must add up.
  tests/run_tests.py
    * 6 new gate_selfcheck regressions (honest cert report accepted; empty
      metadata, omitted field, version lie, file lie, cache mismatch each
      rejected). gate_selfcheck 66 -> 72; grand total 811 -> 817.
  (failsafe/engine.py and report.py unchanged this round.)

RESULT
  Plain-Python valid_cli_scan cases: all pass. Blender 5.2.3 local suite: 817
  passed / 0 failed, SUITE_DONE expected=817 ok=yes, GATE PASS. win_acceptance on
  the real 5.2.3 INSTALLED extension: 43/43, ACCEPT_DONE expected=43 ok=yes, gate
  PASS, 0 raw crash signatures; certified child invoked=27 missing_ev=[]
  mismatch=[], and the dropped-metadata / omitted-field / blender-lie / file-lie
  children each REJECTED.
  NOTE: the local four-version Mac matrix could NOT run this round — the
  4.2.9 / 4.5.9 / 5.0.1 builds under ~/Downloads/blender_runtime_certification/
  are no longer on the machine (the whole folder is gone); only the system 5.2.3
  remains. Four-version coverage is provided by Windows CI below, which downloads
  all four official Blender builds. (If the local builds return, re-run
  tests/run_all_versions.sh to confirm the Mac matrix.)
  Windows CI run 45842589093 (headSha 26ef202 = e9acd2a + toggle; branch tip
  157648f identical) genuinely PASS, verified in logs — the SOLE four-version
  signal this round: 4x SUITE_DONE expected=817 ok=yes + GATE PASS version-
  enforced (4.2.9/4.5.9/5.0.1/5.2.3); ACCEPT_DONE 43/43 expected=43 ok=yes +
  GATE PASS; certified child invoked=27 missing_ev=[] mismatch=[], the meta-drop
  ("no canonical meta"), omitted-field ("name"), blender-lie (vs child's
  '5.2.3 LTS') and file-lie (vs the child's real Windows path) children each
  REJECTED; real-batch marker GATE PASS; 0 raw crash signatures.
  Independent review of the corrected commit still required before certification
  is claimed restored. No merge, publication, or spending.

================================================================================
ROUND 29 — provenance bypass (same-basename / absent provenance) + false-zero cache
================================================================================
REVIEW (independent, on e9acd2a): PARTIAL PASS. R28-1 CLOSED (metadata fail-
closed). R28-2 PARTIAL. Two blockers:
  R29-1 PROVENANCE BYPASS. valid_cli_scan skipped the child's actual-file check
    when provenance=None, and expected_file compared only os.path.basename() —
    so the R28 self-test accepted actual /tmp/fix.blend against expected
    /x/fix.blend. A child opening a DIFFERENT file with the SAME basename passes.
  R29-2 CACHE FALSE ZERO. report._enumerate_caches_safe() caught every
    enumeration error and returned [] — a failed enumeration looked identical to
    a genuine zero ({total_bytes:0, items:[]}), and the gate tolerated a missing
    cache block. A could-not-enumerate certified as a verified zero.

REPRODUCED FIRST on real Blender 5.2.3 (before any fix), with a genuine 27-check
report from an installed scan:
  * expected_file = a different dir, same basename "win fixture.blend" -> ok=True
    (ACCEPTED, bug). provenance=None + wrong expected -> ok=True (ACCEPTED, bug).
  * monkeypatched cache_inspect.enumerate_caches to raise -> build_json_report
    emitted cache_disk_usage {total_bytes:0, items:[]}, byte-identical to an
    empty scene (confirmed Indistinguishable == True).

FIX
  tests/gate_check.py
    * new _same_file(a, b): file identity by inode (os.path.samefile, robust to
      Windows 8.3 short names / symlinks / separators) with a canonical-realpath
      fallback — never basename alone (R29-1).
    * valid_cli_scan gains require_provenance and require_cache_verified.
      - require_provenance: provenance must be PRESENT and COMPLETE (blender+file),
        and expected_blender+expected_file must be supplied; absent/incomplete
        provenance is a hard failure, not a skipped check.
      - the scanned file is matched to the intended fixture by _same_file identity,
        not basename, so /evil/win fixture.blend != /good/win fixture.blend.
      - require_cache_verified: cache_disk_usage must be present and
        enumerated==True; enumerated:false (or the legacy no-'enumerated' zero)
        can never certify as a verified zero (R29-2).
  failsafe/report.py
    * _enumerate_caches() returns (entries, ok); ok=False only when enumeration
      RAISED. _cache_usage_block() emits {"enumerated":true,...} for a real
      measurement and {"enumerated":false,"total_bytes":null,...} for a failure —
      never a fabricated 0. build_json_report gains cache_ok.
  failsafe/cli.py, failsafe/batch.py
    * both scan paths that already caught enumeration errors now thread cache_ok
      (True on success, False on failure) into build_json_report, so a failure is
      reported honestly rather than as entries=[] -> false zero.
  certification/ci/win_acceptance.py
    * _certify() now passes require_provenance=True, require_cache_verified=True.
    * 4 new regressions: (R29-1) a child that really opens a decoy file sharing
      the fixture's basename -> REJECTED by identity; a child that drops its
      provenance -> REJECTED (fail-closed). (R29-2) a real cache-enumeration
      failure -> report marks enumerated:false/null (honesty assertion); a report
      presenting the legacy unverified-zero shape -> REJECTED. ACCEPT 43 -> 47.
  tests/run_tests.py
    * provenance self-tests rewritten to use REAL temp files (good/ and evil/ each
      holding "fix.blend") so identity is genuinely exercised — the old
      /tmp/fix.blend vs /x/fix.blend basename acceptance is gone. +6 gate_selfcheck
      regressions (same-basename reject, absent/incomplete provenance reject,
      verified-cache accept, enumerated:false reject, legacy-zero reject).
      gate_selfcheck 72 -> 78; grand total 817 -> 823.
  (failsafe/engine.py unchanged this round.)

RESULT
  Both blockers reproduced on real 5.2.3 before coding (above). After the fix:
  _same_file correct (same=True, different=False, different-spelling-same=True).
  Blender 5.2.3 local suite: 823 passed / 0 failed, SUITE_DONE expected=823
  ok=yes, GATE PASS version-enforced. win_acceptance on the real 5.2.3 INSTALLED
  extension (rebuilt failsafe-1.0.0.zip, reinstalled): 47/47, ACCEPT_DONE
  expected=47 ok=yes, GATE PASS; certified child invoked=27 missing_ev=[]
  mismatch=[]; the same-basename-different-file child REJECTED by identity, the
  provenance-dropped child REJECTED, the failed-enumeration report marked
  enumerated:false/null, the unverified-zero cache REJECTED. 0 real crash
  signatures (the one "Traceback<redacted>" line is the R21-1 regression's own
  redacted description, and the ACCEPT gate passed).
  NOTE: the local four-version Mac matrix again could NOT run — the
  4.2.9/4.5.9/5.0.1 builds under ~/Downloads/blender_runtime_certification/ are
  still absent (folder gone); only system 5.2.3 remains. Four-version coverage
  this round comes from Windows CI (downloads all four official builds).
  Windows CI run 46015004987 (headSha 73bb2e2 = 7207a05 + toggle; branch tip
  d5e499b identical) genuinely PASS, verified in logs — the SOLE four-version
  signal this round: 4x SUITE_DONE expected=823 ok=yes + GATE PASS version-
  enforced (4.2.9/4.5.9/5.0.1/5.2.3), with the 6 new R29 gate_selfcheck
  regressions PASS on all four; ACCEPT_DONE 47/47 expected=47 ok=yes + GATE PASS;
  certified child invoked=27 missing_ev=[] mismatch=[]; the same-basename decoy
  child REJECTED by identity (the log shows the real Windows decoy path
  C:\Users\RUNNER~1\AppData\Local\Temp\failsafe_decoy_...\win fixture.blend, so
  the identity check ran against a genuinely different Windows file); the
  provenance-dropped child REJECTED; the failed-enumeration report marked
  enumerated:false/null; the unverified-zero cache REJECTED; real-batch marker
  GATE PASS; 0 genuine crash signatures.
  Independent review of the corrected commit still required before certification
  is claimed restored. No merge, publication, or spending.


================================================================================
ROUND 30 — cache SIZE-measurement false zero + _same_file missing-path identity
================================================================================
Independent review of 7207a05: PARTIAL PASS. R29-1 and R29-2 (enumeration
exceptions) CLOSED. Two further gaps:

R30-1  SIZE FAILURE CAN STILL LOOK LIKE VERIFIED ZERO
  cache_inspect._dir_size() / _point_cache_bytes() return None when a per-cache
  SIZE measurement fails, while enumerate_caches() still finishes successfully.
  report._cache_usage_block() EXCLUDED entries whose disk_bytes is None, set
  enumerated=True and summed only the survivors — so an unmeasured cache silently
  disappeared and a populated scene could report total_bytes:0 as a VERIFIED zero
  (or a silent undercount). valid_cli_scan accepted it (enumerated:true, 0==sum).
  REPRODUCED on real 5.2.3 (repro via real CacheEntry through the real
  build_json_report): one measured (4096) + one unmeasured -> the unmeasured cache
  DROPPED, total understated; unmeasured-only -> enumerated:true, total_bytes:0,
  items:[] (false verified zero); the current gate did NOT reject it.

R30-2  _same_file realpath fallback matched two identical NONEXISTENT paths
  _same_file() fell back to os.path.realpath equality when os.path.samefile
  raised; two identical MISSING paths resolve to the same string -> returned True,
  so a deleted/missing fixture could "match". REPRODUCED on real 5.2.3:
  _same_file(missing, missing) == True while the path does not exist; a DIFFERENT
  missing path -> False (R29-1 preserved).

FIX
  failsafe/report.py
    * _cache_usage_block now reports TWO independent facts: `enumerated` (did the
      inventory enumeration succeed, R29-2) and `measured` (was EVERY enumerated
      cache's on-disk size measured). total_bytes is a verified COMPLETE figure
      ONLY when measured; the moment any cache goes unmeasured it is null (unknown),
      never a fabricated 0/undercount. The measured caches' sum is reported,
      labelled, as `known_subtotal_bytes`; every enumerated cache appears in
      `items` (an unmeasured one with bytes:null) so an unknown size is preserved,
      not dropped. Text/HTML reports label a "Subtotal (measured)" and name the
      "N cache(s) of unknown size" when any size is unmeasured.
  tests/gate_check.py
    * _same_file fallback now requires the resolved real-path to EXIST — identity
      of a missing/deleted file can't be established, so identical missing paths
      return False (R30-2); real-file identity and the R29-1 basename rejection are
      unchanged.
    * cache honesty: a NON-NULL total_bytes claims a verified complete figure, so
      it must equal the sum of item bytes, carry measured:true, and have no
      unmeasured caches behind it — a false zero (total:0 over an unmeasured cache)
      is REJECTED (R30-1). A NULL total paired with measured:false is an HONEST
      "size unknown" and is ACCEPTED (the correctness scan doesn't hinge on a
      knowable informational size); a null total dishonestly claiming measured:true
      is REJECTED.
  certification/ci/win_acceptance.py
    * +5 regressions: false-zero (total:0 over unmeasured) REJECTED; verified total
      over unmeasured REJECTED; honest-unknown (null total) ACCEPTED; real report
      carries the honest two-axis schema and never a non-null total it didn't
      measure; _same_file identical-missing rejected / real confirmed / decoy
      rejected. ACCEPT 47 -> 52.
  tests/run_tests.py
    * +9 gate_selfcheck regressions (false-zero reject, honest-unknown accept,
      null-claiming-measured reject, verified-total-over-unmeasured reject, honest
      fully-measured accept, inconsistent known_subtotal reject; _same_file
      identical-missing reject, real-identity confirm, cert-naming-missing-fixture
      reject). _CACHE_OK updated to the measured:true shape. gate_selfcheck
      78 -> 87; grand total 823 -> 832.
  (failsafe/cli.py, batch.py unchanged — they already thread cache_ok; the new
   measured/known_subtotal/unmeasured fields are computed inside _cache_usage_block.)

RESULT
  Both blockers reproduced on real 5.2.3 BEFORE coding (above). After the fix, on
  real 5.2.3: mixed measured+unmeasured -> unmeasured preserved (bytes:null),
  measured:false, total_bytes:null, known_subtotal_bytes labelled; unmeasured-only
  -> NOT a verified zero; fully-measured -> total verified; a genuinely cache-free
  scene -> measured:true, total_bytes:0 (a legitimate verified zero still works);
  _same_file identical-missing=False, real-identity=True, diff-missing=False.
  Local 5.2.3 suite: 832 passed / 0 failed, SUITE_DONE expected=832 ok=yes, GATE
  PASS version-enforced (gate_selfcheck n=87). win_acceptance on the real 5.2.3
  INSTALLED extension (rebuilt failsafe-1.0.0.zip, reinstalled): 52/52, ACCEPT_DONE
  expected=52 ok=yes, GATE PASS; the honest certify path passes (the real fixture's
  own unmeasured cache -> null total -> accepted), the false-zero REJECTED, the
  honest-unknown ACCEPTED, _same_file traps behave. 0 real crash signatures.
  NOTE: the local four-version Mac matrix again could NOT run — the
  4.2.9/4.5.9/5.0.1 builds under ~/Downloads/blender_runtime_certification/ are
  still absent; only system 5.2.3 remains. Four-version coverage this round comes
  from Windows CI (downloads all four official builds).
  Windows CI run 46026889573 (headSha 3dab770 = R30 commit 4003ea5 + push toggle;
  branch tip 1aabfef is the clean revert, functionally identical) genuinely PASS,
  verified in the downloaded log artifacts — the SOLE four-version signal this
  round: 4x SUITE_DONE expected=832 ok=yes with gate_selfcheck n=87 on all four
  (4.2.9/4.5.9/5.0.1/5.2.3); ACCEPT_DONE 52/52 expected=52 ok=yes; honest certify
  PASS (invoked=27 missing_ev=[] mismatch=[]); every R30 trap behaved — false-zero
  (total:0 over unmeasured) REJECTED, verified-total-over-unmeasured REJECTED,
  honest-unknown (null total) ACCEPTED, the real report carries the two-axis
  schema, _same_file identical-missing=False/real=True/decoy=False; real-batch
  "ALL CHECKS PASSED"; 0 genuine crash signatures; all four jobs succeeded (so
  every gate step exited 0 = GATE PASS version-enforced).
  Independent review of the corrected commit (4003ea5) still required before
  certification is claimed restored. No merge, publication, or spending.


================================================================================
ROUND 31 — cache partial-measurement false number (per-file stat failure)
================================================================================
Independent review of 4003ea5: PARTIAL PASS. R30-2 CLOSED (_same_file rejects
missing files). R30-1 PARTIAL: unknown sizes are now represented honestly at the
report/gate layer, but the SOURCE size helpers could still produce a false
numeric measurement when an INDIVIDUAL file's stat failed.

R31-1  SIZE FAILURE CAN STILL PRODUCE A FALSE NUMBER
  cache_inspect._point_cache_bytes() did `except OSError: continue` per frame, and
  _dir_size() did the same per DirEntry.stat(). A single per-file failure dropped
  that file and returned a NUMERIC partial subtotal; report.py sees a numeric
  disk_bytes and treats the cache as fully measured (measured:true). So a true
  300 B stage with one unreadable file reported 200 B, and a wholly unreadable
  stage reported a false VERIFIED 0 B — the R30-1 vector, moved one level down
  from "whole measurement failed" to "one file's measurement failed".
  REPRODUCED on real Blender 5.2.3 (forced per-file stat/getsize failure over real
  files, exercising the REAL helpers): _dir_size 300 -> 200 (one fail) / 0 (all
  fail); _point_cache_bytes 300 -> 200 (one fail); genuine 0-byte file -> 0
  (correctly a measured zero, must be preserved).

FIX
  failsafe/cache_inspect.py
    * _dir_size(): a per-file stat/is_file OSError now RETURNS None (whole-dir
      total unknown) instead of `continue`. A genuine 0-byte file (st_size 0, no
      error) is a MEASURED zero and is summed normally — only a real measurement
      failure forces None.
    * _point_cache_bytes(): a per-frame getsize OSError now RETURNS None instead
      of `continue`. Same 0-byte-is-measured rule.
    * fluid aggregation (inspect_fluid_domain): a sub-cache directory that EXISTS
      but can't be fully measured now voids the whole fluid total (None), distinct
      from a stage that is legitimately ABSENT (feature off — skipped). The total
      is a verified figure only when >=1 stage measured AND no present stage went
      unmeasured. Covers the fluid-subdirectory partial-measurement case.
  tests/gate_check.py (R31-2 — companion at the gate)
    * valid_cli_scan now cross-checks the measured/unmeasured SUMMARY fields
      against the ACTUAL items: measured=True with any null-byte item, or an
      `unmeasured` count that disagrees with the number of null-byte items (either
      direction), or measured=False while every item is measured, is a
      contradictory report and is REJECTED. So even if a partial number ever
      surfaced as an item, a measured:true over it is caught at the gate too.

REGRESSIONS
  tests/run_tests.py gate_selfcheck_tests 87 -> 97 (grand total 832 -> 842):
    +4 R31-2 field-consistency (measured:true over null REJECTED; unmeasured-count
    mismatch REJECTED; measured:false over all-measured REJECTED; honest
    partial-unknown ACCEPTED) and +6 R31-1 size-helper (dir 300 B; dir one-fail
    None; dir all-fail None; pc 300 B; pc one-fail None; 0-byte measured zero).
  certification/ci/win_acceptance.py EXPECTED_ACCEPT_CHECKS 52 -> 56:
    +2 R31-2 contradiction rejections, +1 honest partial-unknown acceptance, +1
    direct repro on the REAL INSTALLED build's cache_inspect (full=200, one-fail
    None, all-fail None, 0-byte 0).
  R17-R30 protections preserved.

LOCAL (real Blender 5.2.3 only; the 4.2.9/4.5.9/5.0.1 runtime builds are absent
from the dev machine this round, so the four-version Mac matrix could NOT run):
  suite 842/0, SUITE_DONE expected=842 ok=yes, GATE PASS, gate_selfcheck n=97;
  acceptance 56/56, ACCEPT_DONE expected=56 ok=yes, GATE PASS; honest certify path
  intact (invoked=27 missing_ev=[] mismatch=[]); installed cache_inspect repro
  full=200 one_fail=None all_fail=None zero=0.
  Committed as 1258ffa.

RESULT — Windows CI run 46052074360 (headSha 53fa33b = 1258ffa + push-trigger
toggle; branch tip is the clean revert 4bcdafb + these notes, functionally
identical). GENUINELY PASS, verified in the downloaded log artifacts:
  * 4× SUITE_DONE version=<4.2.9|4.5.9|5.0.1|5.2.3> passed=842 failed=0 total=842
    expected=842 consistent=yes ok=yes, each with GROUP_COUNT
    gate_selfcheck_tests n=97 (all 10 R31 regressions present and passing on every
    version);
  * ACCEPT_DONE version=5.2.3 passed=56 failed=0 total=56 expected=56 ok=yes;
  * honest certify PASS (invoked=27 missing_ev=[] mismatch=[]);
  * R31-2 traps: measured:true-over-null-item REJECTED, unmeasured-count-lie
    REJECTED, honest partial-unknown ACCEPTED; R31-1 installed cache_inspect repro
    full=200 one_fail=None all_fail=None zero=0;
  * real-batch "REAL BATCH PROOF: ALL CHECKS PASSED"; 0 genuine crash signatures;
    acceptance/install/real-batch ran only on 5.2.3 (matrix guard), all four jobs
    succeeded (every gate step exited 0 = GATE PASS version-enforced).
Independent review of the corrected commit (1258ffa) still required before
certification is claimed restored. No merge, publication, or spending.
