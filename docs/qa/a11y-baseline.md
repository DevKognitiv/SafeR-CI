# Accessibility baseline — Phase 0

What the first automated accessibility pass measured on the Home tab, what was fixed on the
spot, and what Phase 1 inherits. The companion test is `mobile/test/a11y/home_a11y_test.dart`;
the text-scale findings come from the goldens of `mobile/test/goldens/home_golden_test.dart`
(see `docs/qa/golden-harness.md`). The rubric these findings map to is
`docs/qa/screen-rubric.md` (criteria 6, 7, 8 and 9).

Frame: 360×780 logical px, device pixel ratio 1, `HomeFakeHubClient` (demo home, owner role,
three rooms, twelve devices). Guidelines: `flutter_test`'s `androidTapTargetGuideline`
(48×48 dp), `labeledTapTargetGuideline` and `textContrastGuideline` (WCAG AA, 4.5:1 below
18 sp / 14 sp bold), evaluated in **fr, light, text scale 1.0** only. Dark mode and text scale
2.0 are covered by the goldens (visually), not by the guidelines yet.

## 1. Results

| Guideline | Before Phase 0 fixes | After (asserted in CI) |
|---|---|---|
| Tap targets ≥ 48×48 dp | **fail** — home switcher 244×44 dp | pass |
| Every tap target labelled | **fail** — 8 device tiles (long-press node without label) | pass |
| Text contrast AA | pass only by accident (DEBUG ribbon over the badge, §3) | **fail on one node**: unread badge "2", 4.39:1 — recorded, characterised by the test, Phase 1 |

## 2. Fixed in Phase 0 (few lines, obviously right)

| Finding (measured) | Fix | File |
|---|---|---|
| `HomeSwitcherButton` node ("Changer de maison / Maison Cocody") was 244×44 dp. | `minHeight` 44 → 48; the node is now 244×48 dp (y 4→52 in the 56 dp toolbar). | `mobile/lib/features/home/widgets/home_app_bar.dart` |
| Room pills ("Tous", "Salon", …) were 44 dp high. The guideline did **not** report them: a node touching the boundary of an implicitly scrolling ancestor is skipped as "possibly scrolled off", and each pill filled the 44 dp content band of its horizontal scroller. | `RoomTabBar.height` 52 → 56 and pill `minHeight` 44 → 48; the pills are now measured (y 4→52) and pass. | `mobile/lib/features/home/widgets/room_tabs.dart` |
| `SecurityModeChip` was 40 dp high but invisible to the guideline: without `container: true` its button semantics merged upward into the whole weather card, which TalkBack read as one 328×98 dp button labelled "29.5°C / Partiellement nuageux · Humidité 74% / Mode de sécurité: Désarmé / Désarmé". | `Semantics(container: true)` so the chip is its own node, and vertical padding 4 → 8 so the ink well is 48 dp (node now 100×51 dp); the card height is driven by the 66 dp summary, so nothing moved. | `mobile/lib/features/home/widgets/weather_header.dart` |
| Each visible device tile exposed a bare `GestureDetector` node (158×140 dp, action `longPress`, no label) above the ink-well node that carried `tap` and the text ("Lampe salon / ON · 80%"). | Long-press moved onto the tile's `InkWell` (`DeviceTile.onLongPress`); one node now carries `tap`, `longPress` and the label. `GestureDetector` and its key are gone; the key moved to the tile. | `mobile/lib/core/widgets/device_tile.dart`, `mobile/lib/features/home/widgets/device_grid.dart` |

All 38 Home and core widget tests still pass with these changes.

## 3. Recorded baseline for Phase 1 (not fixed here)

### 3.1 Text contrast — unread badge

`MessageBell` → `Badge(label: Text('2'))`, 11 sp (`labelSmall`), node #20 (308,4)-(356,52),
tooltip "Centre de messages".

- Guideline result: `Expected contrast ratio of at least 4.5 but found 4.39`, computed colours
  light `#F3F4F6` (app-bar surface) and dark `#DC2626` (`colorScheme.error` =
  `SafeRColors.danger`).
- Why: the guideline samples the text's paint bounds inflated by 4 px. For an 11 sp glyph that
  rectangle (about 15×19 px) extends past the 16 dp badge circle, so the dominant light
  colour is the surrounding surface, not the white glyph. The pairs actually on screen are:
  white on `#DC2626` (the text) **4.83:1**, and `#DC2626` on `#F3F4F6` (badge on surface,
  a non-text contrast) **4.39:1**, above the 3:1 WCAG 1.4.11 floor.
- Why not fixed: both honest fixes are token-level (a darker `danger`/`error` such as the Calm
  Guardian alarm red lifts white-on-red to ≥ 6:1 and badge-on-surface to ≥ 5:1) or a larger
  badge than the Material 3 size — Phase 1 decisions, not Phase 0 edits.
- Trip-wire: the CI test asserts that the contrast guideline fails on exactly this node and
  nothing else. Any new contrast regression on Home fails CI; once the token change lands the
  test must be replaced by `meetsGuideline(textContrastGuideline)` (it says so when it fails).
- History: the first run passed because `pumpApp` still drew the DEBUG ribbon over the
  top-right corner and its red/white pixels dominated the sampled rectangle. The ribbon is now
  off in every test; the 4.39 result is stable (three consecutive runs, alone and in the full
  suite).

### 3.2 Semantics the guidelines do not judge

- `SecurityModeChip` label is "Mode de sécurité: Désarmé / Désarmé" — the explicit label and
  the chip text both merge in. Phase 1: `ExcludeSemantics` on the text or drop the explicit
  label.
- `MessageBell` is announced as "2, Centre de messages": the count is a bare number before the
  tooltip. Phase 1: a real label ("2 messages non lus") on the bell.
- `DeviceTile` switch label is `toggle Lampe salon` — English inside the French UI (rubric
  criterion 9); state words are ALL-CAPS ("ON · 80%", "OFF", "FERMÉ", "HORS LIGNE").
- The guideline only sees painted nodes: tiles below the fold are `isHidden` and skipped, and
  the "Non assignés" pill, cut by the right edge, is skipped by the boundary rule. Dark mode,
  text scale 2.0 and TalkBack order are not evaluated by any guideline today.

### 3.3 Text scale 2.0 — overflows and clipping (from the goldens)

Every 2.0 golden (`home/{light,dark}_{fr,en}_2.0.png`) tolerates **6 `RenderFlex` overflows**,
reported identically in all four variants:

| Overflow | Widgets | Cause |
|---|---|---|
| `A RenderFlex overflowed by 20 pixels on the bottom` ×3 | Tiles with a toggle: Lampe salon, Prise TV, Interrupteur cuisine | `DeviceGridSliver.tileHeight = 140` (`mainAxisExtent`) while the column needs 160 dp at 2.0: 14 + 48 (switch row) + 10 + 40 (title) + 2 + 32 (state) + 14. |
| `A RenderFlex overflowed by 12 pixels on the bottom` ×3 | Tiles without a toggle: Volet chambre, Climatisation, Porte d'entrée | Same, 152 dp needed (40 dp icon row). |

The tiles of rows four to six are not painted at 360×780 and would overflow the same way.
Other 2.0 findings, all blocking under rubric criterion 8:

- Weather card: "29.5°C" (24 sp → 48 px) breaks into three lines ("29 / .5° / C") beside a
  chip that has doubled in width; "Partiellement nuageux · Humidité 74%" is cut to
  "Partiellem…" (maxLines 2); the card grows to about 300 dp and pushes the grid down.
- App bar: "Maison Cocody" becomes "Maison Coco…".
- Tiles: names ellipsised ("Lampe s…", "Interrup…", "Volet ch…"); the state line disappears
  under the overflow stripes.
- Room pills: "Chambre" is cut at the right edge of the scroller — acceptable (scrollable),
  but the bar should scroll the selected pill into view.

At 1.0 the only clipping is pre-existing ellipsis: the weather details ("…Humidit…", a
117 dp column next to the chip) and long device names ("Détecteur fumée c…").

## 4. Phase 1 exit criteria for Home

- `meetsGuideline(textContrastGuideline)` asserted (badge fixed at token level), plus the
  token contrast test over light, dark and outdoor.
- Guidelines evaluated in dark and at 2.0 as well as fr/light/1.0.
- No `RenderFlex` overflow in any 2.0 golden (`reportOverflows` prints nothing); device tiles
  size to content or the grid re-flows to one column above 1.3.
- No ALL-CAPS state word, no English semantics label in the French UI, a labelled bell.
