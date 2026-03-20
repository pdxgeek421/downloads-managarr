# Changelog

All notable changes to Downloads-Managarr are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

---

## [1.0.0] - 2026-03-19 — First Public Release

### Fixed

#### UI
- **Empty subfolder navigation** — navigating into an empty subfolder hid the `..` back-row because the empty-state check ran before the row was appended. The `..` row is now rendered unconditionally whenever inside a subfolder, then the empty-state message is shown if no files remain.
- **Empty-state message context** — the "No files found" message now reads *"This folder is empty."* when browsing a subfolder, and *"No files found. Configure source folders in Settings."* only at the source root.
- **Custom-path input always visible** — `ab-custom-wrap` had `style="display:none; display:flex"` — the second declaration overrode the first, keeping the custom path input always visible regardless of the selected destination. Duplicate attribute removed.

#### Bugs
- **`atomic_move` error masking** — `os.rename()` failures were caught with a bare `except OSError`, causing non-EXDEV errors (e.g. permission denied) to silently fall through to the copy path and produce confusing downstream errors. Now only `errno.EXDEV` (cross-device) is caught; all other `OSError` subtypes propagate immediately with their original message.
- **Trash restore not atomic** — `POST /api/trash/restore` used `shutil.move()` instead of `atomic_move()`, leaving partial destination files if the process was interrupted on a cross-filesystem restore. Now uses the same atomic copy-then-rename strategy as all other transfers.
- **History ID collision on retry** — history entries reused the source action's ID, so retrying a failed action would silently overwrite the failure record with a success entry. History entries now always receive a fresh `secrets.token_hex(8)` ID independent of the action ID.
- **Partial unwrap state invisible** — when an unwrap-folder operation hit a conflict mid-loop, `ConflictError` carried no information about how many children had already been moved. `ConflictError` now includes a `moved_count` field; conflict API responses expose it as `moved_before_conflict` so callers have full visibility.
- **Trash delete accepts any path** — `DELETE /api/trash/item` accepted any filesystem path with no validation. Now rejects requests whose path does not start with the configured trash folder.
- **Trash scan crashes on permission errors** — the recursive size walk for trash directories would propagate `PermissionError` for unreadable subdirectories. Individual file stat errors are now caught and skipped.

#### Security
- **Filesystem exposure via `/api/ls`, `/api/size`, `/api/extract/info`** — these endpoints accepted any absolute path, allowing arbitrary filesystem enumeration when auth is disabled. All three now validate the requested path against configured sources, destinations, and trash folder; requests outside those roots return a 400-style error response.
- **History LIKE search metacharacter injection** — the `search` parameter was interpolated directly into a SQLite `LIKE` pattern, so `%` matched everything and `_` matched any single character. The pattern is now escaped (`%` → `\%`, `_` → `\_`, `\` → `\\`) with `ESCAPE '\\'` in the query.
- **Session store unbounded growth** — expired sessions were only evicted when the exact token was presented again. A `_prune_sessions()` helper now removes all expired entries on each successful login.

### Changed

#### Performance
- **`GET /api/disk-stats` now async** — `shutil.disk_usage()` calls were previously executed synchronously on the event loop. All stat calls are now dispatched concurrently via `asyncio.gather + asyncio.to_thread`, preventing NFS/SMB mounts from stalling request handling.
- **`get_config()` cached** — every request previously opened and JSON-parsed `config.json` from disk. Results are now cached for 5 seconds (invalidated immediately on `POST /api/config`) eliminating per-request I/O.

#### History API
- `GET /api/history` now accepts `limit` (default 200, max 5000) and `offset` query parameters, matching the pagination pattern already used by `GET /api/files`. Prevents unbounded responses when `history_days=-1`.

#### Code quality
- `_validate_action_paths()` in `routes/executor.py` extracted into three reusable helpers (`_allowed_source_paths`, `_allowed_dest_paths`, `_in_allowed`) — eliminates three near-identical list comprehensions.
- `execute_queue` and `execute_next` now correctly typed as `Optional[ExecuteRequest]` instead of bare `= None`.
- `type_icons` field in `AppConfig` typed as `Dict[str, str]` instead of bare `dict`.
- `routes/prefs.py` no longer imports `QUEUE_PATH` — `PREFS_PATH` defaults directly to `/config/user_prefs.json`.
- `GET /health` now runs a `SELECT 1` against the database and returns HTTP 503 if the connection is broken, making it meaningful for container health checks.
- Schema versioning in `db.py` is now fully wired: the stored version is read on startup and each migration block runs exactly once, with a clear template for adding future schema versions.
- `auth_routes` import in `main.py` moved to the top of the file alongside other route imports (no functional dependency on late import).
- Removed unused `aiofiles` dependency from `requirements.txt`.

---

## [0.11.0] - 2026-03-19 — Archive Extraction

### Added

#### Archive Extraction
- New **Extract** action in the action bar — select one or more archives and queue or run-now an extraction.
- Supports: `.zip`, `.tar`, `.tar.gz` / `.tgz`, `.tar.bz2` / `.tbz2`, `.tar.xz` / `.txz`, standalone `.gz`, `.bz2`.
- **Destination options:** extract in-place (same folder as the archive), any configured destination, or a custom path.
- **Strip root folder** checkbox — if the archive contains a single top-level directory, strip it so contents land directly in the destination rather than nested one level deeper.
- **Rename on extract** — optional rename field to give the extracted folder/file a different name.
- **Extract Temp Folder** setting (Settings → Housekeeping) — extractions are staged in a `.managarr.extract.tmp` directory inside the temp folder before being moved to the final destination, preventing partial content from appearing in media libraries mid-extraction.
- Space check: before extracting, the API reports the estimated uncompressed size versus free space on the temp/destination volume. If space is tight a warning is shown in the UI with the option to pick a different destination.
- `GET /api/extract/info?path=…` — returns archive metadata (format, member count, estimated uncompressed size) and remaining free space on the configured temp folder.
- `app/services/extractor.py` — new module handling archive detection, inspection, and extraction with path-traversal guards (zip `normpath` check; tar `isabs`/`..` filter).

#### Destination Free-Space Indicator
- Accent-coloured free-space sub-label displayed on each **content-type filter button** (📺 TV, 🎬 Movie, etc.) in the toolbar, showing available space on the first configured destination of that type.
- Free-space figure also shown inline next to the path on every **source** and **destination** row in Settings → Library.
- Three display formats selectable in Settings → Appearance → **Destination Free Space**: *Space free* (e.g. `760G free`), *% full* (e.g. `18% full`), or *Both* (e.g. `760G free · 18% full`).
- On/off toggle in the same settings section to hide the labels entirely.
- `GET /api/disk-stats` — returns free/used/total bytes for every configured source and destination; uses an ancestor-path fallback so Docker volume mount points that haven't been written to yet still return meaningful figures.

### Changed

#### File-List Toolbar — Two-Row Layout
- The toolbar above the file list is now split into two rows:
  - **Top row** — file-type filter buttons (All / Files / Folders) and content-type filter buttons (TV / Movie / etc.).
  - **Bottom row** — text filter input, spacer, item count, and refresh button.
- Reduces horizontal crowding, especially on narrower viewports.

#### Settings — Housekeeping section
- Added **Extract Temp Folder** path field with Browse and Clear buttons.
- Supports `EXTRACT_TEMP_FOLDER` env var; shows as a read-only ENV badge when set via environment.

### Fixed
- `shutil.disk_usage()` would raise `OSError` for configured paths that don't exist yet (e.g. a Docker volume not yet populated). Fixed by walking up the path hierarchy to the nearest existing ancestor before calling `disk_usage`.

---

## [0.10.0] — Mobile Responsive Design

### Added
- Full mobile layout — queue panel slides in as a fixed overlay from the right, toggled via a ☰ button in the header.
- Tap the backdrop or press Escape to dismiss the queue panel on mobile.
- ☰ button shows live queue item count when items are queued.
- Modals slide up from the bottom as bottom sheets on small screens.
- Settings nav collapses from a left sidebar to a horizontal scrollable tab bar.
- Table columns reduce on smaller screens (Source/Modified hidden at 768px; Type/Size hidden at 480px).
- Filter input expands to fill available toolbar width on mobile.

---

## [0.9.2] — Text Size Setting

### Added
- Text Size control in Settings → Appearance: Small (12px), Medium (14px), Large (16px).
- Applied instantly without a page reload; saved per user alongside theme and accent preferences.
- Base font-size stored as a CSS custom property — consistent across all themes.

---

## [0.9.1] — Per-User Preferences

### Added
- Theme, accent colour, custom theme colours, and panel width saved server-side per user in `user_prefs.json`.
- Preferences persist across browsers, devices, and sessions.
- When auth is disabled, preferences stored under a shared `default` key and roam server-wide.
- `localStorage` used as a fast-paint cache so the UI renders instantly with the correct theme before the server responds.

---

## [0.9.0] — Authentication

### Added
- Optional login screen shown on load when `ADMIN_USERNAME` / `ADMIN_PASSWORD` env vars are set.
- Session-based auth with an `httponly` cookie; all `/api/*` routes protected when auth is enabled.
- *Keep me logged in* → 30-day persistent cookie; unchecked → browser-session cookie (24h server-side cap).
- Expired or invalid session re-shows the login screen automatically.
- Logout button in the header (only visible when auth is enabled).
- Fully opt-in — omit the env vars to run without any login screen.

---

## [0.8.3] — Lock Auto-Refresh

### Fixed
- Lock badge now clears immediately when a queue item is removed via ✕ or Clear Queue — no manual refresh needed.

---

## [0.8.2] — History & Trash UX

### Changed
- History revert button renamed from "↩ Undo" to "↩ Restore".
- "Restore" action entries in history no longer show a redundant Restore button.
- Trash item delete now shows an inline "Permanently delete?" confirmation instead of a browser dialog.

### Fixed
- Fixed "History item not found" error — backend now falls back to path data if the history record has been pruned by retention policy or a clear.

---

## [0.8.1] — Changelog & Version Tag

### Added
- Version badge displayed next to the logo in the header.
- Click the version badge to open the in-app changelog modal.

---

## [0.8.0] — Trash & History Improvements

### Added
- In-trash history entries survive "Clear History" — locked until restored or permanently deleted.
- 🔒 lock badge and amber left border on history entries for items still in the trash folder.
- Restore button only shown when the file is actually still in trash (real-time cross-reference).
- Amber-styled Restore button for in-trash history items.
- Trash item count badge on the 🗑 Trash header button.

---

## [0.7.0] — Custom Type Icons

### Added
- Emoji icon picker for each media type in Settings → Library.
- Click a type's emoji tag to edit it inline; set an icon when adding a new type.
- Custom icons appear everywhere: filter buttons, type dropdowns, destination sections, history labels.
- Icons persisted to backend config.

---

## [0.6.0] — Help System

### Added
- Help button (?) in the header between Trash and Settings.
- Help modal with 5 tabs: Overview, File Browser, Actions, Queue, Settings.

---

## [0.5.0] — Sort & Type Assignment

### Added
- Type column is now sortable alongside Name, Source, Size, and Modified.
- Unknown types show a full dropdown to manually assign a type.
- "⚙ Add Type" at the bottom of every type dropdown links to Settings → Library.
- Manually assigned types enable the checkbox and allow queuing.

---

## [0.4.1] — Navigation Polish

### Fixed
- Lock tooltip no longer inherits row opacity (was too transparent to read).
- Updated lock message: clarifies you can navigate inside a locked folder and how to unlock it.

---

## [0.4.0] — Folder Navigation

### Added
- Click any folder name to navigate inside it.
- Breadcrumb bar with clickable ancestor links at the top of the file list.
- `..` row at the top of the list to go up one level.
- Queue-locked folders: 🔒 badge when a queued action targets the folder or anything inside it.
- Refresh always returns to the source root view.
- New `GET /api/ls` backend endpoint for in-app directory listing.

---

## [0.3.1] — Detection Polish

### Changed
- Unknown type rows: greyed out with checkbox disabled and a link to Settings → Library.
- Larger refresh icon; filter and media type buttons unified to the same size.
- Mixed Type Safety defaults to enabled.

### Fixed
- Fixed "Tv" displaying instead of "TV".

---

## [0.3.0] — Media Type Detection

### Added
- Auto-detection for Movies, Music, and Games from filenames and folder names.
- Mixed Type Safety: block queuing when different media types are selected together.
- Filter buttons are now dynamic, generated from configured media types.

---

## [0.2.0] — Themes & Appearance

### Added
- Light, OLED (pure black), and Custom themes alongside the default Dark theme.
- Accent colour picker: Purple, Blue, Green, Amber, or custom hex.
- Custom theme builder — set your own background, surface, and text colours.
- All theme and accent preferences saved per browser.

---

## [0.1.0] — Initial Release

### Added
- File browser with configurable source folders.
- Move, Copy, and Delete actions (Trash or Permanent).
- Add to Queue, Run Now, and Run Queue.
- Action history with revert support.
- Settings: Sources, Destinations, Trash folder, History retention.
- TV episode auto-detection from filenames.
- Dark theme.
