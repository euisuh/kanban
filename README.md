# Kanban

Minimal self-hosted task board. The goal: something anyone can run in under a minute, with no database, no heavy framework, and no accounts to manage. Board state lives in a single JSON file.

![Kanban board](docs/screenshots/board.png)

## Features

- **Drag and drop** — move cards between columns with mouse or touch
- **Quick-add** — add tasks from the top bar with inline syntax: `Fix login bug @Auth p1 | happens on Safari`
- **Filters** — search cards by text, filter by project tag or priority
- **Card detail** — click any card to edit title, notes, project, and priority; auto-saves
- **Custom background** — set a background image from a URL or file upload
- **Mobile-friendly** — responsive layout, touch drag, swipe to switch columns
- **Optional auth** — protect the board with HTTP Basic Auth via one environment variable
- **Demo mode** — expose a separate public demo board at a different URL without revealing your real data

## Screenshots

<details>
<summary>Card detail</summary>

![Card detail](docs/screenshots/card-modal.png)

</details>

<details>
<summary>Background settings</summary>

![Background settings](docs/screenshots/settings-panel.png)

</details>

<details>
<summary>Mobile</summary>

![Mobile view](docs/screenshots/mobile.png)

</details>

## Quick start

```bash
git clone https://github.com/euisuh/kanban.git
cd kanban
cp .env.example .env
# edit .env — set KANBAN_CREDENTIAL=yourname:yourpassword
docker compose up -d
```

Open [http://localhost:8097](http://localhost:8097).

## Configuration

Set options in `.env`:

| Variable | Description |
| --- | --- |
| `KANBAN_CREDENTIAL` | `username:password` to protect the board. Omit to run without auth. |
| `KANBAN_DEMO_CREDENTIAL` | Optional second login (e.g. `demo:demo`) that gets its own separate board — useful for sharing a demo at a public URL. |

## Data

Board state is stored in `./data/board.json`. Back this file up to preserve your board.

```bash
cp data/board.json ~/kanban-backup.json
```

## Tests

```bash
python -m pytest
```

## Nginx (optional)

A sample TLS reverse proxy config is at [`nginx/kanban.conf.example`](nginx/kanban.conf.example).

## License

MIT
