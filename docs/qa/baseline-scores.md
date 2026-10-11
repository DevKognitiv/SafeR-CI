# Phase 0 baseline scores

The starting point every Phase 1 screen is measured against. Two reviewer agents (design lens,
accessibility lens) scored the ten reference screens from the Playwright captures of the Demo
build, applying `screen-rubric.md` literally: ten criteria, weighted, screen score = lowest
variant viewed, colour-vision step, blocking findings. **No screen passes the 8.0 gate and every
screen carries at least one blocking finding.** That is the expected baseline of a stock
Material 3 app; it is recorded here so that the gate has a before.

- Captures: `mobile/tool/screenshots/out/` from the harness at commit 88fb6be (the app code of
  the screens is that of 5e099c3), 162/162 variants, downscaled copies of 14 of them in
  `baseline/`. Web captures are a critique instrument, not sign-off evidence (`screen-rubric.md` §5).
- Variants read: design lens 41 (all three mandatory 360×780 variants per screen, 5 en, 5 at
  412×915, both 600 dp tablets), accessibility lens 40. Contrast was sampled from the PNGs with
  Pillow and cross-checked against `mobile/lib/core/theme.dart`; touch targets measured in dp
  from the 2× captures; colour-vision simulations produced with
  `mobile/tool/screenshots/simulate_cvd.py` (Machado 2009 deuteranopia/protanopia).
- This file holds the per-screen scores, the blocking findings and the Phase 1 fix list; the
  per-variant sheets are the judges' structured outputs kept with the session.

## 1. Scores per screen (lowest variant)

| Route | Design | Accessibility | Variants read | Blocking findings | Gate (≥ 8.0, none blocking) |
|---|---|---|---|---|---|
| `/ (Home)` | 3.7 (light/fr/2.0/360x780) | 4.9 (light-fr-2.0-360x780) | 6 + 6 | 11 | fail |
| `/security` | 4.0 (light/fr/2.0/360x780) | 4.8 (light-fr-2.0-360x780) | 6 + 6 | 11 | fail |
| `/security/sos` | 5.1 (light/fr/2.0/360x780) | 6.1 (light-fr-2.0-360x780) | 4 + 4 | 1 | fail |
| `/scenes` | 3.6 (light/fr/2.0/360x780) | 5.0 (light-fr-2.0-360x780) | 3 + 3 | 5 | fail |
| `/me` | 3.5 (light/fr/2.0/360x780) | 5.0 (light-fr-2.0-360x780) | 5 + 5 | 10 | fail |
| `/add-device` | 3.8 (light/fr/2.0/360x780) | 5.0 (light-fr-2.0-360x780) | 3 + 3 | 5 | fail |
| `/add-device/tuya` | 5.2 (light/fr/2.0/360x780) | 5.8 (light-fr-2.0-360x780) | 3 + 3 | 2 | fail |
| `/devices/dev-light` | 4.5 (light/fr/2.0/360x780) | 6.1 (light-fr-1.0-360x780) | 3 + 4 | 4 | fail |
| `/devices/dev-cam` | 4.6 (light/fr/2.0/360x780) | 5.1 (light-fr-2.0-360x780) | 4 + 3 | 4 | fail |
| `/login` | 4.7 (dark/fr/1.0/360x780) | 6.0 (dark-fr-1.0-360x780) | 4 + 3 | 4 | fail |
| **Mean** | **4.3** | **5.4** | | | |

At text scale 1.0 only, the design-lens mean is 4.8: the 2.0 variants pull every screen down.

## 2. Blocking findings per screen

Criterion numbers refer to `screen-rubric.md` §1. Where both lenses raised the same finding it is
listed once.

### `/ (Home)` — design 3.7, accessibility 4.9

- BLOCKING: 8 Text scaling — temperature '29.5°C' wraps to three lines '29 / .5° / C'; 'Partiellement nuageux' breaks mid-word to 'Partie / llem…'; tile names ellipsised 'Lampe s…', 'Volet ch…', 'Interrupt…'; the fourth tile's state line is cut by the grid's fixed mainAxisExtent (home/light-fr-2.0-360x780.png; known overflow in docs/qa/a11y-baseline.md)
- BLOCKING: 9 French copy — same ALL-CAPS 'ON · 80%', 'OFF' plus ellipsised labels
- BLOCKING: 7 Contrast — selected room chip 'Tous' label #1A2D60 on #2563EB = 2.56:1 (dark scheme onPrimary from ColorScheme.fromSeed is navy, never overridden) — home/dark-fr-1.0-360x780.png; 'Désarmé' chip 3.69:1
- BLOCKING: 7 Contrast — 'Désarmé' chip text #16A34A on tint #DEF2E5 = 2.82:1 (needs 4.5) — home/light-fr-1.0-360x780.png weather card; token pair success-on-surfaceLight is 2.99:1, success-on-white 3.30:1, so every green chip in the app fails from the token file
- BLOCKING: 8 Text scaling — '29.5°C' wraps per character ('29 / .5° / C'); weather detail becomes 'Partie / llem…'; tile names 'Lampe s…', 'Interrupt…', 'Volet ch…' ellipsised; the state line of 'Interrupteur cuisine' ('ON') is clipped by the 140 dp mainAxisExtent (RenderFlex overflow 20/12 px); the weather card grows to ~290 dp and pushes the first device row to the fold — out/home/light-fr-2.0-360x780.png — fix: size tiles to content or reflow to one column above 1.3, let the chip drop under the temperature, clamp chrome at 1.4.
- BLOCKING: 7 Contrast — selected room pill 'Tous': label #1A2D60 on #2563EB = 2.56:1. Cause: ColorScheme.fromSeed(brightness: dark) picks a dark onPrimary while primary is forced to #2563EB in both schemes (theme.dart:53-58); every FilledButton / selected pill in dark mode inherits it. Fix: onPrimary white (or a lighter dark primary) in the dark scheme.
- BLOCKING: 7 Contrast — weather-card security chip 'Désarmé' is success #16A34A on tint #DEF2E5 = 2.82:1 (fails 3:1 bold and 4.5:1) — out/home/light-fr-1.0-360x780.png — fix: darker success token or solid chip, verified from the token file.

### `/security` — design 4.0, accessibility 4.8

- BLOCKING: 8 Text scaling — mode tiles truncate their state words to 'Dés…', 'Pré…', 'Abs…' (the rubric's literal failure example); 'Central…' / 'Centrale …' ellipsised in the panel row; 'Modifié · Il y a 12 / min' orphan — security/light-fr-2.0-360x780.png
- BLOCKING: 8 Text scaling — 'Désa…', 'Prés…', 'Abse…' still truncated at 412 dp; 'Centrale d'al…', 'Centrale d'alar…', 'Centrale d'ala…' ellipsised — security/light-fr-2.0-412x915.png
- BLOCKING: 4 Colour discipline — 'Absent' (armed_away) tile glyph and tint are red (SafeRColors.forSecurityMode returns danger) and 'Présent' (armed_home) is amber (warning); the rubric reserves red for alarm/SOS/destructive and makes armed teal — security/light-fr-1.0-360x780.png mode selector; lib/core/theme.dart:19-28
- BLOCKING: 7 Contrast — 'Système prêt · toutes les ouvertures sont fermées' #16A34A on hero tint = 3.07:1 at ~16 sp bold (needs 4.5); 'Désarmé' hero title 2.92:1 (large text needs 3.0); 'Désarmé'/'Fermée'/'Fermé'/'Calme' chips 2.82:1
- BLOCKING: 8 Text scaling — the 412 dp frame does not rescue the tiles: 'Désa…', 'Prés…', 'Abse…' still truncated; 'Centrale d'al…', 'Centrale d'alar…', 'Centrale d'ala…' ellipsised — out/security/light-fr-2.0-412x915.png.
- BLOCKING: 4 Colour discipline — red (danger #DC2626) paints the 'Absent' (armed away) tile tint and glyph; warning orange paints 'Présent'; purple paints 'Nuit' (SafeRColors.forSecurityMode, theme.dart:19-27). Red is reserved for alarm/SOS/destructive; armed should be teal — out/security/light-fr-1.0-360x780.png.
- BLOCKING: 7 Contrast — status chips 'Fermé', 'Calme' (sensors) and 'Désarmé' (panel) are #16A34A on #DEF2E5 = 2.82:1; 'Système prêt · toutes les ouvertures sont fermées' 3.04:1 (14 sp bold, marginal); non-text: the 'Présent' house glyph #EA580C on its #E9CFB6 circle = 2.38:1 (< 3:1).

### `/security/sos` — design 5.1, accessibility 6.1

- BLOCKING: 8 Text scaling — 'Maison Cocody · Cocody, …' address ellipsised; the status line starts flush against the masked button band (y=898 device px) with no gap, suggesting the button and status collide at 2.0; the four number tiles fall below the fold with only their glyphs visible — sos/light-fr-2.0-360x780.png

### `/scenes` — design 3.6, accessibility 5.0

- BLOCKING: 8 Text scaling — 'Bonne n…', '2 actions …', '1 action · …' ellipsised in both cards; 'Automatiser' tab label clipped at the right edge ('Automatise') — scenes/light-fr-2.0-360x780.png
- BLOCKING: 4 Colour discipline — the 'Je pars' scene is a solid red (#DC2626) card: red for a non-alarm, non-destructive element; red badge '2' on 'Moi' — scenes/light-fr-1.0-360x780.png
- BLOCKING: 8 Text scaling — the 'Automatiser' tab label is clipped by the right viewport edge ('Automatise'); cards show 'Bonne n…', '2 actions …', '1 action · …' — out/scenes/light-fr-2.0-360x780.png — fix: scrollable tabs or shorter labels; cards sized to content.
- BLOCKING: 8 Text scaling — at 2.0 the 'Automatiser' tab label is clipped at the viewport edge (see 2.0 variant).

### `/me` — design 3.5, accessibility 5.0

- BLOCKING: 8 Text scaling — quick-action tile labels are clipped by the tile's fixed height: 'Gestio / n de…' (second line cut), 'Centre / de m…', 'Intégr / ations' cut, 'Param / ètres' cut; 'Alice Ko…' ellipsised; home card 'M…' / 'Coc…' ellipsised; 'Membr…' and the 'Gérer' button are cut by the fold — me/light-fr-2.0-360x780.png (worst 2.0 variant in the set)
- BLOCKING: 8 Text scaling — same clipping in English: 'Home / mon…', 'Messa / ges', 'Integr / ations', 'Settin / gs'; 'Maiso…', 'Membe…', 'Manag…' cut — me/light-en-2.0-360x780.png (confirms the fault is layout, not French word length)
- BLOCKING: 8 Text scaling — at 412 dp the second lines are still clipped: 'Gestion / des m…', 'Centre / de me…', 'Intégrati / ons' and 'Paramèt / res' cut mid-word by the tile edge; 'Alice Koua…' ellipsised — me/light-fr-2.0-412x915.png
- BLOCKING: 7 Contrast — 'Propriétaire' chip #EA580C on #FCE7DD = 2.99:1; 'Désarmé' chip 2.82:1 — me/light-fr-1.0-360x780.png home card
- BLOCKING: 8 Text scaling — every quick-action tile clips its second line ('Gestio/n de…', 'Centre/de m…', 'Intégr/ations', 'Param/ètres'); 'Alice Ko…'; the home card shows 'M…' for Maison Cocody and 'Coc…'; the 'Membr…' button is cut by the card edge; the badge '2' overlaps 'Centre' — out/me/light-fr-2.0-360x780.png — fix: tiles sized to content, labels maxLines 2 with reflow, chip row wraps.
- BLOCKING: 8 Text scaling — at 412 dp still clipped: 'Gestion des m…', 'Centre de me…', 'Intégrati/ons', 'Paramèt/res', 'Maiso…', 'Cocody, …', 'Alice Koua…' — out/me/dark-fr-2.0-412x915.png.
- BLOCKING: 6 Touch targets — 'Membres' and 'Gérer' buttons measure 142x44 dp (< 48 dp) — out/me/light-fr-1.0-360x780.png — fix: minimumSize height 48.

### `/add-device` — design 3.8, accessibility 5.0

- BLOCKING: 8 Text scaling — the 'Éclairage' category card breaks its label mid-word ('Éclaira / ge') and its subtitle 'Tuya / …' renders outside the card's bottom edge, colliding with the 'Marques' header; search placeholder 'Rechercher une…' and 'Appareils de d…' ellipsised — add-device/light-fr-2.0-360x780.png
- BLOCKING: 9 French copy / installer gate — protocol identifiers 'tuya_cloud', 'tuya_local', 'demo' rendered as chips on the consumer catalogue without an 'Options avancées' gate — add-device/light-fr-1.0-360x780.png brand rows
- BLOCKING: 8 Text scaling — 'Éclaira / ge' breaks mid-word without a hyphen; the category card's subtitle 'Tuya / …' renders outside the card, over the 'Marques' heading (overflow); 'Appareils de d…', 'Rechercher une…' ellipsised; 'Caméras' chip cut at the edge (scrollable) — out/add-device/light-fr-2.0-360x780.png.
- BLOCKING: 9 / §3 — protocol ids 'tuya_cloud', 'tuya_local' and 'demo' are shown as chips on the consumer brand list with no 'Options avancées' gate — out/add-device/light-fr-1.0-360x780.png — fix: human labels ('Cloud', 'Local') or hide.
- BLOCKING: 8 Text scaling — at 2.0 'Éclaira/ge' breaks mid-word and the category card overflows (see 2.0 variant).

### `/add-device/tuya` — design 5.2, accessibility 5.8

- BLOCKING: 9 French copy / installer gate — 'Access ID / Secret du projet IoT' shown as the subtitle of the first method on a consumer screen (the rubric's literal example) — pair-tuya/light-fr-1.0-360x780.png
- BLOCKING: 9 / §3 — 'Access ID / Secret du projet IoT' is printed on the consumer method chooser without an 'Options avancées' gate; 'Projet Tuya Cloud', 'Clé locale', 'Contrôle local sans cloud' are installer vocabulary — out/pair-tuya/light-fr-1.0-360x780.png.

### `/devices/dev-light` — design 4.5, accessibility 6.1

- BLOCKING: 7 Contrast — state word 'ALLUMÉE' #F59E0B on white = 2.15:1 — device-light/light-fr-1.0-360x780.png
- BLOCKING: 9 French copy — 'ALLUMÉE' ALL-CAPS with letter-spacing (lib/features/device/panels/light_panel.dart:48; 'ÉTEINTE' for off); '80%' without narrow no-break space
- BLOCKING: 7 Contrast — 'ALLUMÉE' amber #F59E0B on white = 2.13:1; the amber is a literal Color(0xFFF59E0B) in light_panel.dart:34, not a token.

### `/devices/dev-cam` — design 4.6, accessibility 5.1

- BLOCKING: 6 Touch targets — HD/SD segmented control measures 111×31.5 dp (each segment ~55×31 dp), under the 48 dp minimum — device-camera/light-fr-1.0-360x780.png
- BLOCKING: 9 French copy — 'EN LIGNE', 'CALME', 'REC' ALL-CAPS chips (lib/features/device/widgets/status_chips.dart:76); 'RTSP · Démo' and 'Orientation (PTZ)' protocol jargon on a consumer surface
- BLOCKING: 6 Touch targets — the HD/SD segmented control measures 112x32 dp (< 48 dp) — out/device-camera/light-fr-1.0-360x780.png.

### `/login` — design 4.7, accessibility 6.0

- BLOCKING: 7 Contrast — 'Se connecter' label #1A2D60 on #2563EB = 2.56:1 (dark ColorScheme.fromSeed onPrimary, never overridden in lib/core/theme.dart) — login/dark-fr-1.0-360x780.png
- BLOCKING: 9 French copy / installer gate — 'Hub : http://localhost:8000' with a settings gear is printed on the consumer login (hub URL is an Installateur field; cleartext http is also the rubric's Play cross-check item) — login/light-fr-1.0-360x780.png
- BLOCKING: 5 State honesty / §3 — 'Hub : http://localhost:8000' sits on the consumer login surface: an installer-level field (hub URL) outside an 'Options avancées' gate, and a cleartext http scheme on screen (Play cross-check) — out/login/light-fr-1.0-360x780.png — fix: move it into the gear sheet, never print the scheme.

## 3. Colour-vision step (`screen-rubric.md` §2)

Design lens:

- Security light, deuteranopia and protanopia: the green 'Désarmé' tile, amber 'Présent' tile and red 'Absent' tile all collapse to the same olive/khaki family (hero shield, 'Désarmé' title, 'Système prêt' line and every chip turn mustard). The four modes stay distinguishable only by glyph + word: open padlock 'Désarmé', house 'Présent', walking figure 'Absent', moon 'Nuit' — each tile has both, so item 1 of the §2 checklist PASSES for the mode selector. Under protanopia the red 'Absent' glyph loses almost all saturation and reads as a grey figure: the colour contributes nothing, which is the rubric's intent but shows how little the current red was carrying.
- Security dark, deuteranopia: same result; the hero gradient becomes a grey wash and the 'Nuit' tile is the only one with a distinct hue (blue), so a deutan user sees three khaki tiles and one blue tile.
- Home light, deuteranopia/protanopia: the 'Désarmé' chip keeps its shield glyph + word (pass). The device-state lines 'ON · 80%', 'OFF', 'FERMÉ', 'CALME' are grey words with no colour and no glyph: they pass 'not colour alone' trivially but fail the rubric's 'glyph AND word' pairing (word only). Online/offline is not visible on Home in the default state (offlineDevices state not in routes.json); on device-camera the 'EN LIGNE' chip has cloud-check glyph + word (pass by inspection, not simulated).
- Red unread badges ('2' on the bell and on 'Moi', '1' on the Security bell) turn mustard in both simulations and lose their 'attention' meaning; they keep a numeral, so no information is lost, but it confirms red is doing no work there and should not be red.
- SOS salience (checklist item 3): FAILS for Home and Security — there is no SOS control on either route today (the Phase 2 SOS pill is a backlog item), so nothing emergency-coloured exists to remain salient; in the simulations the most salient element on Home is the blue 'Tous' chip and the toggles, on Security the khaki hero. On /security/sos the button is masked by the harness (masks.json sos-button) so its salience could not be assessed from captures.
- Armed and alarm states: NOT ASSESSABLE from this run — routes.json captures Home and Security in the default disarmed state only (no armedAway / armedHome / alarm variants), so 'armed vs ready vs alarm distinguishable' could not be checked from PNGs. From the tokens (lib/core/theme.dart forSecurityMode: armed_away = danger #DC2626, armed_home = warning #EA580C, armed_night = #7C3AED, default = success #16A34A) red and green sit in the same lightness band and both map to olive under protanopia; whether the hero shows a different glyph per mode (the disarmed hero shows an outlined shield) was not visible. Recommend adding ?state=armedAway and ?state=alarm variants of home and security to routes.json before the Phase 1 critique loop.
- Charts and dials (checklist item 4): none on Home or Security; on device-light the colour-temperature slider is a hue-only gradient but carries the '4000 K' value label (pass).
- Verdict for §2: no outright hue-only state found on the captured screens; two checklist items fail or cannot be confirmed (SOS salience: no control present; armed/alarm: not captured). Treat the missing SOS control and the missing armed/alarm captures as the blocking gaps, not the mode tiles.

Accessibility lens:

- UNVERIFIED (checklist item 1): the capture matrix only holds the ready/disarmed state (routes.json lists no armedAway/armedHome/alarm/offlineDevices states), so armed vs ready vs alarm could not be compared in simulation. The Phase 1 matrix must add those states before this item can be marked pass.
- PASS by glyph+word, mode tiles: Désarmé (lock-open), Présent (house), Absent (walking figure), Nuit (moon) each keep a distinct glyph and word, so the four modes stay identifiable without colour. The colour layer itself carries nothing: under deuteranopia and protanopia the Présent and Absent tile tints converge (#E8E4D4 vs #E5E2DA, 1.02:1) and the red Absent and green Désarmé accents both turn olive.
- FAIL (glyph contrast): the glyph that is supposed to carry the state is too faint. Light deutan: Absent glyph 2.56:1 on its circle, Présent glyph 2.09:1; light protan: Absent 4.25:1, Présent ~2.1:1; dark protan: Absent glyph #635923 on #333437 = 1.77:1, i.e. an almost empty dark tile with the word 'Absent'. The originals already fail the 3:1 non-text floor (Présent 2.38:1 light, Absent 2.47:1 dark).
- Status chips without a glyph: 'Fermé', 'Calme' (sensors) and 'Désarmé' (panel) are word-only; in simulation they all become the same khaki, so the colour is meaningless and only the word works. Passes the 'icon or word' item, fails criterion 4's 'glyph and word'. The zone chip '✓ Fermée' and the lock chip 'Verrouillée' show the right pattern.
- Online/offline: camera 'EN LIGNE' keeps its cloud glyph + word under deutan (PASS); the offline rendering ('HORS LIGNE' word on Home tiles per device_tile.dart:61) exists in code but was not captured (offlineDevices state absent) → UNVERIFIED.
- Home weather chip 'Désarmé' keeps shield glyph + word (PASS); unread badge red → olive, the digit carries it (PASS); camera 'REC' dot and 'RTSP · Démo' live dot turn olive, the word carries them (PASS by word only).
- FAIL (checklist item 3, SOS salience): the SOS control is masked in every SOS capture and is absent from the Home and Security frames (SosCard is the last list item, below the fold), so in the simulated Home/Security images there is no SOS element at all — it cannot be the most salient element.
- Charts/dials: none on these screens. The colour-temperature slider on device-light is an unlabeled warm→cool gradient whose meaning is hue-only; add 'Chaud'/'Froid' end labels in Phase 1.
- Net: colour-vision step raises two fails (mode-glyph contrast; SOS absent/masked) and two unverified items (armed/alarm states, offline state); plus the criterion-4 blocking red 'Absent'.

## 4. Fix list for Phase 1 (both lenses, ordered by how many screens each unblocks)

Design lens:

- Typography foundation: lib/core/theme.dart never references the bundled Manrope/Inter (pubspec.yaml declares them) so every screen renders Roboto; build the token TextTheme (Manrope display, Inter body, tabular figures on values/times) and delete the 28 fontSize literals under lib/features (criterion 2, every screen).
- Status-colour tokens with AA text-on-tint pairs: today success #16A34A on its 0.14 tint is 2.82:1, on surfaceLight 2.99:1, warning on its tint 2.99:1, primary on cardDark 2.83:1 and the dark scheme's computed onPrimary gives 2.56:1 on the CTA/selected chip ('Se connecter', 'Tous'). Define explicit onPrimary, a darker text shade per status tint (light) and a lighter one (dark), and verify from the token file (criterion 7 blocking on 9 of 10 screens).
- forSecurityMode re-mapping: armed_away red and armed_home amber violate the colour rule on the Security hero and tiles; make the armed family teal, ready green, alarm the only red, and move unread badges off the error colour (criterion 4 blocking on Security, Home, Me, Scenes, Camera 'REC').
- Sentence-case, French-formatted state words: light_panel.dart:48 ('ALLUMÉE'/'ÉTEINTE'), sensor_panel.dart:53 ('OUVERT'/'FERMÉ'), status_chips.dart:76 ('EN LIGNE'/'HORS LIGNE'), Home tile states ('ON · 80%', 'OFF', 'CALME', 'OK'), camera 'CALME'/'REC'; plus '29,5 °C', '80 %' with narrow no-break spaces and 'il y a' lower-case after '·' (criterion 9 blocking on 6 screens).
- Text scale 2.0 layouts: Home grid fixed mainAxisExtent (temperature wraps per character, names ellipsised), Security mode tiles ('Dés…/Pré…/Abs…'), Me quick-action tiles (labels clipped by fixed height even at 412 dp), Scenes cards and tab, Add-device category card (overflows its card). Use intrinsic heights, wrap/stack at ≥1.3, clamp only dense chrome (criterion 8 blocking on 6 screens).
- Installer-field gate: hub URL 'Hub : http://localhost:8000' on the login, 'Access ID / Secret du projet IoT' on pair-tuya, 'tuya_cloud'/'tuya_local'/'demo' chips on add-device, 'RTSP · Démo' and 'PTZ' on the camera: move behind 'Options avancées' and use plain words (§3 blocking on 4 screens).
- Touch targets: HD/SD segmented control on device-camera is 111×31.5 dp (each segment ~55×31); make it 48 dp tall and verify the 34 dp-tall category chips on add-device have the padded 48 dp hit area on device (criterion 6 blocking on camera).
- Hierarchy of the two hero screens: Home must open on the home state (word + glyph + age) with an SOS pill, not on the weather temperature; Security keeps its hero but needs the SOS pill and a selector that does not give four equal hues equal weight (criterion 1; also closes the §2 'SOS most salient' fail).
- Login and Scenes composition: centre the brand hero (column is tagline-width, so the wordmark drifts left with locale and viewport), unify 16 dp gutters; give Scenes and Pair-tuya an inline empty/hint block instead of 70 % blank canvas; Me headers at 20 dp vs cards at 16 dp (criterion 3).
- Critique-loop coverage: add armedAway/armedHome/alarm/offlineDevices variants of home and security to mobile/tool/screenshots/routes.json so the next colour-vision pass can actually test armed vs ready vs alarm, and run simulate_cvd.py as part of the harness output.

Accessibility lens:

- Token-level contrast pass (criterion 7, blocking on 9/10 screens): success/warning/danger text on their tints is 2.82–2.99:1 light and 2.33–3.69:1 dark (every status chip); set the dark scheme's onPrimary to white (today #1A2D60 on #2563EB = 2.56:1 on 'Se connecter', selected pills and every FilledButton); stop using brand blue #2563EB as text on dark surfaces (2.50–3.45:1 on 'Membres', 'Créer un compte', active tab, '80%', '4000 K', 'Compte requis'); replace the amber literal 0xFFF59E0B (2.13:1 on white); lift the mode glyphs above 3:1 on their circles.
- Text scale 2.0 (criterion 8, blocking on 7/10 screens): remove fixed extents — Home tile mainAxisExtent 140, Me quick-action tiles, Security mode tiles, scene cards — and reflow to one column / 2x2 above 1.3; never ellipsise a state word ('Dés…', 'Abs…') or the SOS address; scrollable tabs on Scenes; clamp app-bar chrome and badges at 1.4x; let the temperature row wrap the chip underneath.
- Copy (criterion 9, blocking on 5/10 screens): sentence case and gender agreement for every state string in lib/core/i18n.dart:83-106, lib/core/models/device.dart:244-288 and the device panels ('Allumée · 80 %', 'Fermée', 'En ligne', 'Calme', 'Enregistrement'); narrow no-break space before %, °C, ? and :; move RTSP/PTZ/REC/'Access ID / Secret'/'tuya_cloud'/'tuya_local'/'demo' and the login 'Hub : http://…' line behind 'Options avancées'.
- Colour discipline (criterion 4, blocking on Security and Scenes): rewrite SafeRColors.forSecurityMode so armed = teal and red appears only for alarm/SOS/destructive; remove red from the scene colour palette; neutral unread badges; 'Propriétaire' role chip and Tuya progress bar off the warning orange; give every status chip a glyph as well as a word.
- SOS reachability (criterion 6 and §2 item 3): add a persistent SOS affordance with a ≥ 72 dp hit area on every tab (today the only entry is SosCard as the last child of the Security list, invisible at 360x780 and 600x960); move SosCard to the top of Security; unmask the button in the critique harness so salience can be scored.
- Touch targets (criterion 6, blocking on Me and Camera): Me 'Membres'/'Gérer' 142x44 → 48 dp; camera HD/SD segmented control 112x32 → ≥ 48 dp; weather security chip 35 dp visual → 48 dp visual.
- State honesty (criterion 5): extend routes.json so each screen is captured in its matrix states (offline, offlineDevices, failDevices/failSecurity/failScenes, noScenes/noDevices/noHomes, alarm, armedAway, sosAlerts, protectedStreams, locationDenied) — today only loggedOut is captured and every screen was scored on its happy path; add data-age chips; hide 'Il y a 12 min' when the hub clock is unsynced; replace raw hub text ('Invalid credentials', 'Not authenticated') with the French copy already decided in the state matrix; show an explicit empty/loading view under 'Alertes récentes'.
- Hierarchy and typography groundwork: apply the bundled Manrope/Inter text theme (stock Roboto renders everywhere; 28 fontSize and 19 Color(0x) literals remain under lib/features), centre the login hero, make the home's security state the first thing read on Home, and give the 600 dp layout a three-column grid or a max card width.

## 5. Limits of this baseline

- Only the default (ready / disarmed, signed in) state of each screen was captured; armed, alarm,
  offline, failure and empty states are in `state-matrix.md` and in the demo hooks but not yet
  in `mobile/tool/screenshots/routes.json`, so criterion 5 was scored on the happy path and the
  armed-versus-alarm colour-vision check is unverified.
- The SOS control is masked in the SOS captures (it pulses) and absent from Home and Security,
  so the "SOS stays the most salient element" check fails by construction until the persistent
  SOS affordance exists and the pulse honours `disableAnimations`.
- Web rendering: CanvasKit and the engine's Roboto (the bundled Manrope/Inter are not wired into
  the theme yet), no status bar, no OEM font scaling, no overflow stripes in a release build.
  Android captures per `device-capture.md` remain the sign-off evidence.

## 6. Next action

Phase 1 starts from §4: type theme, status-colour tokens with AA pairs, `forSecurityMode`
re-mapping, sentence-case French state words, text-scale-2.0 layouts, the SOS affordance, and
the capture matrix extended with the matrix states. Each Phase 1 screen PR re-runs both lenses
and records its scores in `screen-signoff.md`; this file is not updated, it is the before.
