# Failsafe — Feature Matrix & Competitor Notes (DRAFT)

> **DRAFT — pending independent review. Not published.** This is an internal
> strategy doc, not public copy (competitor names stay out of the store listing per
> the selling rule).
>
> **Verification status (important):** competitor claims below are labelled by how
> they were checked. Only **Cache Commander** was re-verified against a live
> Superhive listing on **2026-11-13**. Other products and prices are recorded from
> the independent commercial review of the same date and were **not** independently
> re-confirmed here — they are marked accordingly. Unknown ≠ absent: where a rival's
> support for a capability isn't established by public evidence, it's shown as
> **? not verified**, never as "no."

Failsafe = **26 checks** (16 physics setup + 10 cache), read-only, with a GUI panel
**and** a headless CLI (one product — see "one product, two workflows" below). The
one thing that writes a file to disk is the user-clicked **Save Baseline** (an
external sidecar — never the `.blend`); Export writes only an in-memory Text
datablock.

## Honest comparison vs. the one verified overlapping tool (Cache Commander)

Cache Commander is a real Superhive cache tool whose own docs describe a folder
mode that checks **each `.blend` in its own background Blender instance**, isolates
files that won't open, leaves the open scene untouched, and writes folder reports —
i.e. it **overlaps Failsafe's batch-isolation mode**. So batch isolation is **not a
unique Failsafe feature.** Where Failsafe still differs:

| Capability | **Failsafe** | Cache Commander |
|---|:--:|:--:|
| Physics **setup** checks (mass, collision, RBW, pins, overlap…) | ✅ 16 checks | ? not verified (markets as a cache size/mover tool) |
| Cache present **on disk, every required frame** (per-frame, render-range) | ✅ | ? not verified (markets cache size/ownership, move/delete) |
| Honest **"Couldn't verify"** status (never a false pass) | ✅ | ? not verified |
| Orphaned / unclaimed cache files | ✅ #25 | ✅ (flags stale/unclaimed; can move/delete) |
| Per-sim + total cache disk usage | ✅ | ✅ |
| Per-file **background-process folder/batch** mode, crash/hang isolated | ✅ (`--batch`, subprocess + `--timeout`) | ✅ (own background Blender per file; isolates bad files) |
| Headless exit codes for pipelines | ✅ `0/1/2/3` | ? not verified |
| Report output | ✅ text + JSON (to a Text datablock in-GUI; JSON to stdout headless) | ✅ folder reports |
| Read-only scan (never edits scene/`.blend`) | ✅ | ? not verified (docs say it leaves the open scene untouched; it can delete/move cache *files* on request) |

Legend: ✅ established · ? not verified (no public evidence either way) · — only when
a definite "no" is actually supported by evidence.

**Supportable differentiators (the ones to lead with):** physics-setup diagnostics
**plus** per-frame, required-range cache-file verification in one read-only tool,
with transparent "Couldn't verify" uncertainty and an optional headless workflow.
**Do not** claim batch isolation is unique.

**Not claimed (scope, by choice):** general render-readiness (missing textures, no
camera, output paths); Alembic (`.abc`) cache verification and an HTML report are
possible future work.

## Observed competitor list prices (reference only — provenance labelled)

Public **list prices**, not verified sales or willingness-to-pay data. Recorded from
the independent commercial review dated **2026-11-13**; only Cache Commander was
re-checked here.

| Product | Reported list price | Verification (2026-11-13) |
|---|---|---|
| SceneCheck | $3 | Per review; **not re-verified here** |
| Triage | $9.99 | Per review; **not found** in my Superhive search — unverified |
| Preflight | $9.99 | Per review; **not found** in my Superhive search — unverified |
| Cache Guardian | $14 | Per review; **not re-verified here** |
| Cache Commander | $29 | Superhive product/docs page confirmed to exist; **$29 seen on a reseller mirror (Getly)**, not scraped from the Superhive page itself |

Links: [Cache Commander (Superhive)](https://superhivemarket.com/products/cache-commander--see-what-your-simulations-weigh-and-move-them) ·
[Cache Commander docs (background-process batch)](https://superhivemarket.com/products/cache-commander--see-what-your-simulations-weigh-and-move-them/docs) ·
[Cache Commander price mirror (Getly, third-party)](https://www.getly.store/product/cache-commander-see-what-your-simulations-weigh-and-move-them-muq21n45)

> **Before any public use:** re-open each Superhive listing and record the price and
> feature claims directly from the live page, with the date. Do not restate the
> unverified rows above as established fact.

## Pricing — UNDECIDED (owner decision)

No price is set, and no savings or demand figure is asserted. The review suggested
$9.99 / $12 / $14 as *test* prices to evaluate (a preference for $12 one-time as an
experiment, below Cache Guardian's reported $14) — these are options to consider,
**not** externally established values and **not** a decision. A separate higher
"Pipeline" SKU is **not** planned: the GUI and headless workflows ship together in
one product, and Cache Commander's reported $29 does not establish what Failsafe
could charge.

## One product, two workflows (not two editions)

Failsafe is a **single add-on** with two ways to use it. There is **no** separate
"Consumer" vs "Pipeline" SKU — both ship together.

| Workflow | Surface | Modules | Writes anything? |
|---|---|---|---|
| **GUI (artists)** | 3D-viewport panel: Scan, Select Object, Explain, Export Text/JSON Report, Save Baseline | `ui.py`, `operators.py`, `handlers.py` (opt-in render banner) | Only on an explicit click: Export adds an in-memory Text datablock; Save Baseline writes an external sidecar — never the `.blend`, never scene data |
| **Headless (pipelines)** | `cli.py` (exit codes, `--json` to stdout), `batch.py` (isolated `--batch`, `--timeout`) | `cli.py`, `batch.py` | No — read-only; prints a report and sets an exit code |
| **Shared core** | the actual checks + verdicts | `engine.py`, `checks_setup.py`, `checks_cache.py`, `cache_inspect.py`, `baseline.py`, `report.py` | No (scans are read-only) |

The GUI never imports the headless `batch.py`; the headless path never needs the
GUI. Both run the same shared check core, so a finding is identical whether a person
clicks Scan or a farm runs the CLI.

## Exit codes (headless)

| Code | Meaning |
|---|---|
| 0 | clean — no FAIL, nothing unverified. **WARNINGs alone still return 0 unless `--strict`** (then a WARNING blocks → 1). A 0 means "no failures," not "no warnings." |
| 1 | blocking — at least one FAIL (with `--strict`, a WARNING too) |
| 2 | unverified — no FAIL, but something is "Couldn't verify" |
| 3 | usage/internal — bad args, or a file that couldn't be opened/scanned (incl. a batch file that crashed or timed out) |

In a batch, the worst code wins, with a blocking FAIL (1) ranking above an
error (3) and an error ranking above unverified (2) and clean (0).
