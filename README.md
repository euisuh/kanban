# Kanban

Minimal self-hosted kanban board for a homeserver. It serves one responsive web UI, stores the board in a local JSON file, and can sit behind nginx at `kanban.uiseoya.com`.

## What It Does

- Add, edit, delete, and drag cards across columns
- Persist all board data in `./data/board.json`
- Require HTTP Basic Auth when `KANBAN_CREDENTIAL` is set
- Run with Docker Compose on `127.0.0.1:8097`
- Use nginx as public TLS reverse proxy for `https://kanban.uiseoya.com`
- Avoid runtime app dependencies beyond Python stdlib

## Current Deployment

| Thing | Value |
| --- | --- |
| App directory | `/Users/uiseo/Documents/deploy/kanban` |
| Container | `kanban` |
| Local app URL | `http://127.0.0.1:8097` |
| Public URL | `https://kanban.uiseoya.com` |
| Data file | `./data/board.json` |
| Credential file | `.env` |
| nginx vhost | `/opt/homebrew/etc/nginx/servers/kanban.uiseoya.com.conf` |
| TLS cert | `/Users/uiseo/.config/kanban/certbot/config/live/kanban.uiseoya.com/` |

## Credentials

Credentials live in `.env`:

```env
KANBAN_CREDENTIAL=kanban:your-password
KANBAN_DEMO_CREDENTIAL=demo:demo
```

`KANBAN_DEMO_CREDENTIAL` is optional and intentionally non-secret. It gives the public console a demo login while keeping the main `KANBAN_CREDENTIAL` prompt for admin use. Demo data is stored separately under `./data/demo/board.json`.

After changing `.env`, restart the container so it loads the new value:

```bash
cd /Users/uiseo/Documents/deploy/kanban
docker compose up -d
```

Verify auth:

```bash
curl -I http://127.0.0.1:8097/
CRED=$(sed -n 's/^KANBAN_CREDENTIAL=//p' .env)
curl -I -u "$CRED" http://127.0.0.1:8097/
```

Expected:

- Without credentials: `401 Unauthorized`
- With credentials: `200 OK`

## Common Commands

Start or restart:

```bash
cd /Users/uiseo/Documents/deploy/kanban
docker compose up -d
```

Rebuild after code changes:

```bash
cd /Users/uiseo/Documents/deploy/kanban
docker compose up -d --build
```

Stop:

```bash
cd /Users/uiseo/Documents/deploy/kanban
docker compose down
```

Show container status:

```bash
docker ps --filter name=kanban
```

Watch logs:

```bash
cd /Users/uiseo/Documents/deploy/kanban
docker compose logs -f
```

Run tests:

```bash
cd /Users/uiseo/Documents/deploy/kanban
python -m pytest
```

Check Docker config:

```bash
cd /Users/uiseo/Documents/deploy/kanban
docker compose config
```

## Public Domain

The app should be served by nginx:

```text
https://kanban.uiseoya.com -> nginx TLS -> http://127.0.0.1:8097
```

If nginx config changed, reload root nginx:

```bash
sudo /opt/homebrew/opt/nginx/bin/nginx -t
sudo launchctl kickstart -k system/homebrew.mxcl.nginx
```

Verify public auth:

```bash
curl -I https://kanban.uiseoya.com
CRED=$(sed -n 's/^KANBAN_CREDENTIAL=//p' /Users/uiseo/Documents/deploy/kanban/.env)
curl -I -u "$CRED" https://kanban.uiseoya.com
```

Expected:

- Without credentials: `401 Unauthorized`
- With credentials: `200 OK`

## TLS Certificate

Certificate was issued with user-writable certbot config:

```bash
certbot certonly \
  --webroot \
  -w /opt/homebrew/var/www/letsencrypt \
  -d kanban.uiseoya.com \
  --cert-name kanban.uiseoya.com \
  --config-dir /Users/uiseo/.config/kanban/certbot/config \
  --work-dir /Users/uiseo/.config/kanban/certbot/work \
  --logs-dir /Users/uiseo/.config/kanban/certbot/logs
```

Renew manually:

```bash
certbot renew \
  --config-dir /Users/uiseo/.config/kanban/certbot/config \
  --work-dir /Users/uiseo/.config/kanban/certbot/work \
  --logs-dir /Users/uiseo/.config/kanban/certbot/logs
sudo launchctl kickstart -k system/homebrew.mxcl.nginx
```

## Backups

Board data is one JSON file:

```bash
cp data/board.json ~/Desktop/kanban-board-backup.json
```

Restore:

```bash
cp ~/Desktop/kanban-board-backup.json data/board.json
docker compose up -d
```

## Troubleshooting

If credentials do not change, the container has not reloaded `.env`:

```bash
docker compose up -d
```

If local auth works but public domain redirects to `uiseoya.com`, nginx has not loaded the `kanban.uiseoya.com` vhost:

```bash
sudo /opt/homebrew/opt/nginx/bin/nginx -t
sudo launchctl kickstart -k system/homebrew.mxcl.nginx
```

If public domain returns `502`, check container status:

```bash
docker ps --filter name=kanban
docker compose logs --tail=80
```

If anonymous access returns `200`, `.env` is missing `KANBAN_CREDENTIAL` or container was started without it:

```bash
grep '^KANBAN_CREDENTIAL=' .env
docker compose up -d
```
