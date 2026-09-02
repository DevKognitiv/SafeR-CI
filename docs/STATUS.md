# SafeR-CI — Component Status

Ground truth for what actually runs **on `main`**. Keep this current; `CLAUDE.md` points here and
it is the cheapest way to stop anyone (human or agent) re-deriving the state of the repo from
scratch.

**Read "Open PRs" at the bottom before starting work.** Several gaps described here are already
solved on unmerged branches. Writing them again is the most expensive mistake available in this
repo right now.

Last verified: 2026-09-02.

---

## Summary

| Component | State | Runnable | Notes |
|---|---|---|---|
| `web-dashboard/` | **Working** | Yes | Next.js 14, builds and runs; demo data only |
| `ha-config/` | **Complete** | On a HA node | 1,667 lines of YAML; never validated on hardware |
| `backend/` | **Scaffold** | No | 4 source files; imports 5 modules that do not exist |
| `mobile/` | **Scaffold** | No | 3 source files; imports 8 files that do not exist |

---

## `web-dashboard/` — working

Next.js 14 App Router + TypeScript + Tailwind + Leaflet. `npm run build` passes.

Known limits, all deliberate:

- `src/app/api/incidents/route.ts` is an **in-memory array** seeded from `src/lib/mock-data.ts`.
  It resets on every cold start. There is no database.
- `src/app/api/incidents/webhook/ha/route.ts` logs the payload and returns `ok`. It stores nothing
  and verifies no signature.
- `IncidentMap.tsx` injects Leaflet's CSS and JS from `unpkg.com` at runtime instead of using the
  installed `leaflet` / `react-leaflet` packages. This sidesteps SSR issues but means the map does
  not render offline, and the two npm packages are currently unused.
- No tests, no `next-env.d.ts` (Next generates it), no ESLint config file.

## `ha-config/` — complete but unvalidated

All YAML for a per-neighborhood Home Assistant hub: 610 lines of entities, 9 bidirectional
automations, 7 emergency scripts, a 6-view Lovelace dashboard, and REST commands to the SafeR API.

- Syntax-valid, but **never run against a real Home Assistant instance**.
- `rest_commands.yaml` targets backend endpoints that are not implemented (see below).
- Requires a real `secrets.yaml` (gitignored) built from `secrets.yaml.example`.

## `backend/` — scaffold on `main`, does not import

> **A fix already exists in PR #10** (`feature/backend-e2e`), which adds every module listed below
> and reports end-to-end verification against PostGIS. Do not re-implement this; review and merge
> that PR instead.

Four files exist: `main.py`, `core/config.py`, `models/incident.py`, `api/routes/incidents.py`.

**Missing modules that existing code imports:**

| Import | Needed by |
|---|---|
| `app.core.database` (`Base`, `init_db`, `get_db`) | `main.py`, `models/incident.py`, `api/routes/incidents.py` |
| `app.api.routes.alerts` | `main.py` |
| `app.api.routes.users` | `main.py` |
| `app.api.routes.health` | `main.py` |
| `app.schemas.incident` | `api/routes/incidents.py` |
| `app.services.incident_service` | `api/routes/incidents.py` |
| `app.services.notification_service` | `api/routes/incidents.py` |

**Other missing files referenced by config:**

- `backend/Dockerfile` — `docker-compose.yml` builds from it in two services.
- `app/workers/celery_app` — the `celery_worker` service command.
- `infrastructure/nginx/nginx.conf` — mounted by the `nginx` service.
- No `__init__.py` anywhere, so `app` is not a package under this layout.

`docker-compose up` therefore fails at build. `python -m compileall backend/app` passes — the files
are syntactically valid, just unwired.

`docker-compose.yml` also hardcodes `safer:safer_pass` as the Postgres credentials and publishes
5432 and 6379 to the host. That is fine for a laptop, not for a deployment.

## `mobile/` — scaffold on `main`, does not build

> **PR #9** (`feature/ha-mobile-integration`) adds an MQTT `HomeAssistantService`, wires the SOS
> screen to it, and carries an "Aurora" design system with i18n. It does not add the missing
> `core/` and `screens/` files listed below, so the app still would not build from that branch alone.

Three files exist: `main.dart`, `screens/sos_screen.dart`, `widgets/sos_button.dart`.

Missing but imported: `core/theme.dart`, `core/router.dart`, `screens/home_screen.dart`,
`screens/map_screen.dart`, `screens/alerts_screen.dart`, `screens/profile_screen.dart`,
`services/api_service.dart`, `services/location_service.dart`, `services/notification_service.dart`.

No `android/`, `ios/`, or `test/` directories. `flutter run` cannot work.

---

## Cross-cutting

- **Duplicated incident model.** `web-dashboard/src/types/incident.ts` and
  `backend/app/models/incident.py` define the same shape independently and already differ: the
  backend has an extra `false_alarm` status the dashboard type does not. Keep them in sync by hand
  until one becomes generated.
- **No tests anywhere**, in any component.
- **CI** (`.github/workflows/ci.yml`) checks the dashboard build, ha-config YAML syntax, and backend
  syntax only. It intentionally does not try to run the backend or build the mobile app.

---

## Open PRs — read before starting anything

Five PRs are open against `main`; the oldest has been open since 3 May. `main` has not moved since,
so every branch is working from the same stale base and they overlap with each other. This is
currently the largest source of duplicated effort in the project.

| PR | Branch | Adds | State |
|---|---|---|---|
| [#9](https://github.com/DevKognitiv/SafeR-CI/pull/9) | `feature/ha-mobile-integration` | Flutter MQTT service, 3 backend endpoints for `rest_commands.yaml`, Aurora design + i18n | Draft |
| [#10](https://github.com/DevKognitiv/SafeR-CI/pull/10) | `feature/backend-e2e` | **Makes the backend boot**: `core/database.py`, `schemas/`, `services/`, health/alerts/users routes, `__init__.py`, `.env.example` | Draft |
| [#11](https://github.com/DevKognitiv/SafeR-CI/pull/11) | `security/critical-fixes-2026-07-02` | **Auth on the emergency API, HMAC on the HA webhook, rate limiting, CVE bump** | Ready |
| [#12](https://github.com/DevKognitiv/SafeR-CI/pull/12) | `claude/safer-pricing-page-xb6exw` | Marketing pricing page + shared site chrome, 4 languages | Draft |
| [#13](https://github.com/DevKognitiv/SafeR-CI/pull/13) | `claude/code-audit-cleanup-kve4ls` | This audit: docs, CI, gitignore | Draft |

Known overlaps to resolve when merging:

- **#10 and #13 both add `backend/.env.example`.** Keep #10's — it was written against the modules
  it also adds.
- **#10, #9 and #13 all touch `.gitignore`.** #9 adds a `!mobile/lib/**` exception to escape the
  Python `lib/` rule; #13 removes that rule entirely, so the exception becomes unnecessary.
- **#10 and #13 both add a dashboard lockfile.** Same file, regenerate once after merging.
- **#11 builds on backend modules that only exist in #10.** Merge order matters: #10 before #11.

Suggested order: **#11 → #10** (or #10 → #11 if #11 does not apply cleanly to `main`), then #13,
then #9, then #12. Update this file as they land.
