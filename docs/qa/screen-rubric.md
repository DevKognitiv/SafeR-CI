# Screen rubric — how a screen is scored and signed off

Used by the two reviewer agents of the critique loop (design lens, accessibility lens), by the
product owner when approving a screen, and by anyone reading `docs/qa/screen-signoff.md`. A
screen is scored **per variant**: light/dark × fr/en, at 360×780 and 412×915 dp, from the
Playwright captures of the Demo home (`--dart-define=SAFER_DEMO=1`), plus the states listed for
the route in `docs/qa/state-matrix.md`.

Web captures are a critique instrument. They never constitute sign-off on their own (§5).

## 1. The ten criteria

Each criterion is scored 0–10. The screen score is the weighted mean, rounded to one decimal.

| # | Criterion | Weight | 10 looks like | 0 looks like |
|---|---|---|---|---|
| 1 | **Hierarchy** | 12 | One obvious primary action per screen; the state of the home (armed / ready / alarm) or of the device is the first thing read; secondary data recedes. | Everything the same size; the primary action competes with chrome; the user has to hunt for "what now". |
| 2 | **Typography** | 8 | Bundled Manrope (display) and Inter (body) from the token text theme only; tabular figures on values and times; no `fontSize` literal in `features/`; line lengths under 60 characters. | Stock font, ad-hoc sizes, proportional digits jumping in counters, titles wrapping to three lines at 1.0. |
| 3 | **Spacing and rhythm** | 8 | Every gap comes from the spacing scale (`SafeRSpace`); consistent card insets; groups separated more than items within groups; 16 dp side gutters on phones. | Mixed 12/14/18 paddings, cards touching the edge, orphaned headers at the bottom of the viewport. |
| 4 | **Colour discipline** | 12 | Red appears **only** for an active alarm, the SOS control and destructive confirmations; armed is teal, ready/disarmed is green, warnings amber; accent and attention never share a component; every status colour is paired with a glyph **and** a word. | Red on "Absent" (today's `forSecurityMode('armed_away')`), coloured text as the only cue, brand blue used as a state. |
| 5 | **State honesty** | 14 | Every state of the route's matrix row renders a dedicated view with French copy; cached data carries an age; offline is a state, not an error; commands show pending/acknowledged/failed; no raw exception text; relative ages hidden when the hub clock is unsynced. | Spinner forever, "ApiException(...)" on screen, controls that silently snap back, "il y a 56 ans". |
| 6 | **Touch targets** | 10 | Every tappable area ≥ 48×48 dp (arm control ≥ 56 dp, SOS ≥ 72 dp) with ≥ 8 dp between targets; long-press actions have a visible alternative. | 32 dp icon buttons, chips that cannot be hit with a thumb, adjacent toggles with no gap. |
| 7 | **Contrast AA** | 10 | Every text/background pair ≥ 4.5:1 (≥ 3:1 for ≥ 18 sp bold, icons and focus rings) in light, dark and outdoor; verified from the token file, not by eye. | Amber-on-white banners (today's `warning` on `0.14` alpha), white on light teal, placeholder grey under 3:1. |
| 8 | **Text scaling 2.0** | 8 | At `textScaler: 2.0` on a 360 dp frame nothing overflows, no label is clipped or ellipsised, grids re-flow, dense chrome clamps at 1.4× only. | Fixed-height tiles cutting the second line, `RenderFlex overflowed` stripes, state words truncated to "ALAR…". |
| 9 | **French copy quality** | 10 | Sentence case everywhere ("Alarme déclenchée", not "ALARME DÉCLENCHÉE"); no ALL-CAPS state words; no emoji glyphs; gendered state words agree ("Allumée · 80 %"); narrow no-break space before `%`, `°C` and `:`; plain words for consumers, protocol jargon only behind "Options avancées"; English has full parity. | "EN LIGNE", an emoji check mark before "Alerte transmise" (today's SOS screen), "Access ID" on a consumer screen, hub exception text in English inside a French screen. |
| 10 | **Dark mode parity** | 8 | Dark variant is a first-class design: same hierarchy, same contrast, elevation expressed by tone not shadow, no pure black, brand mark adapts; images and snapshots have a dark placeholder. | Light-only assets on a dark canvas, invisible dividers, white cards glowing on black. |

Weights sum to 100; `score = Σ(weight × criterion) / 100`.

## 2. Colour-vision simulation step (mandatory, every variant)

Teal (armed) versus green (ready) is a confusable pair for roughly 5 % of men. The plan asserts
"colour is never the only cue"; this step **checks** it.

1. Take the light and dark PNGs of the screen in its armed, ready and alarm states (and any
   state that uses a status colour: offline, warning, pending).
2. Produce a deuteranopia and a protanopia simulation of each PNG. The capture harness does it
   with a Brettel/Viénot/Mollon matrix filter (`mobile/tool/screenshots/simulate_cvd.py`, output
   next to the capture as `<name>.deutan.png` and `<name>.protan.png`); a manual reviewer may
   use any equivalent filter.
3. Checklist, each item pass/fail:
   - Armed, ready and alarm remain distinguishable **without** reading colour: each has its own
     glyph (shield / shield-check / siren) and its own word ("Armée", "Prête", "Alarme").
   - No information is carried by hue alone: battery, signal, online/offline, pending, error
     chips all keep an icon or a word.
   - The SOS control is still the most salient element in the simulation.
   - Charts and dials (energy, temperature) keep readable series by pattern, label or order.
4. Any fail is a **blocking finding** (§3). The simulation files are referenced from the
   score sheet.

A greyscale golden variant of Home and Security (definition of done) is the automated
counterpart of this step; it does not replace the checklist for the other screens.

## 3. Blocking findings

A blocking finding stops sign-off regardless of the score. The reviewer writes it as
`BLOCKING: <criterion> — <what> — <where>`.

- Any criterion scored **3 or lower**.
- Red used outside alarm / SOS / destructive confirmation (criterion 4).
- A state colour without glyph + word, or a colour-vision checklist fail (§2).
- A text/background pair under AA in any variant (criterion 7), measured from tokens.
- Any overflow or clipped label at text scale 2.0 (criterion 8).
- Raw exception text, an infinite spinner, or a matrix state rendered as a generic error
  (criterion 5).
- A tappable target under 48 dp, or the SOS control under 72 dp (criterion 6).
- ALL-CAPS state words or emoji glyphs in user-visible copy (criterion 9).
- Missing English string for a French one (parity test failure).
- An "Installateur"-level field (hub URL, Access ID/Secret, hex Matter id, protocol id) visible
  on a consumer surface without the "Options avancées" gate.
- Motion that loops while idle (except the SOS pulse on its own route) or that ignores
  `disableAnimations`.
- Anything that would fail the Play reviewer cross-check (cleartext, missing permission
  rationale, credentials on screen).

## 4. Scoring procedure for reviewer agents

1. Read `docs/qa/state-matrix.md` for the route; list the states and variants to review.
2. Open every capture (and its colour-vision simulations) for the screen; read the PNGs, do
   not infer from code.
3. Fill one score sheet (§6) per screen, scoring each variant; the screen's score is the
   **lowest** variant score.
4. List findings, blocking first, each with criterion, variant, capture path and a concrete
   fix.
5. The design lens weighs criteria 1–4 and 10 in its narrative; the accessibility lens
   weighs 5–9 and runs §2. Both score all ten.

Two reviewer agents are two automated passes, not independent verification. They are good at
finding what is wrong in a PNG and bad at knowing what a Tecno Spark Go does with haptics,
font scaling or the native splash. That is what §5 is for.

## 5. Sign-off rule

A screen is **signed off** for a commit when all of the following hold:

1. **Critique loop passed**: both reviewer agents scored the screen ≥ 8.0/10 for every
   required variant (light/dark × fr/en at 360×780 and 412×915, plus 600 dp for Home and
   Security), with **no blocking finding**, and the colour-vision step raised nothing.
2. **Verified by a human or a device**: the product owner approved the screen (a written
   approval in the PR or in `docs/qa/screen-signoff.md`), **or** an Android capture of the same
   screen at the same commit is attached, from Firebase Test Lab, remote adb or a user-recorded
   phone (`docs/qa/device-capture.md`).
3. The goldens for the route and its matrix states are committed and the golden job is green.
4. The TalkBack checklist for the screen (`docs/qa/talkback.md`) is ticked, for the six key
   screens.

The record goes in `docs/qa/screen-signoff.md`, one row per screen:

```
| Route | Commit | Design score | A11y score | Blocking | CVD pass | Human/device evidence | Captures | Signed by | Date |
| /security | b8880be | 8.4 | 8.1 | none | pass | docs/qa/captures/2026-10-18-galaxy-a05-security.png | mobile/tool/screenshots/out/security/… | product owner | 2026-10-18 |
```

A later commit that touches the route resets the row to "pending" (the golden diff is the
trigger). Web captures alone never fill the evidence column.

## 6. Score-sheet template

Copy into the PR description or into `docs/qa/reviews/<date>-<route>-<lens>.md`.

```markdown
# Score sheet — <route> — <design | accessibility> lens

Commit: <sha>
Captures reviewed: <paths or artifact URL>
Colour-vision simulations: <paths> (accessibility lens)
States reviewed (from the state matrix): <list>

## Scores per variant (0–10)

| Criterion (weight)            | light/fr/360 | dark/fr/360 | light/en/360 | dark/en/360 | light/fr/412 | dark/fr/412 | 600 dp (Home/Security) |
|-------------------------------|--------------|-------------|--------------|-------------|--------------|-------------|------------------------|
| 1 Hierarchy (12)              |              |             |              |             |              |             |                        |
| 2 Typography (8)              |              |             |              |             |              |             |                        |
| 3 Spacing and rhythm (8)      |              |             |              |             |              |             |                        |
| 4 Colour discipline (12)      |              |             |              |             |              |             |                        |
| 5 State honesty (14)          |              |             |              |             |              |             |                        |
| 6 Touch targets (10)          |              |             |              |             |              |             |                        |
| 7 Contrast AA (10)            |              |             |              |             |              |             |                        |
| 8 Text scaling 2.0 (8)        |              |             |              |             |              |             |                        |
| 9 French copy quality (10)    |              |             |              |             |              |             |                        |
| 10 Dark mode parity (8)       |              |             |              |             |              |             |                        |
| **Weighted score**            |              |             |              |             |              |             |                        |

Screen score (lowest variant): <x.x>/10

## Colour-vision checklist (accessibility lens)

- [ ] armed / ready / alarm distinguishable by glyph and word under deuteranopia
- [ ] same under protanopia
- [ ] no hue-only information (battery, signal, online, pending, error)
- [ ] SOS control remains the most salient element
- [ ] charts/dials readable by pattern or label

## Findings (blocking first)

- BLOCKING: <criterion> — <what> — <variant, capture path> — fix: <concrete change>
- <criterion> — <what> — <where> — fix: <…>

## Verdict

<pass ≥ 8.0 with no blocking | fail> — next action: <…>
```
