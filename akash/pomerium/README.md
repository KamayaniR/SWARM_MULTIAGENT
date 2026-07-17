# swarm-pomerium — zero-trust ingress for the Akash sandbox

Builds the `swarm-pomerium` image referenced by
`akash/deploy-sandbox-pomerium.yaml`. Pomerium becomes the only public service;
the sandbox `agent` moves to the internal Akash mesh.

```
internet ──https──▶ Akash edge (TLS) ──http──▶ Pomerium ──http──▶ agent:8080
                                                  │ authenticates the orchestrator
                                                  ▼ (fail-closed until auth wired)
```

## Files

| File | Purpose |
|---|---|
| `config.yaml` | Baked-in Pomerium config: one route → internal `agent:8080`, fail-closed policy. Safe to commit (no secrets). |
| `Dockerfile` | `FROM pomerium/pomerium` + the config. |

## Build & push

```bash
cd akash/pomerium
docker build -t himanishprakash23/swarm-pomerium:latest .
docker push  himanishprakash23/swarm-pomerium:latest
```

## Deploy

Deploy `akash/deploy-sandbox-pomerium.yaml` via Akash Console. In its
`pomerium` service env, set:

- `SHARED_SECRET`, `COOKIE_SECRET` — `head -c32 /dev/urandom | base64` each.
- `AUTHENTICATE_SERVICE_URL` (optional) — overrides the file so you don't have
  to rebuild the image when the ingress host changes.

After the lease is up, note the Pomerium ingress host and put it in **both**
`authenticate_service_url` and the route `from` in `config.yaml` (or override
via env), then point `SANDBOX_AKASH_URLS` in `.env` at the **Pomerium** URI
(not the agent's).

## Two steps still open (by design)

1. **Public host** — replace the `CHANGE_ME.ingress...` placeholders in
   `config.yaml` with the real Pomerium ingress host (or a custom domain).
2. **Auth** — the route is currently `policy: []` = **deny all** (fail-closed).
   Wire the orchestrator's identity (JWT service account or mTLS), then:
   - add the `allow` rule shown in `config.yaml`, and
   - update `AkashSandbox._headers()` (sandbox/akash.py:54) to send the
     Pomerium credential instead of the raw bearer token.

   To smoke-test Pomerium→agent routing *before* auth, temporarily uncomment
   the clearly-marked TEST-ONLY block in `config.yaml` (reopens the endpoint —
   re-close it immediately after).
