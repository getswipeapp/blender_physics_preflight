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
