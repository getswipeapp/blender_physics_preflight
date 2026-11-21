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
