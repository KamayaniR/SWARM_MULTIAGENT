# Pomerium — zero-trust access to the Swarm Control dashboard

Pomerium is an identity-aware reverse proxy. It sits in front of the FastAPI
dashboard (`orchestrator/server.py`, port 8000), forces every visitor through a
login, and only forwards requests from allowed identities. The app code is
unchanged — anything that reaches `:8000` is already authenticated.

```
browser ──https──▶ Pomerium ──▶ login (GitHub) ──▶ policy check ──▶ uvicorn :8000
```

## One-time setup

1. **Secrets + IdP config**
   ```bash
   cp pomerium/.env.pomerium.example pomerium/.env.pomerium
   # generate the two base64 secrets:
   head -c32 /dev/urandom | base64   # -> POMERIUM_SHARED_SECRET
   head -c32 /dev/urandom | base64   # -> POMERIUM_COOKIE_SECRET
   ```
   Create a GitHub OAuth App at https://github.com/settings/developers with:
   - Homepage URL: `https://authenticate.localhost.pomerium.io`
   - Authorization callback URL: `https://authenticate.localhost.pomerium.io/oauth2/callback`

   Paste the client id/secret into `pomerium/.env.pomerium`.

2. **Local TLS certs**
   ```bash
   ./pomerium/gen-certs.sh
   ```

## Run

```bash
# terminal 1 — the app, exactly as before
uvicorn orchestrator.server:app --port 8000

# terminal 2 — the proxy
docker compose -f pomerium/docker-compose.pomerium.yml up
```

Open **https://swarm.localhost.pomerium.io** (accept the self-signed cert
warning). You'll be redirected to GitHub login; only `SWARM_ALLOWED_EMAIL`
gets through to the dashboard.

## Notes

- `*.localhost.pomerium.io` resolves to `127.0.0.1`, so no `/etc/hosts` or DNS
  changes are needed.
- The dashboard's live event stream (`/ws/events`) works because the route sets
  `allow_websocket_upgrade: true`.
- To allow any logged-in GitHub user instead of a single email, replace the
  `email: {is: ...}` policy in `config.yaml` with `authenticated_user: {}`.
- Prefer zero infra? Pomerium Zero (console.pomerium.app) is the hosted, free
  version of this same config — ask and I'll port it.
