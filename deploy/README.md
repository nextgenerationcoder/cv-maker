# Deploying to cvmaker.amirseyti.de

This app runs behind the shared Traefik reverse proxy already set up for
other apps on this VPS (`/root/n8n-compose/compose.yaml`), which handles
routing and Let's Encrypt certificates automatically via Docker labels —
no manual nginx or certbot config needed here.

## 1. DNS

Add an A record for `cvmaker.amirseyti.de` pointing at the VPS's IP, the
same way `book.amirseyti.de` is set up. This has to be done in your DNS
provider — nothing in this repo can do it for you.

## 2. Get the code onto the server and start it

```bash
ssh you@your-server
git clone https://github.com/nextgenerationcoder/cv-maker.git
cd cv-maker
docker compose up -d --build
```

`docker-compose.yml` here builds two containers:
- `backend` — FastAPI + JobSpy. Internal only, no Traefik labels — nothing
  external ever reaches it directly.
- `frontend` — nginx serving the static UI and proxying `/api/` to
  `backend`. This is the one Traefik routes to, via labels on the
  `frontend` service:
  - `traefik.http.routers.cvmaker.rule=Host(\`cvmaker.amirseyti.de\`)`
  - `traefik.http.services.cvmaker.loadbalancer.server.port=80` — this
    is nginx's actual internal listening port (set in
    `frontend/nginx.conf`), not a host-published port. Neither container
    publishes a port to the host at all — Traefik reaches them over the
    shared `n8n-compose_default` Docker network, so there's no host port
    to pick or conflict with.

Both services join `n8n-compose_default` as an `external` network — this
repo only attaches to that network, it never touches the shared Traefik/
n8n compose file itself.

The router/service name `cvmaker` must stay unique across every compose
file on this VPS (Traefik would otherwise get two conflicting definitions
for the same name) — don't reuse it for another app.

## 3. Verify

Within a minute or two, Traefik should provision the certificate and
`https://cvmaker.amirseyti.de` should load the app. If it 404s or 502s,
check:

```bash
docker compose ps
docker compose logs -f backend
docker compose logs -f frontend
docker logs <traefik-container-name> --tail 50   # cert/routing errors show up here
```

## Redeploying after a code change

```bash
cd cv-maker
git pull
docker compose up -d --build
```

## Persistent data

None currently — this app has no accounts or database, so there's no
volume to manage. If that changes later (e.g. saved searches, user
accounts), add a named Docker volume (not a bind-mount into the repo) the
same way other stateful apps on this VPS do.
