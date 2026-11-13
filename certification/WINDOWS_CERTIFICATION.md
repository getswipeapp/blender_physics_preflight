# Failsafe — Windows Certification (real execution)

> **DRAFT evidence — pending owner sign-off.** Real Windows execution on GitHub
> Actions hosted `windows-2025` runners, against official Blender Windows x64
> portable builds. No Windows computer purchased; no secrets; disposable fixtures
> only. Source under test: branch `failsafe-expanded-hardening`, build `933ea17`
> code (commit at run time `bda8b6d`). Date: 2026-11-13.

**Workflow:** `.github/workflows/windows-cert.yml` (runner `windows-2025`).
**Run:** <https://github.com/getswipeapp/blender_physics_preflight/actions/runs/43472730612>
— all four matrix jobs **success**. Logs preserved under
`certification/results/windows/`.

## Headless test suite — 292/292 on every Windows version

| Blender (Windows x64) | Result | Log |
|-----------------------|--------|-----|
| **4.2.9 LTS** | ✅ 292 passed, 0 failed | `results/windows/run_win_4.2.9.log` |
| **4.5.9 LTS** | ✅ 292 passed, 0 failed | `results/windows/run_win_4.5.9.log` |
| **5.0.1** | ✅ 292 passed, 0 failed | `results/windows/run_win_5.0.1.log` |
| **5.2.3 LTS** | ✅ 292 passed, 0 failed | `results/windows/run_win_5.2.3.log` |

Downloaded from download.blender.org (official Windows x64 zips), extracted and
run headless (`-b --factory-startup -P tests/run_tests.py`) on the hosted runner.

## Functional acceptance (Windows, 5.2.3) — 24/24

`results/windows/win_acceptance_5.2.3.log` — the extension was **built** on
Windows (`--command extension build`), **installed**
(`extensions.package_install_files`, result `FINISHED`), **enabled**, and its real
operators exercised headlessly:

- Extension imports, **26 checks** registered, **Save Baseline** + **Export JSON**
  operators registered; `label(UNKNOWN)` = "Couldn't verify".
- **Save Baseline** wrote the external sidecar at the correct Windows path and left
  the `.blend` **byte-identical** (SHA before == after).
- #26 **PASS** after save; **WARNING** after a tracked setting changed.
- Overwrite: no-overwrite **CANCELLED + preserved**; explicit overwrite **replaced**.
- **Export JSON** valid, keeps the machine token `UNKNOWN`, never emits the display
  word "Couldn't verify", 26 checks.
- "Couldn't verify" carries a reason + next action.
- An ordinary scan wrote **no files** and left the `.blend` unchanged.
- **CLI exit codes via a real child process on Windows:** `--help` → 3, bad arg →
  3, clean scan → 0.

> This is **headless** functional acceptance, not GUI acceptance. GUI acceptance
> was done separately on macOS (`GUI_ACCEPTANCE_933ea17.md`); a Windows GUI session
> is not claimed here.

## Real multi-process batch (Windows, 5.2.3) — PASS

`results/windows/real_batch_win_5.2.3.log` — Blender spawned **actual child Blender
processes** on Windows (paths like `C:\Users\…\Temp\…`):

- a real `good.blend` scanned clean in its own process;
- a real `corrupt.blend` → an **actual failed worker**, isolated as a per-file
  error, with the good file's result preserved (overall exit 3);
- a genuinely hanging child (`time.sleep(60)`) **killed at a 3 s timeout** and
  recorded as a timeout.

`REAL BATCH PROOF: ALL CHECKS PASSED (real subprocesses)`.

## Issues found during certification (CI harness, not the add-on)

Both were defects in the certification plumbing; neither is a Failsafe
compatibility problem (the suite passed on the same builds throughout):

1. `extension build --output-dir ./dist` failed on Windows ("No such file or
   directory: ./dist\.failsafe-1.0.0.zip") — the `dist/` dir didn't exist and a
   forward-slash relative path confused Blender's builder. Fixed: create the dir
   and pass resolved native paths.
2. `blender -b` didn't auto-enable the just-installed extension (the install
   enabled it in-memory but didn't persist prefs), and Blender exited 0 even after
   the script failed. Fixed: the acceptance script `addon_utils.enable()`s the
   extension, the install step saves userprefs, and the workflow step now fails on
   any `FAIL -` line instead of trusting Blender's exit code.

## Scope

Prior macOS/Linux certification evidence (§0/§−1 of `RUNTIME_CERTIFICATION.md`) is
**preserved unchanged**. This adds Windows. Not covered: a Windows **GUI** session,
and ARM-Windows (the runners are x64).
