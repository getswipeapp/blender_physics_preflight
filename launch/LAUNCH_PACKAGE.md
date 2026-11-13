# Failsafe — Launch Package (DRAFT for independent review)

> **DRAFT — nothing published, merged, priced, or sent. Not finished.**
> Prepared in response to the "WINDOWS EVIDENCE ACCEPTED; PREPARE SALES MATERIALS"
> directive. This is the single entry point for the reviewer: it lists every launch
> document and maps each directive item to where it's satisfied, then separates what
> has been independently verified from what remains an owner decision.

## Contents of this package

| Document | What it is |
|---|---|
| `launch/STORE_LISTING.md` | The Superhive product-page copy: headline, hook, short description, who it's for, the problem, all 26 checks, what makes it different, how it works, artist-vs-pipeline split, **FAQ**, honest limitations, requirements, licensing, **pricing (UNDECIDED)**. |
| `launch/INSTALL_GUIDE.md` | Beginner install + first-scan guide (reuse on the product page; Superhive wants install + FAQ **on the page**). |
| `launch/LIMITATIONS.md` | Full honest "what it can and can't do," including every UNKNOWN/NA case. |
| `launch/DEMO_SHOTLIST.md` | Shot-by-shot plan for **real** screenshots + an optional demo video. No mockups. |
| `strategy/FEATURE_MATRIX.md` | Capability matrix vs. competitors (factual list prices only) and the consumer-vs-pipeline module split. |
| `README.md` | Repo-level overview (the 26 checks, read-only guarantee, versions). |

## Directive items → where addressed

1. **Complete store listing** (headline, short description, features, FAQ, compatibility, installation, limitations) → `STORE_LISTING.md` (FAQ + "Two ways to run it" added this round) and `INSTALL_GUIDE.md`.
2. **Artist-facing vs headless/Pipeline, clearly separated** → `STORE_LISTING.md` § "Two ways to run it (artist vs. pipeline)" and `FEATURE_MATRIX.md` § "Modularity — consumer vs pipeline."
3. **Screenshot shot-list from real Blender output, no fabricated UI/results/testimonials** → `DEMO_SHOTLIST.md` (explicitly real-scene-only; a repeatable fixture generator offered but not faked).
4. **Beginner install + first-scan guide** → `INSTALL_GUIDE.md`.
5. **Every claim reconciled against reviewed source + test evidence** → check descriptions already match the fixed build (R19–R27); versions/counts (26 checks, 292 tests, 4.2.9/4.5.9/5.0.1/5.2.3, macOS + Windows x64 headless) cite `certification/`. No "guaranteed render," "universal cache verification," or "Windows GUI certified" claims remain (see FAQ + LIMITATIONS).
6. **Pricing UNDECIDED; no invented demand/savings/revenue** → `STORE_LISTING.md` § Pricing now says UNDECIDED and removes the stack-cost/"half the price"/target-price framing; `FEATURE_MATRIX.md` target-price line removed. Competitor prices kept only as factual reference.
7. **Scans read-only; saving a baseline or exporting creates an external file** → stated in the short description, "How it works," FAQ, Requirements, and LIMITATIONS; baseline writes an **external** sidecar, never the `.blend`.
8. **No overclaims** (no guaranteed render success, universal cache verification, Windows GUI certification, or commercial render-farm integrations) → FAQ answers each explicitly; the pipeline section says "a command-line capability … **not** a bundled integration with any render-farm product."

## Commercial-review corrections (review of ebfd65e → this revision)

The independent commercial review (2026-11-13) blocked the **copy** (not the
engineering) and raised C01–C10 + polish. All are documentation-only fixes; code
claims were re-verified against the source before editing:

| ID | Correction made |
|---|---|
| **C01** | Batch isolation is **no longer called unique.** Cache Commander (verified on its live Superhive docs) offers a comparable per-file background-process folder mode; `FEATURE_MATRIX.md` now says so and records its **$29** reported price (reseller mirror). Lead differentiator is now frame-level cache verification + physics-setup + honest "Couldn't verify." |
| **C02** | **GUI exports corrected everywhere.** `Export Text Report` / `Export JSON Report` write a Blender **Text datablock** + clipboard — **no file-save dialog.** Docs now say you save it yourself from the Text Editor, that this changes the **in-memory** project (not the `.blend` on disk, never scene data), and that **headless `--json` prints to stdout.** Real button names used. |
| **C03** | Check #25 is now "**potentially unclaimed** cache files — review before deleting," never "safe to remove" (STORE_LISTING, LIMITATIONS, README). Matches the code's own cautious message. |
| **C04** | `FEATURE_MATRIX.md` replaces unsupported "— no" cells with **? not verified**; only Cache Commander was re-verified. |
| **C05** | Everywhere exit codes appear (LIMITATIONS, FEATURE_MATRIX, README): **exit `0` can include WARNINGs unless `--strict`** is now stated explicitly. (Verified in `cli.py` `verdict_exit_code`.) |
| **C06** | Licensing corrected: **Superhive permits GPL or MIT** for code products; Failsafe uses GPL-3.0-or-later (STORE_LISTING, README). |
| **C07** | Gallery requirement corrected in `DEMO_SHOTLIST.md`: **featured image + ≥1 additional** (Superhive recommends ~4–6), confirm on site. |
| **C08** | Removed the unsupported "other tools bluff / say all-good" generalization from `INSTALL_GUIDE.md`; reworded to describe Failsafe's own behaviour only. |
| **C09** | Removed the contradictory internal note; the macOS live-GUI acceptance **did** exercise Save Baseline + Export JSON (`GUI_ACCEPTANCE_933ea17.md`). |
| **C10** | Removed the unverified "Render Ready $19+" comparator from the matrix. |
| Polish | Real export button names in the guide; added the **opt-in non-cancelling "check before render"** feature (verified in `handlers.py`) to STORE_LISTING FAQ, LIMITATIONS, README; clarified GUI + CLI are **one product, two workflows** (no separate SKU); pricing stays UNDECIDED with observed prices recorded and provenance-labelled. |

## Independently verified (real execution evidence)

- Code review findings **R19–R27 all PASS** (two review rounds).
- Test suite **292/292** on Blender **4.2.9 / 4.5.9 / 5.0.1 / 5.2.3**, on **macOS and Windows x64** (headless). Windows run confirmed green on GitHub Actions.
- **Real multi-process batch isolation** on macOS **and** Windows (crash / corrupt / timeout-kill).
- **Read-only guarantee**: a scan writes nothing; Save Baseline leaves the `.blend` byte-identical.
- **macOS GUI acceptance** 9/9 (`certification/GUI_ACCEPTANCE_933ea17.md`).
- **Windows functional acceptance** 24/24, headless (`certification/WINDOWS_CERTIFICATION.md`).
- **Reproducible release artifact**: ZIP byte-identical to committed source; SHA in `certification/RELEASE_SHA256SUMS.txt`.

## Owner decisions / human gates (not code — yours to make)

1. A **real first-time-user session** — a genuine naive user tries install + first scan (only a heuristic pre-pass was done: `certification/BEGINNER_UX_REVIEW.md`).
2. **Final store assets** — the real screenshots (and optional video) per `DEMO_SHOTLIST.md`.
3. **Price** — currently UNDECIDED.
4. **Publication approval** and the merge/release action itself.
5. *(Optional)* a **Windows GUI** session — headless Windows is covered and macOS GUI is done.

Everything above remains **PENDING INDEPENDENT REVIEW / owner approval**. Nothing is
published or merged; `main` and the certified baseline are untouched.
