# Changelog

All notable changes to Downloads-Managarr are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

---

## [Unreleased]

---

## [1.3.3] - 2026-03-21 — Queue Header Tweaks

### Added
- **Floating mode toggle (⧉) in queue header** — one-click toggle to switch the queue between docked sidebar and floating overlay mode. Button highlights in accent colour when floating is active. Syncs with the Settings → Behavior checkbox.

### Changed
- **"Clear Queue" → "Clear"** — button label shortened; the context is obvious from its position in the queue header.

---

## [1.3.2] - 2026-03-21 — Login Polish & Desktop Floating Queue

### Added
- **Settings → Behavior → Floating queue panel (desktop)** — when enabled, the queue slides in as a fixed overlay on desktop (identical to mobile behaviour). The ☰ button opens and closes it; the backdrop and Escape key dismiss it. Off by default, preserving the existing sidebar behaviour.

### Fixed
- **Login form — no placeholder text** — removed the `admin` username placeholder and `••••••••` password placeholder. Fields are now blank, which is cleaner and avoids implying fixed credentials.
- **Login password field styling** — `input[type="password"]` now inherits the same dark-surface background, border, and focus styling as text inputs. Browser autofill no longer overrides the field background with white (suppressed via `-webkit-autofill` box-shadow trick).

---

## [1.3.1] - 2026-03-21 — Mobile & UI Polish

### Fixed
- **Mobile action bar fully visible** — Sources & Destinations now auto-collapses on mobile (≤480 px) when you select a file, freeing the vertical space needed for all three action buttons (Add to Queue, Run Now, Clear). It restores to your saved preference when the selection is cleared.
- **Sticky sort header transparent when scrolling** — column header row now has `z-index: 1` so it stays fully opaque when scrolling past dimmed/unknown rows.
- **Modified column right edge clipping** — added 10 px right padding to both the Modified header cell and its data cells so the timestamp is never flush against the edge of the window.

---

## [1.3.0] - 2026-03-21 — Queue Toggle, Live Transfer Progress & Toolbar Polish

### Added
- **Desktop queue toggle** — the ☰ queue button is now always visible in the header on all screen sizes. On desktop it collapses and expands the queue sidebar (state saved in `localStorage`); on mobile it keeps the existing slide-in overlay behaviour. Previously the button was hidden on desktop entirely.
- **Real-time transfer progress** — while a file is being copied or moved across filesystems, the progress modal now shows a live mini progress bar, bytes transferred / total, and current transfer speed (MB/s). The backend streams progress through a new `GET /api/transfer/progress` endpoint polled every 400 ms by the frontend. Same-filesystem moves (`os.rename`) are instant and show no byte-level progress. Directory copies show per-file progress with aggregate bytes.
- **Settings → Behavior → File Browser** — new section with a "Show Sources & Destinations by default" toggle. Controls whether the collapsible Sources & Destinations bar is expanded or collapsed when the page loads. Saved server-side with the rest of user preferences so it roams across browsers.

### Changed
- **Toolbar layout — Sources & Destinations moved below controls** — the All / Files / Folders filter buttons and search input row is now the first row in the toolbar (always visible). The collapsible Sources & Destinations toggle bar sits below it, with the expandable filter buttons beneath that. This puts the most-used controls at the top.
- **Sources & Destinations toggle styling** — toggle bar is now left-aligned, taller (8 px vertical padding), larger text (12 px), and has a visible top and bottom border to clearly separate it from the rows above and below.

### Fixed
- **Mobile action bar buttons clipped** — on small screens the "Add to Queue", "Run Now", and "Clear" buttons were cut off below the viewport. Fixed by adding `min-height: 0` to the file list container so it can shrink and give the action bar the space it needs. On ≤480 px screens the action preview text is hidden and the buttons row stays on a single non-wrapping line so all three buttons are always reachable.
- **Browser caching of `index.html`** — added `Cache-Control: no-cache` to the index route so browsers always revalidate after an update. Previously, users had to hard-refresh to pick up a new frontend after rebuilding the container.

---

## [1.2.0] - 2026-03-20 — Auto Trash & Settings Cleanup

### Changed
- **Toggle unrecognized files** — the ❓ filter-bar button was renamed from "Hide Unknown" to "Toggle unrecognized files". Logic is now inverted: toggled **on** shows unrecognized files, toggled **off** hides them. Default is **on** (shown). The matching Settings checkbox was moved from Behavior to **Appearance → File List** and is labelled "Show unrecognized files (❓ Unknown)".
- **Settings → Behavior: Queue Defaults** — the "File Defaults" and "Folder Defaults" sections were merged into a single **Queue Defaults** section; the File Browser subsection was removed from Behavior entirely (its "Show Unknown" toggle moved to Appearance).
- **Settings → Housekeeping: Destination Free Space + Storage Color merged** — the separate "Storage Availability Color" section was folded into the "Destination Free Space" section under a divider, reducing visual clutter.
- **Trash mode "Disabled" renamed to "Off"** — the radio option in Settings → Housekeeping now reads "Off" instead of "Disabled" for brevity.
- **Color picker CSS classes extracted** — inline color-picker styles replaced with shared CSS classes (`.cp-row`, `.cp-picker`, `.cp-picker-lg`, `.cp-hex`, `.cp-hex-lg`, `.cp-label`) to keep markup clean.

### Fixed
- **Auto trash mode fully functional** — `trash.py` was missing all auto-mode support: listing, deleting individual items, and emptying the trash now correctly scan `.Trash` folders co-located with source files. The scan covers the source root and one level of immediate subdirectories. Path validation for `DELETE /api/trash/item` in auto mode checks that the item lives inside a `.Trash` folder that itself sits within a configured source directory.
- **Revert-of-restore in auto mode** — the history revert handler now resolves the correct `.Trash` path when reverting a restore that originated from an auto-trash operation.
- **Sources/Destinations separator spacing symmetric** — separator used custom left/right margins that caused unequal padding on desktop and opposite issues on mobile. Now relies solely on the flex container's `gap` property (`margin: 0` on the separator) so spacing is identical on both sides on all viewports.
- **Trash and mobile queue button emoji size** — added `font-size: 16px` to both buttons so the emoji renders at the same scale as other icon buttons after the button-padding reduction in v1.1.0.

---

## [1.1.0] - 2026-03-20 — UX Polish & Mobile Improvements

### Added
- **Source filter buttons in toolbar** — toolbar row 1 shows per-source buttons (with free-space labels) alongside destination buttons, each with "Sources" / "Destinations" section labels. Clicking a source button filters the file list to that source only.
- **Collapsible Sources & Destinations bar** — a click-to-toggle bar sits between the header and the sources/destinations row; state persists across sessions via `localStorage`.
- **Storage availability color settings** — new Appearance section to color free-space labels by a 4-level meter (plenty ≥50% green, medium 20–50% yellow, low 10–20% orange, warning <10% red) or a single static color (Accent or Custom hex); all thresholds individually customizable.
- **Trash mode selection** — Settings → Behavior now offers three trash modes: **Disabled** (no trash action), **Auto** (creates a `.Trash` folder beside the file at execute time — default), and **Custom** (explicit configured path). The auto mode requires no pre-configuration and keeps trash alongside its source.
- **Hide Unknown file type toggle** — ❓ button in the filter bar hides unrecognized files from the list; also available as a checkbox in Settings → Behavior.
- **Assign Unknown type to any file/folder** — the Unknown option now appears in the media-type dropdown for all rows, not just already-unknown files. Useful for correcting mis-detected items.
- **Confirmation dialogs for destructive settings actions** — removing a source folder, destination folder, or entire media type section now prompts for confirmation. A "Don't ask again" pref suppresses future prompts.
- **Clear Queue / Clear History confirmations** — both buttons now show a confirmation modal with a "Don't ask again" checkbox; the choice is saved per user.
- **Favicon** — browser tab/bookmark now shows the ⬇ logo icon on a purple background.
- **Empty folder offer in confirm dialog** — execution confirmation now shows a "Delete source folder(s) if empty after move" checkbox (pre-checked from Behavior default) with a link to make it permanent.
- **Trash → Sources tip** — trash modal shows a one-time callout suggesting you add the trash folder as a source for in-app browsing.
- **/dev/shm recommendation** — Extract Temp Folder in Housekeeping settings includes a one-click "Use /dev/shm →" link for shared-memory extraction.

### Changed
- **Toolbar layout** — All / Files / Folders filter buttons moved to the LEFT of the filter search input; filter input widens to fill available space; left-aligned with the Name column.
- **Column padding** — Source / Type / Size / Modified column padding reduced to 6 px to reclaim horizontal space.
- **Column alignment** — Source, Type, Size, and Modified columns right-justified.
- **Refresh icon** — enlarged to 1.9 em (32×32 px squared, lighter weight, larger fill); button size unchanged.
- **Header dropdown icons** — ⚙ / ? / ⏏ icons standardized to 16 px / 20 px container.
- **Media Types settings UI** — type-tag pills row removed; each destination section header carries its own × remove button and inline icon editor. Suggestion tooltip moved next to the Add button.
- **Button padding** — internal horizontal padding reduced by 6 px across all buttons.
- **Trash button** — icon-only (trash can emoji, no text label) to save toolbar space.
- **Clear buttons renamed** — "Clear" → "Clear Queue" and "Clear History" for clarity.
- **Library settings** — Name field narrowed to 40 px (flex-none); location path field expands to fill remaining row width; rows are single-line on mobile (no wrapping).
- **Static color mode** — Accent / Custom radio sub-options; selecting Accent uses `var(--accent)` so the label always matches the theme.

### Fixed
- **Complete Series misdetected as movie** — `TV_COMPLETE_RE` pattern catches "COMPLETE SERIES / SEASON / PACK / SHOW / BOX SET / FULL SERIES" and blocks the movie fallthrough.
- **.nfs\* files preventing source folder removal** — executor now detects NFS open-file placeholders after a cross-filesystem move, logs at INFO, and surfaces a human-readable message instead of a spurious warning.
- **Sources/Destinations separator full height** — vertical divider now stretches to match the full height of the row instead of a fixed 1.5 em.
- **Mobile sources/destinations natural sizing** — sources and destinations sections size to content instead of splitting 50/50.
- **Mobile free-space labels restored** — free-space sub-labels on source/destination filter buttons were incorrectly hidden on mobile; now shown again.
- **Rename applies to wrap folder** — when Rename is active and Place in subfolder is checked, the action preview and the created folder both use the renamed filename as the folder stem, not the original.
- **Mixed type block ignores Delete/Extract** — switching the action to Delete or Extract now immediately clears any stale mixed-type warning and re-enables the queue/run buttons; the block only applies to Move and Copy.
- **Warning tooltip off-screen on mobile** — the ⚠ tooltip in the action bar now uses `position: fixed` on mobile, spans the screen width with 10 px margins, and is positioned dynamically above the action bar. On mobile it requires a tap to open (hover is suppressed); tapping anywhere else closes it.

---

## [1.0.1] - 2026-03-19 — Auth env var rename

### Changed
- Renamed `ADMIN_USERNAME` → `DL_MANAGARR_ADMIN_USERNAME` and `ADMIN_PASSWORD` → `DL_MANAGARR_ADMIN_PASSWORD` to avoid collisions in a shared `.env` used by multiple services (Sonarr, Radarr, etc.)

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
- Optional login screen shown on load when `DL_MANAGARR_ADMIN_USERNAME` / `DL_MANAGARR_ADMIN_PASSWORD` env vars are set.
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
