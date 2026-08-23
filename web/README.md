# SPEQULA — web

Next.js + TypeScript frontend. See the [repo root README](../README.md) for the full project, corpus, architecture, and local setup instructions (including the WorkOS configuration this frontend needs).

Quick start once `web/.env.local` is filled in:

```
npm install
npm run dev
```

Runs on `http://localhost:3000`, talking to the FastAPI backend at `NEXT_PUBLIC_API_BASE_URL` (defaults to `http://localhost:8000`).

## Screens

Upload, Load runs, Mapping, Statements, Overview, Data health, Exceptions, Ask, Reports, Operating (profile-specific: consumer CM ladder / manufacturing operating metrics), Settings (roles, employee access grants, audit log, restore rehearsal, tenant deletion).
