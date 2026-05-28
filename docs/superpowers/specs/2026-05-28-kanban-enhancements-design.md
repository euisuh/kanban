# Kanban UI Enhancements — Design Spec

Date: 2026-05-28  
Branch: feat/self-hosted-kanban (branch from here)

## Overview

Five enhancements to the self-hosted kanban app:
1. Transparent column panes (glassmorphism)
2. Richer card metadata (project, priority, date created)
3. Customizable board background (upload or URL)
4. Smart quick-add syntax with live parse preview
5. Expandable card modal with smooth animation

---

## 1. Data Model

### Card schema additions

```json
{
  "id": "abc123",
  "title": "Buy milk",
  "notes": "almond not oat",
  "project": "PersonalLife",
  "priority": 4,
  "column": "backlog",
  "createdAt": 1234567890,
  "updatedAt": 1234567890
}
```

- `priority`: int 1–4 (1=Urgent, 2=High, 3=Med, 4=Low). Default `4`.
- `project`: string. Default `""`.
- Both fields are optional in the API — existing cards normalize to defaults.

### Board-level settings

Top-level `settings` key added to `board.json`:

```json
{
  "settings": {
    "background": {
      "type": "none",
      "value": "",
      "fit": "cover"
    }
  },
  "columns": [...],
  "cards": [...]
}
```

- `type`: `"none"` | `"url"` | `"upload"`
- `value`: URL string or `/uploads/filename.ext`
- `fit`: `"cover"` | `"contain"` | `"center"` (maps to `background-size`)

---

## 2. API Changes

### Existing — extended

`PATCH /api/cards/:id` — gains `project` (str) and `priority` (int 1–4) in accepted patch fields.

### New endpoints

**`PATCH /api/board/settings`**  
Body: `{ "background": { "type": "url", "value": "https://...", "fit": "cover" } }`  
Returns: updated settings object.

**`POST /api/upload`**  
Multipart form upload. Server validates MIME (jpeg/png/webp/gif only). Saves to `app/static/uploads/`. Returns `{ "path": "/uploads/filename.ext" }`.

### `GET /api/board` response

Already returns full board. Now includes `settings` key at top level.

---

## 3. Column Transparency

Trello-style glassmorphism. CSS:

```css
.column {
  background: rgba(255, 253, 248, 0.45);
  backdrop-filter: blur(12px);
  border: 1px solid rgba(255, 255, 255, 0.28);
}
```

Gracefully near-opaque when no background image is set.

---

## 4. Card Layout (Collapsed)

Each card shows:
- Priority badge (pastel color chip) + project name chip — top row
- Title (bold)
- Notes (muted, 2-line clamp)
- Created date (small, muted)
- Delete button (top-right)

**Priority badge colors (pastel):**
| Level | Background | Text |
|-------|-----------|------|
| p1 Urgent | `#fdd` | `#c0392b` |
| p2 High | `#fde8d0` | `#c0672b` |
| p3 Med | `#fdf6c0` | `#9a7d0a` |
| p4 Low | `#e0e6f0` | `#5a6478` |

**Sort order within each column:** `priority asc` then `createdAt asc` (p1 floats to top). Drag-and-drop still moves cards between columns only.

---

## 5. Quick-Add Parser

Single input. Live parse preview appears below as user types.

**Syntax:**
```
Title text @ProjectName p2 | optional notes here
```

**Parse rules (left-to-right):**
- `@word` (any position) → project name. Last `@word` wins if multiple.
- `p1`–`p4` as standalone token → priority
- `| rest of line` → notes (everything after first `|`)
- Remaining tokens → title

**Examples:**
```
Fix login bug @Auth p1 | check token expiry   → title="Fix login bug", project="Auth", priority=1, notes="check token expiry"
Write tests                                    → title="Write tests", project="", priority=4, notes=""
@Design p3 Update hero banner                  → title="Update hero banner", project="Design", priority=3
```

**UX:**
- Preview line renders below input: `Title: Fix login bug · @Auth · p1`
- `Enter` submits, adds to Backlog column
- `Escape` clears input and preview
- Submit button removed — keyboard only

---

## 6. Card Expand Modal

Clicking the card body (anywhere except the delete button) opens the expand modal.

**Layout:**
```
┌──────────────── modal ──────────────────────┐
│  [p2]  PersonalLife              [×] close  │
│  ─────────────────────────────────────────  │
│  Title                                      │
│  ┌─────────────────────────────────────┐   │
│  │ Buy milk                            │   │
│  └─────────────────────────────────────┘   │
│                                             │
│  Project          Priority    Column        │
│  [PersonalLife]   [p1][p2✓]  [Backlog ▾]  │
│                   [p3][p4]                  │
│                                             │
│  Notes                                      │
│  ┌─────────────────────────────────────┐   │
│  │ almond not oat                      │   │
│  └─────────────────────────────────────┘   │
│                                             │
│  Created May 28, 2026                       │
└─────────────────────────────────────────────┘
```

**Fields:**
- Title — text input
- Project — text input
- Priority — segmented button group (p1/p2/p3/p4), pastel colors
- Column — `<select>` dropdown
- Notes — textarea (resizable)
- Created date — read-only

**Behavior:**
- Changes auto-save on field blur (`PATCH /api/cards/:id`)
- Click backdrop or `Escape` closes
- No explicit save button

**Transition:**
- Open: `opacity: 0 → 1`, `transform: scale(0.92) → scale(1)`, `200ms cubic-bezier(0.4, 0, 0.2, 1)`
- Close: same easing reversed, `150ms`
- Backdrop: `opacity: 0 → 0.4` (dark overlay)

---

## 7. Background Customization

Gear icon (⚙) in topbar. Settings panel slides down inline (not a modal).

**Panel layout:**
```
[ Upload file ]  [ Paste URL ]  [ None ]

Upload mode: [  Choose image...  ]
URL mode:    [  https://...      ]
Fit:         ( Cover ) ( Contain ) ( Center )

Preview thumbnail (80×50px)

                              [  Apply  ]
```

**Upload flow:**
1. User picks file → preview shown immediately (FileReader API)
2. Apply → `POST /api/upload` → get `/uploads/filename.ext`
3. `PATCH /api/board/settings` with `{ type: "upload", value: "/uploads/...", fit }`

**URL flow:**
1. User pastes URL → preview loads in thumbnail
2. Apply → `PATCH /api/board/settings` with `{ type: "url", value: "https://...", fit }`

**None:** clears background, reverts to default gradient.

**Fit options:**
- Cover → `background-size: cover` (fills, crops)
- Contain → `background-size: contain` (full image, may letterbox)
- Center → `background-size: auto; background-position: center` (no scale)

---

## 8. File Structure Changes

```
app/
  server.py          — add PATCH /api/board/settings, POST /api/upload
  storage.py         — add settings to schema, project/priority to cards
  static/
    index.html       — add modal template, settings panel, card template updates
    styles.css       — column glass, card badges, modal, transitions
    app.js           — parser, modal logic, settings logic, sort
    uploads/         — new dir, created on first upload (gitignored)
```

---

## 9. Out of Scope

- Card due dates
- Multiple boards
- User assignments
- Drag reorder within a column
- Dark mode
