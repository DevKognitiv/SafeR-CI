# SafeR-CI — Agent Brief

Open-source community safety platform for Côte d'Ivoire. Four components, **very different maturity**.
Read `docs/STATUS.md` before touching `backend/` or `mobile/` — most of their imports point at files
that were never written. Do not go hunting for them.

## Component map

| Path | Stack | State | Runs? |
|---|---|---|---|
| `web-dashboard/` | Next.js 14 App Router, TS, Tailwind, Leaflet | **Working** — the only runnable component | Yes |
| `ha-config/` | Home Assistant YAML | **Complete config**, unvalidated on hardware | On a HA node |
| `backend/` | FastAPI + PostGIS + Celery | **Scaffold** — does not import | No |
| `mobile/` | Flutter 3, Riverpod, go_router | **Scaffold** — does not build | No |

Default to `web-dashboard/` when a request is ambiguous about where work goes.

## Commands

```bash
# web-dashboard (the one that works)
cd web-dashboard && npm install
npm run dev        # http://localhost:3000
npm run build      # must pass before any dashboard PR
npm run lint

# ha-config — YAML syntax only; no HA available in CI
python -c "import yaml,sys,glob; [yaml.safe_load(open(f)) for f in glob.glob('ha-config/**/*.yaml', recursive=True)]"

# backend — syntax-checkable only, NOT runnable
python -m compileall -q backend/app
```

There are no tests in this repo yet. Do not claim a change is "tested" without adding one.

## Conventions

- **User-facing strings are French (fr-CI).** Emergency numbers: Police 170, Pompiers 180, SAMU 185, Gendarmerie 111.
- Dashboard imports use the `@/*` alias → `web-dashboard/src/*`.
- Incident shape is defined twice and **must stay in sync**: `web-dashboard/src/types/incident.ts`
  and `backend/app/models/incident.py`. Changing one without the other is a bug.
- Abidjan map default: lat `5.3484`, lon `-4.0107`, zoom `12`.
- Secrets live in `.env` / `.env.local` / `ha-config/secrets.yaml` — all gitignored. Never commit real values;
  update the matching `.example` file instead.

## Boundaries

- `web-dashboard/src/app/api/*` is an **in-memory demo store** seeded from `src/lib/mock-data.ts`.
  It resets on cold start and is not the real backend. Do not treat it as persistence.
- `IncidentMap.tsx` loads Leaflet from a CDN at runtime rather than the installed npm package.
  That is deliberate (SSR workaround) — leave it unless asked to change it.
- Do not scaffold `backend/` or `mobile/` modules speculatively. If a task needs them,
  say so and confirm scope first — it is a large, separate piece of work.
