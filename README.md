# Downloads-Managarr

You know the situation. You've got a home server running 24/7, Sonarr and Radarr humming along, and somewhere in `/data/completed` there's a pile of stuff that didn't auto-import — wrong filename, wrong folder structure, manual grab, whatever. It happens constantly.

The "correct" fix is to RDP or VNC into the Windows box, open File Explorer, drag things around. But that feels like overkill just to move three files. Or you're on a Mac and you try to browse the SMB share — and SMB on macOS is a disaster. Finder stalls. Transfers hang. Copy speeds are embarrassing. You end up opening a terminal and doing it with `rsync` over SSH like it's 1998.

There's no good middle ground. Until you just... build one.

**Downloads-Managarr** is a self-hosted web app that lives on your server and gives you a clean browser UI to browse your download folders, queue up move/copy/delete actions against your media library, and run them — all without touching a desktop or fighting with a network share. It's not trying to replace Sonarr. It's the thing you reach for when Sonarr doesn't pick something up and you just need to get it where it belongs.

---

## Features

### File Browser
- Unified view across multiple **source folders** (e.g. `/data/completed`, `/data/usenet/completed`, `/data/torrents/completed`)
- Sort by name, source, type, size, or modified date
- Filter by All / Files / Folders, by media type (TV, Movie, Music, etc.), or by individual source
- **Toggle unrecognized files** (❓) — shows or hides files whose type couldn't be detected; on by default, also configurable in Settings → Appearance
- Multi-select with checkboxes or select-all
- Folder size calculation (cached)
- Breadcrumb navigation into subfolders

### Action Queue
- Queue **Move**, **Copy**, or **Delete** actions per selection
- Queue persists to disk — survives page refreshes and container restarts
- Drag-to-reorder queued items
- **Run Queue** — processes all items in sequence
- **Run Now** — execute the current selection immediately, bypassing the queue
- **Clear** — discard everything pending

### Smart Destinations
- Separate destination sections per media type (TV, Movie, Music, etc.)
- **Wrap in folder** — wraps a loose file in a new subfolder named after it (useful for multi-episode torrents that arrive as a single file)
- **Move contents only** — unwraps a folder and moves its contents directly to the destination
- **Season folder** — automatically places TV files inside a `Season XX` subfolder
- Custom destination name override with a rename field
- Warns when a wrapping decision might not be what you want (e.g. wrapping something that already looks like an episode)

### Archive Extraction
- **Extract** action in the action bar — select one or more archives and queue or run them immediately
- Supports `.zip`, `.tar`, `.tar.gz` / `.tgz`, `.tar.bz2` / `.tbz2`, `.tar.xz` / `.txz`, standalone `.gz` / `.bz2`
- Extract **in place** (same folder as the archive) or to any configured destination or custom path
- **Strip root folder** — if the archive has a single top-level directory, unwrap it so contents land directly in the destination
- **Rename on extract** — give the extracted output a different name without a separate rename step
- **Extract Temp Folder** (Settings → Housekeeping) — extractions stage in a temp directory before moving to the final destination, so your media library never sees a partial extraction
- Space check — warns if estimated uncompressed size exceeds free space on the target volume, with an option to pick an alternative destination

### Destination Free-Space Indicator
- Small accent-coloured **"X free"** label shown inline next to each destination selector
- Updates live when switching destinations; refreshes after saving settings

### Conflict Resolution
- When a destination file already exists, execution pauses
- Choose **Skip**, **Overwrite**, or **Rename** (auto-numbered suffix) per conflict
- Applies per-item so you can handle each collision differently in a single queue run

### Delete & Trash
- **Three trash modes** — Off (disabled), Auto (creates `.Trash` beside the source file automatically — default), or Custom (explicit path)
- **Move to Trash** — soft-delete to the configured/auto trash location (reversible)
- **Permanent Delete** — confirmation-gated, no takebacks
- Dedicated **Trash panel** — browse, restore (with auto-rename on collision), or permanently delete individual items
- **Empty Trash** to clear everything at once

### History Log
- All completed actions recorded: moves, copies, deletes, trash operations, restores
- Colour-coded labels per action type
- **↩ Restore** button on eligible entries — undoes the action:
  - Move/Trash → moves the file back to its original location
  - Copy → deletes the copy at the destination
  - Restore → moves the file back to trash
- Restore works even if the history record was pruned — backend falls back to path data sent by the client
- Full-text search across history
- Auto-prunes entries older than a configurable retention period (default 30 days; set to `-1` for unlimited)
- History entries for trashed files survive a "Clear History" — locked until the file is restored or permanently deleted

### Authentication (optional)
- Set `DL_MANAGARR_ADMIN_USERNAME` and `DL_MANAGARR_ADMIN_PASSWORD` in your environment to enable a login screen
- Clean login form — no placeholder credentials shown; both fields match the app's dark theme including when browser autofill is active
- Session-based auth with an `httponly` cookie — 30 days with *Keep me logged in*, 24 hours otherwise
- All `/api/*` routes are protected when auth is enabled; auth endpoints are always public
- Omit the env vars entirely to run with no login — behaves exactly as before
- Logout button appears in the header only when auth is active

### Per-User Preferences
- Theme, accent colour, custom colours, panel width, and text size saved server-side per user in `user_prefs.json`
- Persists across browsers, devices, and sessions
- When auth is disabled, preferences use a shared `default` key and still roam server-wide
- `localStorage` used as a fast-paint cache so the UI renders in your saved theme before the server responds

### Appearance
- **Themes:** Dark (default), OLED/Pure Black, Light, Custom (set your own background/surface/text colours)
- **Accent colours:** Purple (default), Blue, Green, Amber, or any custom hex
- **Text size:** Small (12px), Medium (14px), Large (16px) — applied instantly
- **Panel width:** drag the resize handle on the queue sidebar; size is remembered

### File-List Toolbar
- **Top row** — All / Files / Folders filter buttons, text filter input, ❓ toggle for unrecognized files, item count, and refresh (always visible)
- **Collapsible Sources & Destinations** — toggle bar below the controls row expands/collapses source and destination filter buttons with free-space labels; default state configurable in Settings → Behavior

### Queue Panel
- **☰ toggle button** always visible in the header — collapses/expands the queue sidebar on desktop; opens the slide-in overlay on mobile
- **⧉ floating mode toggle** in the queue panel header — switches the queue between a docked sidebar and a floating overlay (like mobile) on desktop; highlights in accent colour when active; syncs with Settings → Behavior
- **Floating queue** can also be enabled permanently in Settings → Behavior → "Floating queue panel (desktop)"
- Queue item count badge on the ☰ button whenever items are staged

### Real-Time Transfer Progress
- While a cross-filesystem copy or move is in progress, the execution modal shows a live mini progress bar with bytes transferred / total and current speed (e.g. `1.2 GB / 4.5 GB · 320 MB/s`)
- Same-filesystem moves are instant (`os.rename`) and show no byte-level progress

### Mobile / Responsive
- At ≤768px the queue panel becomes a slide-in overlay toggled by the ☰ header button; shows live queue count
- Action bar buttons (Add to Queue / Run Now / Clear) always reachable on small screens — file list shrinks to make room
- Modals become bottom sheets; settings nav collapses to a horizontal scrollable tab bar
- Table columns reduce on smaller screens (Source/Modified hidden at 768px; Type/Size hidden at 480px)
- Action bar warning tooltip is tap-to-show on mobile and uses `position: fixed` so it never goes off-screen

---

## Quick Start (Docker)

The image is published to GitHub Container Registry — no clone required.

### 1. Create a `docker-compose.yml`

```yaml
services:
  downloads-managarr:
    image: ghcr.io/pdxgeek421/downloads-managarr:latest
    container_name: downloads-managarr
    restart: unless-stopped
    ports:
      - "8181:8080"
    environment:
      - PUID=1000
      - PGID=1000
      - CONFIG_PATH=/config/config.json
      - DB_PATH=/config/state.db
      # ── Authentication ──────────────────────────────────────────────────────
      # Remove both to disable the login screen entirely
      - DL_MANAGARR_ADMIN_USERNAME=youruser
      - DL_MANAGARR_ADMIN_PASSWORD=yourpassword
      # ── Sources ─────────────────────────────────────────────────────────────
      # - SOURCE_0_PATH=/path/to/your/data/completed
      # - SOURCE_0_LABEL=Completed
      # - SOURCE_1_PATH=/path/to/your/data/usenet/completed
      # - SOURCE_1_LABEL=Usenet
      # ── Destinations ────────────────────────────────────────────────────────
      # - DEST_0_PATH=/path/to/your/media/tv
      # - DEST_0_LABEL=TV Shows
      # - DEST_0_TYPE=tv
      # - DEST_1_PATH=/path/to/your/media/movies
      # - DEST_1_LABEL=Movies
      # - DEST_1_TYPE=movie
      # ── Trash ───────────────────────────────────────────────────────────────
      # - TRASH_FOLDER=/path/to/your/data/trash
    volumes:
      - /path/to/your/config:/config
      # Mount your source and destination folders — container-side paths must
      # match what you set in SOURCE_n_PATH / DEST_n_PATH above
      # - /path/to/your/data/completed:/path/to/your/data/completed
      # - /path/to/your/media/tv:/path/to/your/media/tv
      # - /path/to/your/media/movies:/path/to/your/media/movies
      # - /path/to/your/data/trash:/path/to/your/data/trash
```

> **Important:** The container-side path (right of the `:`) is what you enter in the Settings UI. They must match exactly.

### 3. Start

```bash
docker compose up -d
```

Open **http://your-server:8181** (or whatever port you set). `config.json`, `state.db`, and `user_prefs.json` are created automatically on first boot — no manual seeding needed.

---

## Maintenance

### Updating

```bash
docker compose pull downloads-managarr && docker compose up -d downloads-managarr
```

All state lives in the mounted `/config` directory and survives updates untouched.

### Building from source

If you prefer to build the image yourself, clone the repo and swap `image:` for `build: .` in your compose file:

```bash
git clone https://github.com/pdxgeek421/downloads-managarr.git /opt/downloads-managarr
cd /opt/downloads-managarr
```

```yaml
# image: ghcr.io/pdxgeek421/downloads-managarr:latest
build: .
```

To update from source:

```bash
cd /opt/downloads-managarr
git pull
docker compose down && docker compose build --no-cache && docker compose up -d
```

### Troubleshooting

**"Container name already in use"**

The old container wasn't started by this compose file (e.g. originally run with `docker run`), so `docker compose down` didn't remove it. Force-remove it manually:

```bash
docker rm -f downloads-managarr
docker compose up -d
```

**"Port already allocated"**

Something else on the host is bound to the same port (check with `docker ps -a | grep <port>`). Update `DOWNLOADS_MANAGARR_PORT` in your `.env` to a free port and restart:

```bash
docker compose up -d
```

---

## Environment Variables

### System

| Variable | Default | Description |
|---|---|---|
| `PUID` | `1000` | UID the container process runs as |
| `PGID` | `1000` | GID the container process runs as |
| `DOWNLOADS_MANAGARR_PORT` | `8080` | Host port to bind |
| `DL_MANAGARR_ADMIN_USERNAME` | *(unset)* | Login username — **leave unset to disable auth entirely** |
| `DL_MANAGARR_ADMIN_PASSWORD` | *(unset)* | Login password — **leave unset to disable auth entirely** |

### State File Paths

| Variable | Default | Description |
|---|---|---|
| `CONFIG_PATH` | `/config/config.json` | App configuration |
| `DB_PATH` | `/config/state.db` | SQLite database (queue + history) |
| `LOG_PATH` | `/config/app.log` | Rotating log file |
| `PREFS_PATH` | `/config/user_prefs.json` | Per-user UI preferences |

### Storage (Sources, Destinations, Trash)

Sources and destinations can be defined entirely via environment variables — no UI interaction needed. Entries are **0-indexed** and scanned in order; scanning stops at the first missing index. They appear in the Settings UI as read-only `ENV` badges alongside any folders you add manually.

Env-managed entries are always authoritative and are **never written to `config.json`** — they're injected at read time so changing an env var takes effect immediately on the next request.

**Sources** — where your downloads are:

| Variable | Required | Description |
|---|---|---|
| `SOURCE_n_PATH` | yes | Absolute container path to the source folder |
| `SOURCE_n_LABEL` | no | Display label (defaults to the folder's basename) |

**Destinations** — where files should go:

| Variable | Required | Description |
|---|---|---|
| `DEST_n_PATH` | yes | Absolute container path to the destination folder |
| `DEST_n_LABEL` | no | Display label (defaults to the folder's basename) |
| `DEST_n_TYPE` | no | Media type (`tv`, `movie`, `music`, `games`, …) — defaults to `tv` |

**Trash:**

| Variable | Description |
|---|---|
| `TRASH_FOLDER` | Absolute container path to the trash folder. When set, overrides whatever is configured in the Settings UI. |

**Example:**

```yaml
environment:
  - SOURCE_0_PATH=/data/completed
  - SOURCE_0_LABEL=Completed Downloads
  - SOURCE_1_PATH=/data/usenet/completed
  - SOURCE_1_LABEL=Usenet
  - SOURCE_2_PATH=/data/torrents/completed
  - SOURCE_2_LABEL=Torrents

  - DEST_0_PATH=/media/tv
  - DEST_0_LABEL=TV Shows
  - DEST_0_TYPE=tv
  - DEST_1_PATH=/media/movies
  - DEST_1_LABEL=Movies
  - DEST_1_TYPE=movie
  - DEST_2_PATH=/media/music
  - DEST_2_LABEL=Music
  - DEST_2_TYPE=music

  - TRASH_FOLDER=/data/trash
```

> **Remember:** every path listed here must also have a matching volume mount so the container can actually see it.

---

## Volume Mount Reference

| Host path | Container path | Purpose |
|---|---|---|
| `./config/` | `/config/` | Config + state directory (config.json, state.db, user_prefs.json, app.log) |
| `/data/completed` | `/data/completed` | Example source folder |
| `/media/tv` | `/media/tv` | Example TV destination |
| `/media/movies` | `/media/movies` | Example movies destination |
| `/data/trash` | `/data/trash` | Trash folder |

> You can mount source and destination folders at any path — the app doesn't care what they're called. Just make sure the container-side paths match what you configure in Settings.

---

## Stack & Dependencies

**Runtime:**
- Python 3.12
- [FastAPI](https://fastapi.tiangolo.com/) — API framework
- [Uvicorn](https://www.uvicorn.org/) — ASGI server
- [python-multipart](https://andrew-d.github.io/python-multipart/) — form parsing
- [aiosqlite](https://github.com/omnilib/aiosqlite) — async SQLite (queue + history persistence)

**Container:**
- `python:3.12-slim` base image
- `gosu` for UID/GID remapping at runtime (same pattern as linuxserver.io images)

**Frontend:**
- Zero dependencies — single `index.html` with vanilla JS and inline CSS
- No build step, no node_modules, no bundler

---

## Local Development (Without Docker)

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Create test folders
mkdir -p /tmp/test-downloads /tmp/test-media/tv /tmp/test-media/movies /tmp/test-trash

# Create a minimal config
mkdir -p config
cat > config/config.json <<'EOF'
{
  "sources": [{"label": "Downloads", "path": "/tmp/test-downloads"}],
  "destinations": [
    {"label": "TV Shows", "path": "/tmp/test-media/tv",     "dest_type": "tv"},
    {"label": "Movies",   "path": "/tmp/test-media/movies", "dest_type": "movie"}
  ],
  "trash_folder": "/tmp/test-trash"
}
EOF

CONFIG_PATH=./config/config.json DB_PATH=./config/state.db \
  uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
```

To test with auth enabled:

```bash
CONFIG_PATH=./config/config.json DB_PATH=./config/state.db \
  DL_MANAGARR_ADMIN_USERNAME=admin DL_MANAGARR_ADMIN_PASSWORD=admin \
  uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
```

---

## API Reference

All routes are prefixed with `/api`. When auth is enabled, all routes except `/api/auth/*` require a valid session cookie.

### Files

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/files` | List all items across configured source folders |
| `GET` | `/api/browse?path=…` | List subdirectories at a path (for the folder picker) |
| `GET` | `/api/ls?path=…` | List files and folders at a path with metadata |
| `GET` | `/api/size?path=…` | Recursively compute directory size (60s cache) |
| `GET` | `/api/extract/info?path=…` | Archive metadata + free-space check for extraction |
| `GET` | `/api/disk-stats` | Free/used/total bytes for all configured sources and destinations |

### Queue

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/queue` | Get current queue |
| `POST` | `/api/queue` | Replace entire queue |
| `DELETE` | `/api/queue` | Clear queue |

### Execution

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/execute` | Execute all queued items |
| `POST` | `/api/execute/next` | Execute next queue item (returns conflict info if blocked) |
| `POST` | `/api/execute/direct` | Execute actions immediately without touching the queue |
| `GET` | `/api/transfer/progress` | Current file-transfer progress (bytes transferred, total, speed in bytes/s, active flag) |

#### Conflict resolution (`/api/execute/next`)

```json
{
  "conflict_resolution": {
    "action_id": "<id of conflicting item>",
    "resolution": "skip | overwrite | rename"
  }
}
```

Response is either `{"status": "success", …}` or `{"status": "conflict", "conflict": {"action": {…}, "conflicting_path": "…"}}`.

### History

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/history?search=…` | Get action history (optional search filter) |
| `DELETE` | `/api/history` | Clear history (optional `exclude_ids` body to preserve entries) |
| `POST` | `/api/history/revert` | Revert a history entry by ID (falls back to path data if record pruned) |

### Trash

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/trash` | List items in the trash folder |
| `POST` | `/api/trash/restore` | Restore an item from trash to a destination |
| `DELETE` | `/api/trash/item` | Permanently delete a single trash item |
| `DELETE` | `/api/trash` | Empty the entire trash folder |

### Config & Preferences

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/config` | Get app configuration |
| `POST` | `/api/config` | Save app configuration |
| `GET` | `/api/prefs` | Get UI preferences for the current user |
| `PUT` | `/api/prefs` | Save UI preferences for the current user |

### Auth

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/auth/status` | Check if auth is required and if the current session is valid |
| `POST` | `/api/auth/login` | Log in (body: `{"username": "…", "password": "…"}`) |
| `POST` | `/api/auth/logout` | Log out (clears session cookie) |

---

## Project Structure

```
downloads-managarr/
├── app/
│   ├── main.py               # FastAPI app, lifespan, auth middleware, router registration
│   ├── db.py                 # SQLite setup (WAL mode, schema, JSON migration)
│   ├── static/
│   │   └── index.html        # Entire frontend — single file, no build step
│   ├── routes/
│   │   ├── auth.py           # Session auth (login, logout, status)
│   │   ├── config.py         # App config CRUD + env var injection
│   │   ├── executor.py       # Queue execution and history revert endpoints
│   │   ├── files.py          # File listing and directory browsing
│   │   ├── history.py        # History log backed by SQLite
│   │   ├── prefs.py          # Per-user UI preferences
│   │   ├── queue.py          # Queue CRUD backed by SQLite
│   │   └── trash.py          # Trash operations
│   └── services/
│       ├── executor.py       # Synchronous file operation logic (move, copy, delete, wrap, restore)
│       └── extractor.py      # Archive detection, inspection, and extraction (zip / tar family / gz / bz2)
├── Dockerfile
├── docker-compose.yml
├── entrypoint.sh             # UID/GID remapping + uvicorn launch
├── requirements.txt
└── config/
    ├── config.json           # Volume-mounted app config (gitignored)
    ├── state.db              # SQLite database — auto-created (gitignored)
    └── user_prefs.json       # Per-user preferences — auto-created (gitignored)
```

---

## Notes

- **State is SQLite + JSON.** The action queue and history live in a single SQLite file (`state.db`) using WAL journal mode — crash-safe, fast, and trivially inspectable with any SQLite browser. Configuration (`config.json`) and user preferences (`user_prefs.json`) stay as plain JSON since they're small, rarely change, and easy to edit by hand. On first boot after upgrading from the old JSON-based queue/history, the app auto-migrates any existing `queue.json` / `history.json` into SQLite — no manual steps needed.
- **Env vars are not stored.** `SOURCE_n_*`, `DEST_n_*`, and `TRASH_FOLDER` are injected at runtime and never written to `config.json`. Remove an env var and the entry disappears on the next request — no stale config to clean up.
- **Sessions are in-memory.** Restarting the container clears all active sessions. Users will need to log in again after a restart.
- **The frontend is one file.** `index.html` contains all HTML, CSS, and JavaScript inline. No framework, no node_modules, no build step. Open it in a text editor and you can read the whole thing.
- **File operations are atomic.** All transfers use a write-to-`.managarr.tmp`-then-rename strategy. The destination is never touched until the data is fully written. If the container dies mid-transfer, a clearly-named `.managarr.tmp` leftover is the only trace — the destination is clean and the source is intact. Same-filesystem moves skip the temp file and use a direct `os.rename()` (a single kernel call).
- **Paths are container-internal.** The app only knows about paths inside the container. If you tell it `/media/tv`, that has to be a real path inside the container — hence the volume mounts.
