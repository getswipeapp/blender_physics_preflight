# Failsafe — Verified Build Roadmap (to "#1 hands down")

> Written 2026-11-15 after a source-grounded inventory of the current `dfda2f7`-line
> code (branch `failsafe-expanded-hardening`). Supersedes the memory-based gap guesses
> in COMPETITOR_LEDGER.md where they conflict. Decisions locked: full breadth, hybrid
> repairs (read-only default + opt-in authorized fixes), best product over fast launch.

## VERIFIED current state — we are far ahead of where the first comparison implied

Already built and confirmed in source (these were WRONGLY listed as gaps from memory):

| Capability | Status | Beats whom |
|---|---|---|
| **Exhaustive every-required-frame disk check** (no sampling) | ✅ DONE | Beats Cache Guardian ($14), which samples |
| Cache path portability check (#22) | ✅ DONE | Matches Cache Guardian |
| Cloud-synced cache detection (#24) — Dropbox/OneDrive/Drive/iCloud/pCloud/Nextcloud/ownCloud/Sync/MEGA/Box | ✅ DONE, **broader than anyone** | Beats Cache Guardian (4 services) |
| Shared cache directory warning (#21) | ✅ DONE | Matches Cache Guardian |
| Bake-covers-render-range check (#19) | ✅ DONE | Matches Cache Guardian |
| Orphaned cache file detection (#25) | ✅ DONE (computes, won't delete) | Matches Cache Commander detection |
| Headless CLI, honest exit codes 0/1/2/3 (UNKNOWN≠pass; empty folder≠clean) | ✅ DONE | Matches Cache Commander |
| Batch multi-file folder scan, subprocess-isolated + timeouts | ✅ DONE | Matches Cache Commander |
| JSON report (stable schema) + text report | ✅ DONE | Matches SceneCheck/RabbidRender JSON |
| Staleness/settings drift (#26) + FPS timing baseline (#23) | ✅ DONE | Beats cache rivals on FPS |
| Severity model + filter + per-row collapse | ✅ DONE | Matches Triage severity |
| Physics-SETUP checks (16, pre-bake: colliders, scale, mass…) | ✅ DONE | Beats all cache tools (they're cache-only) |
| Read-only guarantee (only write = external baseline sidecar) | ✅ DONE | Our trust identity |

**Bottom line: on the simulation/physics-cache lane we already MATCH or BEAT Cache Guardian and Cache Commander, with a real exhaustive-frame moat none of them have.** The expansion is now about (a) finishing a few real gaps in our own lane, (b) widening into the general-preflight lane to beat the generalists too, and (c) adding things nobody has.

## Verified REAL gaps (confirmed absent in source)
1. ~~Hair-particle caches and Dynamic Paint canvas caches — not enumerated.~~ ✅ DONE (2026-11-16): hair dynamics (`use_hair_dynamics`) and Dynamic Paint VERTEX surfaces now enumerated through a shared `_iter_object_point_caches` helper that also feeds the orphan check (fixed a latent false-orphan bug for DP caches). Filename scheme empirically verified on 5.2.3 (standard `.bphys`). Dynamic Paint IMAGE-format surfaces (image sequence to `image_output_path`) are now surfaced as an explicit **"Couldn't verify"** (#17 UNKNOWN) rather than silently skipped — and their output path still gets the real portability (#22) and cloud-sync (#24) checks. Reading the image-sequence *contents* remains a later item.
2. Cache **structure** validation — ✅ SHIPPED (2026-11-16): basic `.bphys` structural verification (magic + full 20-byte header + non-zero `totpoint`/`data_types` + payload present + sim-type matches the owning sim), catching present-but-malformed frames beyond the 0-byte check, certified 4 versions. This is **basic structural** verification, NOT payload content integrity — a corrupted/truncated body with a valid header is not detected (Blender itself can't load it but gives no error signal; see [CACHE_FORMAT_NOTES.md](CACHE_FORMAT_NOTES.md), reviews B1/M1).
2b. **Baselined per-frame SHA-256 cache hashes** — ✅ SHIPPED (2026-11-16, review M2; hardened 2026-11-17, review M3): check **#27** detects when a baked **body** changed since a saved baseline, even with a valid header — the gap #2 can't close. On-demand streaming hash (Verify Cache Hashes button / CLI `--verify-hashes`), kept off the quick scan so gigabytes never freeze the UI; honest wording throughout (a match = "bytes unchanged", never "valid"; a mismatch = "changed", not flatly "corrupt"; no reference can PASS). Point caches only for now. **M3 fixes (certified 4 versions):** requested verification that can't run now returns nonzero incl. batch (B1); direct CAPTURE no longer forces overwrite (B2); an incomplete baseline can't PASS (B3, `S_INCOMPLETE_REF`); per-block streaming keeps a multi-GB hash cancellable/responsive (M1); a settings re-save preserves captured hashes (M2). **Still open:** fluid/GN hash coverage, Blender-decode verification, stale-topology (`totpoint` vs mesh).
3. ~~HTML report — only text + JSON today (Cache Commander ships HTML).~~ ✅ SHIPPED (2026-11-16): self-contained HTML report + `--html`.
4. Persistent **dismissal** of intentional findings — state is transient (Triage persists it).
5. Jump-to-fix buttons cover checks 1–23 only; 24–26 have none. Stale docstring in checks_cache.py ("17-23" → actually 17-26).
6. No repair actions (by design) — the hybrid decision.

---

## The plan (recommended order: win our lane → widen → go beyond → repairs)

### PHASE 1 — Finish & extend our own lane (read-only). Beat every cache tool outright.
- ✅ **Hair-particle + Dynamic Paint vertex cache coverage** (2026-11-16). Follow-up: Dynamic Paint IMAGE-sequence surfaces.
- ✅ **HTML report** (2026-11-16).
- ✅ **Deep content integrity (structure + baselined hashes)** (2026-11-16): `.bphys` header/type structure check (#17/#18) + on-demand per-frame SHA-256 change detection vs a saved baseline (#27, review M2). #27 point-cache increment **ACCEPTED** by independent review (2026-11-18, commit e460744, B1–B7 closed). **Fluid cache hash coverage SHIPPED (2026-11-18)** — per-stage SHA-256 of Mantaflow data/noise/mesh/particles/guiding/config, tested on real bakes across all 4 versions (incl. 4.2); layouts in [FLUID_GN_CACHE_NOTES.md](FLUID_GN_CACHE_NOTES.md). **Geometry Nodes disk-bake hash coverage SHIPPED (2026-11-19; hardened 2026-11-20, review B1/B2/M1)** — meta + blob hashing for DISK bakes on **all four versions** (4.2 included: packed storage is a 4.3+ feature, so a 4.2 sim bake is always disk and is hashed via `bake_directory`; verified on real 4.2 bakes). Packed bakes (4.3+) stay "Couldn't verify", never hashed. Interior-frame holes are caught via the contiguous present-frame span (`S_INCOMPLETE_REF`, never a false complete-coverage PASS); real blob dependencies — the shared first-frame topology blob every later frame references — are hashed by name, so a deleted dependency floors a verify. Next: Blender-decode verification (Phase 3), render preflight, competitor parity, guided repairs.
- **Persistent dismissal** of intentional findings (stored in scene props, like Triage; shown as "acknowledged").
- Polish: extend jump-to-fix to #24–26; fix stale docstring.
- Every item ships with failure fixtures + tests + cross-version check.

### PHASE 2 — New "Render Readiness" check group. Beat the generalists (Triage/Preflight/RabbidRender/SceneCheck/RenderForge).
- Camera present & render-enabled; output path set & writable; missing/ unpacked / absolute-path textures; render-settings sanity (very-high samples, no-denoise, CPU-with-GPU-idle, motion-blur-no-animation); frame-range vs animation; color-management clipping; compositor outputs connected; transparency→no-alpha format; frames-already-in-output (overwrite) warning.
- Optional: **real render-time probe** (render a small frame to measure, like Preflight) with full settings-fingerprint restore — read-only guarantee preserved.
- Pick the ~15–25 genuinely useful checks; do NOT inflate to a 98-count generalist.

### PHASE 3 — Beyond: features nobody has.
- **Subprocess cache-load verification**: actually ask a headless Blender to load the cache and confirm it reads — the deepest possible proof short of rendering.
- **Baseline history / diff over time**: "what changed since last scan" (better than Cache Commander's basic compare).
- **Farm/portability verdict**: one bundled check that answers "will this render the same on another machine?" — rolls up version, engine, add-on, path, cloud, and cache-completeness into a single go/no-go.

### PHASE 4 — Hybrid repairs (LAST, per decision). Opt-in, authorized, transactional, preview + backup + one-click rollback; read-only stays the default.
- First: delete orphan caches (#25 already computes them).
- Then: re-bake stale/incomplete sim (Cache Guardian parity), add missing collider (#07), relativize non-portable cache path (#22), reset FPS to baseline (#23).

### Cross-cutting (every phase)
Genuine failure fixtures (not synthetic), regression tests, real Blender acceptance on 4.2/4.5/5.0/5.2, adversarial review (ChatGPT as reviewer, not approver), and the cardinal rule: never a false PASS — UNKNOWN stays a first-class result. Price decided only after scope is built.
