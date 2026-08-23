# Deployment

The pipeline: `.github/workflows/ci.yml` tests every push and PR. `.github/
workflows/deploy.yml` triggers only after CI passes on `main`, then builds
both Docker images, pushes them to GitHub Container Registry, runs
migrations, and deploys. Nothing here is specific to any one laptop -- once
the secrets below are set on the repo, either of you can trigger a deploy by
merging to `main`, from any machine, or none at all.

## What needs to exist before this pipeline can deploy anything

The pipeline builds and pushes images regardless. It stops short of an
actual deploy until these exist:

1. **A production Postgres and object storage bucket.** Per the chat
   decision: a managed Postgres (Neon or Supabase, Mumbai/India-adjacent
   region) and S3-compatible storage (AWS S3 `ap-south-1` or Cloudflare R2).
   Neither is provisioned by this pipeline -- create them once, by hand.
2. **A WorkOS production environment** (separate from whatever you used for
   local testing), per `docs/workos_setup.md`.
3. **A hosting platform for the two containers.** The deploy job ships with
   a worked Fly.io example; swapping it is a few lines (below).

## Repo secrets and variables to set

GitHub repo -> Settings -> Secrets and variables -> Actions.

| Name | Type | Used by |
|---|---|---|
| `DATABASE_URL` | Secret | `migrate` job, and whatever you set as the API container's own env var |
| `FLY_API_TOKEN` | Secret | `deploy` job (Fly.io example only -- omit if you swap platforms) |
| `NEXT_PUBLIC_API_BASE_URL` | Variable | `build-and-push` (baked into the web image at build time) |
| `NEXT_PUBLIC_WORKOS_REDIRECT_URI` | Variable | `build-and-push` (baked in at build time) |

Not set as GitHub secrets at all -- these belong on the running containers
themselves (Fly `flyctl secrets set`, or your platform's equivalent), since
they're read at runtime, not at image build time: `OBJECT_STORE_ENDPOINT`,
`OBJECT_STORE_ACCESS_KEY`, `OBJECT_STORE_SECRET_KEY`, `OBJECT_STORE_BUCKET`,
`WORKOS_API_KEY`, `WORKOS_CLIENT_ID` (backend), `WORKOS_API_KEY`,
`WORKOS_CLIENT_ID`, `WORKOS_COOKIE_PASSWORD` (frontend, its own WorkOS
verification per `web/.env.local.example`).

`GITHUB_TOKEN` is automatic -- GitHub Actions provides it, and it already
has permission to push to this repo's own GHCR namespace.

## Why the pipeline is shaped this way

- **`deploy.yml` triggers on `workflow_run`, not `push`.** If it triggered
  on push directly, a broken commit pushed straight to `main` could reach
  production before CI ever ran. Gating on CI's own conclusion closes that
  gap.
- **Migrations run as their own job, never inside the API container's
  startup.** `db/migrations/runner.py` is idempotent (tracked in
  `app.schema_migration`), but if every new container instance tried to
  migrate on boot, a multi-instance deploy could race two instances into
  applying the same migration concurrently. One job, before any new
  instance starts, avoids that entirely.
- **The API image takes no build-time secrets.** It's the same image
  whether it's serving a pilot tenant or a production one; everything it
  needs is a runtime env var. The web image is the exception, because
  Next.js bakes `NEXT_PUBLIC_*` values into the client JS bundle at build
  time -- there's no way to inject them later the way a server can.
- **The deploy step degrades gracefully, not silently.** If `FLY_API_TOKEN`
  isn't set, the job prints what it would have done and exits 0 rather than
  failing the whole pipeline -- images still get built, tagged and pushed,
  and migrations still run, so none of that work is lost while you're still
  deciding on a hosting platform.

## Swapping the deploy step for a different platform

`build-and-push` and `migrate` don't change. Only the final `deploy` job's
steps do. Two worked alternatives:

**Cloud Run** (`asia-south1`, Mumbai):
```yaml
- uses: google-github-actions/auth@v2
  with: { credentials_json: '${{ secrets.GCP_SA_KEY }}' }
- uses: google-github-actions/deploy-cloudrun@v2
  with:
    service: spequla-api
    region: asia-south1
    image: ${{ env.API_IMAGE }}:${{ needs.build-and-push.outputs.sha }}
```
(a second step, same shape, for the web image as its own Cloud Run service).

**Render**: Render deploys off a registry image via a deploy hook URL
rather than a GitHub Action:
```yaml
- run: curl "${{ secrets.RENDER_API_DEPLOY_HOOK }}"
```
after pointing the Render service at the GHCR image tag this workflow just
pushed.

Either way: delete `fly.api.toml`/`fly.web.toml` if you're not using Fly, and
drop the `FLY_API_TOKEN` secret.

## Local dev is unaffected

`docker-compose.yml` (Postgres + MinIO) and `scripts/bootstrap.sh` are for
local development only and don't participate in this pipeline at all --
production points at the real managed Postgres/S3 instead, via
`DATABASE_URL`/`OBJECT_STORE_*`, same code either way.
