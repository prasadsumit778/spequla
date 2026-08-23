# WorkOS setup

The code side of the WorkOS integration is done (see the commits from
"auth: real WorkOS session verification" onward). Everything below is the
account-owner-only part -- account creation, key generation, and role/org
configuration -- that only you can do, since it requires logging into a
WorkOS account.

## 1. Create the WorkOS account and application

1. Sign up at [workos.com](https://workos.com) if you don't already have an
   account.
2. In the dashboard, you'll have a default Application (or create one) --
   this is what issues `WORKOS_CLIENT_ID` and `WORKOS_API_KEY`.
3. Under the application's **Redirects** settings, add:
   - Redirect URI: `http://localhost:3000/callback` (add your production
     domain's `/callback` too once you have one)
   - Default Logout URI: wherever you want users sent after sign-out, e.g.
     `http://localhost:3000`
4. Enable **AuthKit** for the application if it isn't already (it's the
   hosted login UI this integration uses -- `web/middleware.ts` redirects
   here for anyone unauthenticated).

## 2. Create the four SPEQULA roles

Under the dashboard's **Roles** section, create exactly these four role
slugs -- they must match `VALID_ROLES` in `src/api/deps/auth.py` and
`UPLOAD_ALLOWED_ROLES` in `web/app/upload/page.tsx` verbatim, since the code
compares against these strings:

| Slug | Corresponds to (corpus/02 section 2) |
|---|---|
| `promoter` | Owner, MD or CEO |
| `client_finance_lead` | CFO, controller or CA |
| `spequla_analyst` | You, for pilot one |
| `admin` | Engineering |

Set `spequla_analyst` (or whichever role you use day to day) as the default
role for new memberships if the dashboard offers that, so you don't have to
assign it by hand every time.

## 3. Create an Organization per pilot tenant, and invite users

WorkOS Organizations map 1:1 to SPEQULA tenants (`app.tenant`).

For each pilot company:

1. Create a WorkOS **Organization** for it.
2. Invite the people who should have access, assigning each one the correct
   role from the table above via their **Organization Membership**.
3. Note the Organization's id (`org_...`).
4. Link it to the corresponding SPEQULA tenant:
   ```bash
   python3 scripts/create_tenant.py "Acme Manufacturing Pvt Ltd"
   # prints tenant_id=... schema_name=...
   python3 db/migrations/runner.py   # applies the new tenant's schema
   python3 scripts/seed_dim_date.py --schema <schema_name> --start 2022-04-01 --end 2029-03-31
   python3 scripts/seed_entity.py --schema <schema_name> --tenant-id <tenant_id> --name "Acme Manufacturing Pvt Ltd"
   python3 scripts/link_tenant_workos_org.py --tenant-id <tenant_id> --workos-org-id org_...
   ```

Until step 4 runs, users in that Organization can sign in (WorkOS
authenticates them fine) but every API call will 404 with "no SPEQULA tenant
is linked to WorkOS organization ..." -- that's `src/api/deps/tenant.py`
failing loudly rather than guessing which tenant they meant.

## 4. Get the keys and fill in the env files

From the application's **API Keys** page:

```bash
cp .env.example .env
cp web/.env.local.example web/.env.local
```

Fill in, in both files:
- `WORKOS_API_KEY` (starts `sk_`)
- `WORKOS_CLIENT_ID` (starts `client_`)

In `web/.env.local` only, also set:
- `WORKOS_COOKIE_PASSWORD` -- generate with `openssl rand -base64 24`
  (must be at least 32 characters; this encrypts the session cookie, treat
  it like any other secret)
- `NEXT_PUBLIC_WORKOS_REDIRECT_URI` -- must exactly match what you added to
  Redirects in step 1

Never paste these into chat with an AI assistant, including this one -- set
them directly in your own `.env` files.

## 5. Verify

```bash
# backend
uvicorn src.api.main:app --reload
# frontend, separate terminal
cd web && npm run dev
```

Visit `http://localhost:3000` -- you should be redirected to the AuthKit
hosted login. After signing in as a user with an Organization Membership
linked to a tenant, `/upload` and `/load-runs` should work; a user with the
`promoter` role should see `/upload` refuse them (client-side) and the
backend refuse them too if they bypass the UI (`require_upload_role`,
`src/api/deps/auth.py`).
