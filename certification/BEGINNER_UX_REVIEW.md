# Failsafe — First-Time-User (Beginner) UX Review

> **DRAFT — heuristic review, not a substitute for a real naive-user session.**
> This is an expert walkthrough of the live panel (build `933ea17`, Blender 5.2.3)
> from a first-time-user lens. A genuine beginner-acceptance test still needs an
> actual first-time user sitting down with it; this catches the obvious friction
> ahead of that. No code was changed (per the "no redesign / no new features"
> direction) — the items below are recommendations for a future polish pass.

## What already works well for a newcomer

- **Safe, reassuring empty state.** Before scanning, the panel says *"Press Scan
  Scene to check this scene."* and *"Read-only scan — your scene, caches and files
  are never changed."* That's exactly the right first impression.
- **One obvious action.** **Scan Scene** is the big, top button (magnifier icon);
  there's no ambiguity about where to start.
- **Plain-English findings.** Each problem has a short headline, a word-wrapped
  reason, and a **Tip:** next step — no Blender jargon required to act.
- **Honesty is visible.** "Couldn't verify" items show their reason and next step,
  and a collapsed problem row still shows a one-line "why" (never a bare dot).
- **Guided fixes.** "Open Physics settings (Object)" jumps a beginner straight to
  the tab where the fix lives; "Select Affected Object" for the rest.
- **Clear button labels:** Scan Scene · Export Text Report · Export JSON Report ·
  Save Settings Baseline · Select Affected Object · Open Physics Settings.

## Minor friction (recommendations, not defects)

1. **Icon-only toggles.** The Export-JSON, "show passed" (eye) and "Explain" (?)
   controls are icon-only. They have hover tooltips, so they're discoverable, but a
   first-timer may not realise the eye reveals passed checks or that "?" turns on
   explanations. *Optional:* a tiny text label, or a one-line hint under the row.
2. **"Baseline" is jargon.** "Save Settings Baseline" is powerful but unexplained
   inline; a newcomer won't know what a baseline is or when to click it until they
   read the tooltip. *Optional:* a one-line caption ("Snapshot current sim settings
   so later scans can flag changes — writes an external file, never your .blend").
3. **Explanations are off by default.** The "why it matters" lines (Explain mode)
   are hidden until the "?" toggle is on. Beginners benefit most from them.
   *Optional:* leave off (keeps the list tidy) but consider a first-run nudge.
4. **No single headline verdict after a scan.** The panel shows a coloured tally
   (3 / 1 / 2) and grouped results, but no one-line "⚠ 3 problems found" / "✓ All
   clear" summary at the very top. The tally conveys it, but a headline would land
   faster for a beginner. *Optional.*

## Verdict

The core first-time experience is **clear, safe, and actionable** — a beginner can
scan, understand a finding, and jump to the fix without help, and the read-only
promise is stated up front. The items above are small polish opportunities, none
blocking. **A real first-time-user session is still recommended** before calling
the beginner-acceptance gate formally closed; this review is the heuristic
pre-pass, not that session.
