# SafeR-CI — Component Status

Ground truth for what actually runs. Keep this current; `CLAUDE.md` points here and it is the
cheapest way to stop anyone (human or agent) re-deriving the state of the repo from scratch.

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

## `backend/` — scaffold, does not import

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

## `mobile/` — scaffold, does not build

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
