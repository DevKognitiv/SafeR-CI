# TalkBack walkthrough checklists

Manual screen-reader pass for the six key screens, ticked per screen before sign-off
(`docs/qa/screen-rubric.md` §5). Automated guideline tests (`meetsGuideline` with
`androidTapTargetGuideline`, `textContrastGuideline`, `labeledTapTargetGuideline`) run in CI on
Home in Phase 0 (`a11y-baseline.md`); every interactive screen is a Phase 1 exit criterion.
This page covers what those tests cannot: announcement wording, focus order, live regions and
the SOS semantic action.

Language: TalkBack is set to French for the fr pass and English for the en pass; both are
required for Login, Home, Security and SOS, French only for the pairing wizard and device panel.

## 0. Setup

```bash
# Enable TalkBack from the host (Android 11+; the phone may ask to confirm)
adb shell settings put secure enabled_accessibility_services \
  com.google.android.marvin.talkback/com.google.android.marvin.talkback.TalkBackService
adb shell settings put secure accessibility_enabled 1
# Disable
adb shell settings put secure enabled_accessibility_services ""
```

Gestures used below: swipe right/left = next/previous element; double tap = activate; swipe
up-then-down = read from top; two-finger swipe = scroll; local context menu (swipe up then
right) lists custom actions.

General rules checked on every screen:

- [ ] Every element that looks tappable is announced with its role ("bouton", "commutateur",
      "onglet") and a French label; no "image" or "bouton" without a name.
- [ ] Composite controls (icon + label + value) are merged into one announcement
      (`MergeSemantics`): "Lampe salon, allumée, 80 %, commutateur, activé".
- [ ] Section titles are announced as headings (`header: true`), so heading navigation jumps
      between "Centrales", "Zones", "Capteurs & serrures".
- [ ] Decorative icons and the brand mark are excluded (`ExcludeSemantics`).
- [ ] Status banners (alarm, offline, session, version, clock) are live regions
      (`liveRegion: true`): the change is announced without moving focus.
- [ ] Snackbars are announced; an error snackbar reads the human message, never
      "ApiException".
- [ ] Focus does not jump to the app bar after a list refresh; it stays on the refreshed row
      or on the first new item.
- [ ] Nothing is announced in English on the French pass (hub-generated strings included).
- [ ] At text scale 2.0 the same elements are reachable and the announcements are unchanged.

## 1. Login (`/login`)

Focus order: brand mark (excluded) → title "Connexion" (heading) → hub chip "Hub : <url>" with
action "Changer l'URL du hub" → e-mail field → mot de passe field with "Afficher le mot de
passe" toggle → "Se connecter" button → "Créer un compte" link (hidden when
`flags.open_registration` is false).

- [ ] Fields announce label, current value and hint; validation errors are announced on
      submit and attached to the field (`errorText`), not only shown in a snackbar.
- [ ] "Se connecter" announces "en cours" while busy and is disabled; the 429/423 countdown
      ("Réessayez dans 42 s") is announced once and then updates silently.
- [ ] The hub-URL sheet announces "Hub joignable" / "Hub injoignable" after "Tester la
      connexion" through a live region; the insecure-URL refusal is announced as an error.
- [ ] Session-expired arrival (Phase 1 screen) announces "Session expirée" first, then the
      emergency numbers row is reachable before the form.

## 2. Home (`/`)

Focus order: home switcher button "Maison Cocody, changer de maison" → add button "Ajouter un
appareil" (admins) → offline/alarm/session/version/clock banners (live regions, in that order)
→ weather header (one merged announcement "29 °C, partiellement nuageux, humidité 74 %")
→ room tabs ("Tous, onglet, sélectionné, 1 sur 4") → device grid → bottom navigation
("Accueil, onglet, sélectionné, 1 sur 4").

- [ ] Each tile is one element: "<name>, <state word>, <value>, <room>" plus the quick toggle
      as a custom action "Allumer" / "Éteindre" in the local context menu and as a double tap
      on the toggle part; the tile body opens the panel.
- [ ] Long-press actions (rename, move, remove) are exposed as custom actions, not only as a
      long press.
- [ ] The alarm banner announces "Alarme déclenchée, <device>, ouvrir la sécurité" and is
      reachable before the grid.
- [ ] Cached/offline state: the age chip is part of the tile announcement ("mis à jour il y a
      4 min"); the offline banner is announced once when it appears.
- [ ] Empty state: "Aucun appareil" heading then the action button; the member variant
      ("Demandez à un administrateur…") has no dead button.
- [ ] SOS pill (Phase 1, on every tab): announced as "SOS, bouton, maintenir pour envoyer une
      alerte"; see §4 for the semantic action.

## 3. Security (`/security`)

Focus order: title "Sécurité" (heading) → notifications button → hero card (one announcement:
"Maison Cocody, désarmée depuis 12 min, prête") → alarm banner when active (live region) → arm
mode selector (radio group: "Désarmé, 1 sur 4, sélectionné") → "Centrales" heading → panel rows
→ "Zones" heading → zone rows → "Capteurs & serrures" heading → sensor rows → "Historique des
alarmes" heading → history rows → bottom navigation.

- [ ] The arm-mode control is a radio group with `selected` state; the target is ≥ 56 dp and
      double tap arms after the openings dialog, which traps focus and announces its title.
- [ ] The alarm banner announces "Alarme, <zone or device>, acquitter" and the "Acquitter"
      action is the first element after it.
- [ ] Zone and sensor rows: "<name>, ouvert|fermé, batterie 78 %, signal 80 %" — state words
      in sentence case, no ALL-CAPS announcements ("OUVERT" is read letter by letter on some
      engines).
- [ ] Bypass toggle on a zone: announced with its consequence ("Zone exclue de l'armement").
- [ ] Offline-cached: controls announce "indisponible hors ligne" with the reason, not just
      "désactivé".
- [ ] Clock-unsynced: the "depuis 12 min" part disappears from the hero announcement and the
      banner is announced.

## 4. SOS (`/security/sos`)

Focus order: close button → title "SOS" (heading) → status line (live region) → SOS control →
position line (live region: "Votre position a été jointe à l'alerte." / "Position non
disponible : indiquez votre adresse aux secours.") → address field when required → note field
→ "Numéros d'urgence" heading → number tiles ("Appeler Police au 170, bouton") → "Alertes
récentes" heading → alert rows.

- [ ] The SOS control announces "SOS, bouton, maintenir 2 secondes pour envoyer une alerte"
      and exposes a **semantic action "Envoyer"** (`onLongPress` semantics or a custom action
      named "Envoyer") so a TalkBack user sends without performing the hold; the 5 s cancel
      window still applies and is announced ("Envoi dans 5 secondes, annuler") with the
      "Annuler" and "Envoyer maintenant" buttons reachable immediately after the control.
- [ ] Phase announcements through the live region: "Localisation…", "Envoi de l'alerte…",
      "Alerte enregistrée sur le hub", "Alerte transmise aux secours", "Échec de l'envoi,
      réessayez"; no emoji read aloud ("coche blanche" must never be heard).
- [ ] `position_required`: focus moves to the address field, its error text is announced, and
      the confirmation checkbox is labelled "Les secours iront à cette adresse".
- [ ] Emergency tiles are ≥ 48 dp, labelled "Appeler <service> au <number>", and work on the
      session-expired and forced-update screens.
- [ ] Composer fallback ("Prévenir mes proches par SMS"): announced as a button with its
      consequence; when no SMS app exists the error is announced and the message text is
      reachable for copy.
- [ ] Alert rows: "SOS du 11 octobre à 12:04, enregistrée, transmise, ouverte" with the
      "Marquer comme résolue" custom action.
- [ ] Alarm takeover (Phase 2): opens as a modal that traps focus, announces "Alarme, Maison
      Cocody, <device>" first, with "Désarmer", "Voir", "Appeler" in that order.

## 5. Pairing wizard (`/add-device`, `/add-device/scan`, `/add-device/:brand`)

Focus order (catalogue): title → search field → "Catégories" heading → category tiles →
"Marques" heading → brand cards ("Tuya / Smart Life, Appareils Tuya via le cloud ou en local,
bouton") → scan button.

- [ ] Admin-only view announces "Réservé aux administrateurs" with the explanation, no dead
      controls.
- [ ] Scan screen: the overlay instruction "Placez le code QR dans le cadre" is announced on
      entry; the torch button announces its state; "Saisir manuellement" is reachable without
      finding the camera area; camera-permission denial announces the explanation and the
      manual button gets focus.
- [ ] Stepper: the current step is announced as "Étape 2 sur 4, Formulaire"; moving to the
      next step moves focus to the step title.
- [ ] Dynamic form fields (from `FormFieldSpec`) announce label, type (password fields say
      "mot de passe"), required state and help text; select fields announce the chosen option.
- [ ] Discovery: "Recherche des appareils…" is a live region; the result list announces
      count ("2 appareils trouvés") and each row with a checkbox state.
- [ ] Pairing error card: announced as an error, with "Réessayer" and "Modifier" reachable
      immediately after.
- [ ] Success: "1 appareil ajouté" announced, room picker labelled, "Terminer" is the last
      element.

## 6. Device panel (`/devices/:id`, light panel as the reference)

Focus order: back → device name (heading) → settings button "Paramètres de l'appareil" →
offline banner (live region) → big power button ("Lampe salon, allumée, bouton, éteindre") →
brightness slider ("Luminosité, 80 %, curseur") → colour temperature slider → colour picker
(named swatches, "Blanc chaud") → mode selector → info rows → history.

- [ ] Sliders announce label, value with unit and adjust by 5 % with volume keys/swipe
      up-down; the value announcement uses a narrow no-break space ("80 %" read as "80 pour
      cent").
- [ ] The big power button announces the device state and the action it will take, not just
      "bouton".
- [ ] Command receipt: "En attente" then "Confirmé" or "Échec, réessayer" through a live
      region; a failed command's retry is reachable from the control.
- [ ] Device offline banner announces "Appareil hors ligne, dernière activité il y a 3 min,
      actualiser"; controls that cannot work are announced as unavailable with the reason.
- [ ] Camera panel: the player area is labelled "Vidéo en direct" or "Lecture vidéo
      indisponible, instantané disponible"; PTZ pad buttons are labelled by direction;
      HD/SD segmented control announces selection.
- [ ] Lock panel: the unlock confirmation dialog traps focus and announces its consequence;
      the state is "verrouillée" / "déverrouillée" in sentence case.
- [ ] Alarm panel: "Alarme déclenchée, zone salon, désarmez pour arrêter la sirène" as a live
      region; zone rows as in §3.

## 7. VoiceOver (only if decision 0001 §1 is "go")

Same six screens with the iOS reader. Additional checks: the rotor exposes headings and
custom actions; the SOS "Envoyer" action appears in the actions rotor; the alarm takeover uses
`accessibilityViewIsModal`; dynamic type at the largest accessibility size matches the 2.0
text-scale goldens; Cupertino alerts announce their title before their actions. Until iOS is
go this section is informational and no row in `docs/qa/screen-signoff.md` requires it.

## 8. Recording a pass

Tick the boxes in a copy of the relevant section inside the PR description (or
`docs/qa/reviews/<date>-<route>-talkback.md`), name the device, Android version, TalkBack
version and language, attach a short screen recording with captions on
(`docs/qa/device-capture.md` §2) where an announcement was in doubt, and reference it from the
sign-off row.
