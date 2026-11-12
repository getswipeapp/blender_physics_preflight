# Failsafe — Feature Matrix (DRAFT)

> **DRAFT — pending independent review. Not published.** Competitor rows are from
> their live product pages read 2026-11-12; re-confirm before using publicly.
> Prices are the competitors' own list prices at that date.

Failsafe = **26 checks** (16 physics setup + 10 cache), read-only, GUI **and**
headless, with a crash-isolated batch mode for render farms. The one thing that
writes is the user-clicked **Save Baseline** (an external sidecar — never the
`.blend`).

## Failsafe vs the cache/sim competitors

| Capability | **Failsafe** | Cache Guardian ($14) | Cache Commander ($9.99) | SceneCheck ($3) | Render Ready ($19+) |
|---|:--:|:--:|:--:|:--:|:--:|
| Physics **setup** checks (mass, collision, RBW, pins…) | ✅ 16 | — | — | — | — |
| Cache present **on disk, every required frame** | ✅ per-frame | ~ samples | ~ first/last | — | — |
| Honest **"Couldn't verify"** (never a false pass) | ✅ | — | — | — | — |
| Settings-changed-since-baseline (opt-in) | ✅ #26 | ✅ | ✅ | — | — |
| Cloud-synced cache-folder warning | ✅ #24 | ✅ | — | — | — |
| Orphaned cache files | ✅ #25 | — | ✅ | — | — |
| Per-sim + total cache disk usage | ✅ | — | ✅ | — | — |
| Headless CLI with exit codes | ✅ 0/1/2/3 | — | ✅ | — | — |
| **Batch a folder** of `.blend`s headless | ✅ | — | ✅ | — | — |
| **Crash/hang-isolated batch** (subprocess + timeout) | ✅ | — | — | — | — |
| JSON report output | ✅ | — | ✅ (HTML) | ✅ | — |
| Read-only (never edits the scene/`.blend`) | ✅ | ? | ? | ? | ? |
| Fully offline (no account/telemetry) | ✅ | ? | ? | ? | ? |

Legend: ✅ yes · ~ partial · — no · ? not stated on the page.

**Where Failsafe leads:** per-frame disk verification, an honest "Couldn't verify"
status, physics-setup **and** cache checks in one tool, and — unique here — a
**crash/hang-isolated** batch mode built for render farms. Target price **$12**
sits under Cache Guardian and at/under the others while covering more.

**Not claimed (scope, by choice):** general render-readiness (missing textures, no
camera, output paths) is SceneCheck/Render Ready territory and is deliberately out
of scope for v1; Alembic (`.abc`) cache verification and an HTML report are Phase 2.

## Modularity — consumer vs pipeline (kept separate)

| Edition | Surface | Modules | Writes anything? |
|---|---|---|---|
| **Consumer** (GUI) | 3D-viewport panel: Scan, Select Object, Explain, Export, Save Baseline | `ui.py`, `operators.py`, `handlers.py` (render banner) | Only on an explicit click (Export, Save Baseline) — never the `.blend` |
| **Pipeline** (headless) | `cli.py` (exit codes, `--json`), `batch.py` (isolated `--batch`, `--timeout`) | `cli.py`, `batch.py` | No — read-only; prints a report and sets an exit code |
| **Shared core** | the actual checks + verdicts | `engine.py`, `checks_setup.py`, `checks_cache.py`, `cache_inspect.py`, `baseline.py`, `report.py` | No (scans are read-only) |

The consumer GUI never imports the pipeline's `batch.py`; the pipeline never needs
the GUI. Both run the same shared check core, so a finding is identical whether a
person clicks Scan or a farm runs the CLI.

## Exit codes (pipeline)

| Code | Meaning |
|---|---|
| 0 | clean — no FAIL, nothing unverified |
| 1 | blocking — at least one FAIL (with `--strict`, a WARNING too) |
| 2 | unverified — no FAIL, but something is "Couldn't verify" |
| 3 | usage/internal — bad args, or a file that couldn't be opened/scanned (incl. a batch file that crashed or timed out) |

In a batch, the worst code wins, with a blocking FAIL (1) ranking above an
error (3) and an error ranking above unverified (2) and clean (0).
