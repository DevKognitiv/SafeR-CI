# Contributing to SafeR-CI

Thanks for helping build community safety infrastructure for Côte d'Ivoire.

## Before you start

Read [`docs/STATUS.md`](STATUS.md). Only `web-dashboard/` and `ha-config/` are in a usable state;
`backend/` and `mobile/` are scaffolds whose imports point at files that do not exist yet. Knowing
which of those you are in saves everyone a lot of time.

## Setup

```bash
git clone https://github.com/DevKognitiv/SafeR-CI.git
cd SafeR-CI/web-dashboard
npm install
npm run dev          # http://localhost:3000
```

## Before opening a PR

Run whatever applies to what you touched — these are exactly the checks CI runs:

```bash
# web-dashboard
cd web-dashboard && npm run lint && npm run build

# ha-config
python -c "import yaml,glob;[yaml.safe_load(open(f)) for f in glob.glob('ha-config/**/*.yaml',recursive=True)]"

# backend
python -m compileall -q backend/app
```

## Conventions

- **User-facing strings are French (fr-CI).** Escape apostrophes in JSX as `&apos;` — ESLint enforces it.
- Keep `web-dashboard/src/types/incident.ts` and `backend/app/models/incident.py` in sync. They
  describe the same incident and currently drift.
- Never commit real secrets. Update the relevant `.example` file instead: `backend/.env.example`,
  `web-dashboard/.env.example`, `ha-config/secrets.yaml.example`.
- Keep PRs scoped to one component where you can. Cross-cutting changes to the incident shape are
  the exception and should say so in the description.

## Filling in a scaffold

If you are implementing the missing `backend/` or `mobile/` modules, open an issue first describing
the slice you are taking. These are large and easy to duplicate. Update `docs/STATUS.md` in the same
PR and promote the matching CI job from a syntax check to a real one.

## Emergency numbers (Côte d'Ivoire)

Police 170 · Sapeurs-Pompiers 180 · SAMU 185 · Gendarmerie 111
