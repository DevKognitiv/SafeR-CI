# QA documents

The quality gates of the SafeR app and hub are written down here so that a screen, an adapter
or a performance number is never called "done" or "verified" on someone's word. Everything in
this folder is English with the French UI strings quoted as they appear in the app.

## Index

| File | What it is | Read it when |
|---|---|---|
| [state-matrix.md](state-matrix.md) | Every route × every state, `exists` / `missing` / `n/a` as of today, with the fake-client switch that forces each state. The enumeration the golden and screenshot jobs read. | Adding a route or a state, writing goldens, planning a screen PR. |
| [screen-rubric.md](screen-rubric.md) | The 10-criterion weighted rubric, the colour-vision simulation step, blocking findings, the sign-off rule and the score-sheet template. | Reviewing captures, approving a screen, reading a score. |
| [device-capture.md](device-capture.md) | How evidence from real phones reaches the repo: adb and Test Lab commands, the reference device matrix, perf capture, file naming, the "pending hardware" rule. | Attaching a device capture, recording a performance number. |
| [hardware-status.md](hardware-status.md) | Badges per adapter and per external contract, what CI mocks, the human checklist that flips a badge. The only source for a "verified" claim. | Writing release notes or About copy, running a hardware session. |
| [talkback.md](talkback.md) | TalkBack (and VoiceOver if iOS is go) walkthrough checklists for Login, Home, Security, SOS, pairing wizard and device panel. | Before signing off one of the six key screens. |
| [golden-harness.md](golden-harness.md) | The golden-test harness: bundled Manrope/Inter subsets, the 0.1 % tolerant comparator, the variant matrix, how to add or regenerate a golden, the 2 px proof run and the CI steps. | Adding a golden, reading a golden failure, changing fonts. |
| [a11y-baseline.md](a11y-baseline.md) | The accessibility guideline baseline of the Home screen (tap targets, labels, contrast) with the one recorded exception and the text-scale 2.0 findings for Phase 1. | Changing a tap target, a label or a status colour; planning Phase 1 fixes. |
| screen-signoff.md | One row per signed-off screen with commit SHA, scores, evidence and capture paths. Created by the first sign-off. | Checking whether a screen may ship. |
| perf-baseline.md | Measured budgets per reference device, "pending hardware" until a trace is committed. Created by the first measurement. | Quoting any performance number. |
| captures/ | Device evidence named `<date>-<device>-<screen>[-<state>][-<variant>]`. | — |

Related: `../decisions/` (product decisions the gates depend on), `../contracts/` (hub and
relay contracts the states refer to).

## Sign-off flow for a screen

1. **Scope**: the implementer lists the route's states from `state-matrix.md` and adds the
   French copy for any `missing` state the PR introduces; `missing` cells flip to `exists` in
   the same PR.
2. **Pixels**: goldens for every state × variant land under `mobile/test/goldens/`; the golden
   job is green; the accessibility guideline tests and the token contrast test pass.
3. **Critique loop**: the Playwright job captures the Demo home for the route in every variant;
   two reviewer agents (design lens, accessibility lens) fill a score sheet each
   (`screen-rubric.md` §6), including the colour-vision simulation. Exit when both scores are
   ≥ 8.0/10 for every variant with no blocking finding; otherwise the findings go back to the
   implementer and the loop repeats.
4. **Screen reader**: the TalkBack checklist for the screen is ticked (six key screens).
5. **Human or device**: the product owner approves the screen, or a device capture of the same
   commit is attached per `device-capture.md`. Web captures alone never count.
6. **Record**: a row is added to `screen-signoff.md` with the commit SHA, both scores,
   "none" under blocking, the colour-vision result, the evidence and capture paths, who signed
   and when. A later commit touching the route resets the row to pending (the golden diff is
   the trigger).

## Rules that apply across the folder

- A route or matrix state without a golden fails CI.
- Red is for alarm, SOS and destructive confirmations only; every status colour has a glyph
  and a word; the colour-vision step checks it on every variant.
- Performance numbers read "pending hardware" until the trace behind them is committed and
  referenced from `perf-baseline.md`; the web perf proxy is never quoted as an Android number.
- Adapters and contracts carry the badge from `hardware-status.md` and nothing more; an
  automated agent never flips a badge.
- Captures show the Demo home only; no real address, member, phone number or camera still is
  committed.
