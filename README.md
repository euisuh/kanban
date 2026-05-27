# Kanban

Minimal self-hosted kanban board with a calm interface and file-backed persistence.

## Run Locally

```bash
python -m app.server
```

Open `http://127.0.0.1:8080`.

## Docker

```bash
docker compose up -d --build
```

Open `http://<homeserver-ip>:8080`.

Board data is stored at `./data/board.json` by default.

For reverse-proxy deployments, set `KANBAN_CREDENTIAL=user:password` in `.env`.
The app will require HTTP Basic Auth when that variable is present.

## Config

| Variable | Default | Purpose |
| --- | --- | --- |
| `KANBAN_HOST` | `127.0.0.1` | Bind host for local Python runs |
| `KANBAN_PORT` | `8080` | HTTP port |
| `KANBAN_DATA` | `data/board.json` | JSON storage file |
| `KANBAN_CREDENTIAL` | empty | Optional Basic Auth credential as `user:password` |

## Features

- Add, edit, delete, and move cards across columns
- Drag cards between columns
- Persistent JSON storage with atomic writes
- Responsive layout for desktop and mobile
- No external runtime dependencies
