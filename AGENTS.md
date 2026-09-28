# Agent Guidelines — Home Voice Assistant

The complete technical reference for anyone (human or AI agent) working on this
project. Read this before changing anything. Keep it updated as the system
evolves.

---

## 1. System at a glance

- **Backend**: Raspberry Pi 3 B+ (1 GB RAM), DietPi / Debian 12 (arm64), FastAPI.
  Always on. Code lives at `/opt/home-voice-assistant`, runs via systemd
  (`home-voice-assistant`, auto-restart).
- **iOS app**: SwiftUI (iPhone 16, iOS 27). Built on the Mac, installed over USB.
- **Mac (laptop)**: runs **Jellyfin** (metadata only) and mounts the Pi's drive
  over SMB (now via Tailscale). Not required for streaming/downloading.
- **Networking**: everything talks over **Tailscale** — works from anywhere,
  no port-forwarding.

### Hardware / IPs

| Device | LAN IP | Tailscale IP | Notes |
|---|---|---|---|
| Pi (backend) | 192.168.8.147 (eth0) | 100.92.219.95 (`dietpi`) | SSH as `root` (password not stored in git — see deploy §) |
| Mac | varies (192.168.8.x / 192.168.0.x) | 100.95.105.68 | runs Jellyfin :8096 |
| iPhone | — | 100.73.186.123 | app installed via devicectl |
| Android TV (Kodi) | 192.168.8.137 | — | TCP JSON-RPC :9090 |
| Ventilation (SaveConnect) | 192.168.8.146 | — | HTTP `/mread`, `/mwrite` |

### ⚠️ Two networks (double NAT)

The house has **two** routers:
- **Huawei** `192.168.8.1` — the ISP/main router; Pi/TV/ventilation are wired to it.
- **TP-Link** `192.168.0.1` — a second router; Mac/iPhone connect to *its* Wi-Fi.

The two subnets can't talk directly. **The permanent fix is putting the TP-Link
in "Access Point" mode** (or connecting everything to the Huawei's Wi-Fi). Until
then, always reach the Pi via its **Tailscale IP** (`100.92.219.95`), never the
LAN IP, because the Mac may be on the wrong subnet.

---

## 2. Services (Pi, systemd)

| Service | Port | Data dir | Purpose |
|---|---|---|---|
| `home-voice-assistant` | 8000 | `/opt/home-voice-assistant` | the FastAPI backend |
| `radarr` | 7878 | `/var/lib/radarr` | movie manager (Letterboxd → download) |
| `prowlarr` | 9696 | `/var/lib/prowlarr` | torrent indexers (YTS + The Pirate Bay) |
| `transmission-daemon` | 9091 | `/etc/transmission-daemon/settings.json` | downloads (no RPC auth) |

Check/restart: `systemctl status|restart <service>`. All four auto-start on boot.

### Mac-side
- **Jellyfin 12.0.0** on :8096 — libraries `Movies` (filmid), `TV Shows` (serials),
  `Multikad` (cartoons). Reads the Pi's files through the SMB mount `~/PiMedia`.
- **SMB mount** `~/PiMedia` → Pi `/mnt/ketas` (guest share `Movies`). Auto-remount
  via launchd agent `~/Library/LaunchAgents/com.mattiasdaum.pimedia.plist`
  (tries `100.92.219.95` first, then `192.168.8.147`).

---

## 3. Media storage (`/mnt/ketas`)

```
filmid/       movies  (category folders + "Movie (Year)" folders)
serials/      TV shows (normalized to "Show (Year)/Season N/episodes")
multikad/     cartoons (Estonian children's films)
downloads/    Transmission download target
```

- Drive is **NTFS** (≈1 TB). Has some filesystem corruption (see Known issues).
- The Pi serves files directly: `GET /api/media/stream?path=<path>` with single
  byte-range support (including suffix ranges, 416 for unsatisfiable ranges).
  It auto-transcodes **DTS/TrueHD/FLAC/etc. → AAC** (ffmpeg, video copied)
  so iPhones can play them. In-app unsupported-audio playback uses HLS;
  offline downloads use a progressive remux.

### Codec rules (important!)
- **The TV can't decode 10-bit HEVC/HDR/AV1** — only H.264/x264 plays.
- **The iPhone plays H.264, HEVC, and 10-bit/HDR fine**, but **not DTS audio**
  (handled by auto-transcode) and **not XviD/`.avi`** (old SD files).
- Radarr has a custom-format rule: x264 +10, x265/10-bit/HDR/AV1 −10000, min score 0.
  This keeps auto-downloads TV-playable.

---

## 4. Backend

### Layout
```
app/main.py            FastAPI routes + background watchers
app/config.py          all config, read once from .env
app/db.py              SQLite helpers (canonical fridge items, recipes, shopping, history, receipts…)
app/llm.py             DeepSeek (OpenAI-compatible) client + tool loop
app/prompts.py         system prompt (answers in Estonian)
app/speech.py          server-side STT (Groq, optional)
app/letterboxd.py      Letterboxd watchlist → Radarr sync
app/tools/*.py         the tool implementations
app/tools/registry.py  tool registry (TOOLS dict) — name, schema, handler
app/tools/__init__.py  lazy facade over the registry — importing a leaf module
                       (e.g. app.tools.base) stays cheap; the registry and its heavy
                       integrations load on first TOOLS/get_schemas/run_tool use
```

### Config highlights (`.env`, on the Pi — git-ignored)
```
LLM_PROVIDER=openai   LLM_MODEL=deepseek-chat   LLM_BASE_URL=https://api.deepseek.com/v1
OPENAI_API_KEY=…      (DeepSeek key)
JELLYFIN_URL=http://100.95.105.68:8096   (Mac's Tailscale IP)
JELLYFIN_API_KEY=…    JELLYFIN_SMB_PREFIX=/Users/mattiasdaum/PiMedia
RADARR_URL=http://localhost:7878   RADARR_API_KEY=…
LETTERBOXD_USER=daum13
FS_ROOT=/mnt/ketas
TRANSMISSION_URL=http://localhost:9091
HON_USER/HON_PASS, SMARTTHINGS_PAT, SAVECONNECT_URL=http://192.168.8.146, …
```

### HTTP API (all under the Pi's :8000)
| Endpoint | Method | Purpose |
|---|---|---|
| `/api/health` | GET | liveness → `{"ok":true}` |
| `/api/tools` | GET | list tool names + descriptions |
| `/api/tools/{name}` | POST | run a tool: body `{"args":{…}}` → `{"ok":bool,"data":…,"error":…}` |
| `/api/chat` | POST | LLM chat: `{"text"}` → `{"reply"}` (recent turns loaded from SQLite; English default) |
| `/api/stt` | POST | multipart audio → `{"text"}` (optional Groq STT) |
| `/api/receipts/import` | POST | multipart PDF → parsed receipt |
| `/api/log` | POST | receive an error line from the app → `{"message"}` |
| `/api/jellyfin/image/{item_id}` | GET | proxied poster (disk-cached 7 days) |
| `/api/media/stream?path=` | GET | stream a movie/episode (Range + DTS→AAC transcode) |
| `/api/media/subtitles?path=` | GET | `.srt` → WebVTT (Estonian preferred) |

### Tools (≈60, grouped)
- **Media**: `jellyfin_status/search/recent/resume/library/item_detail/delete/refresh/stream_url/download_url/episodes`, `local_movies`
- **Downloads**: `list_torrents`, `add_torrent`, `torrent_status/remove/pause/resume/delete`, `search_torrents`, `disk_usage`
- **Devices**: `washer_status/start/stop/pause`, `fridge_status/set_temp`, `ventilation_status/set/set_temp`, `kodi_*`
- **Home**: `weather_now/forecast`, `electricity_price`, `shopping_add/list/remove/clear`
- **Food**: `inventory_*`, `fridge_inventory_*`, `lookup_barcode`, `add_barcode_item`, `suggest_recipes`, `recipe_*`, `import_recipe(_text)`, `update_recipe`, `saved_recipes`
- **Files/receipts/spending**: `list_files/read_file/search_files`, `import_receipts`, `check_email_receipts`, `spending_stats`, `price_trend`
- **Automation**: `sync_letterboxd`

### Background watchers (in `main.py` lifespan)
- receipts: poll `data/receipts/` every 30 s (+ email every 4th tick)
- `_letterboxd_watcher`: Letterboxd → Radarr every 30 min (only when Radarr is configured)
- `_jellyfin_refresh_watcher`: Jellyfin rescan every 10 min (only when Jellyfin is configured)
- warm-up: hOn tokens + fridge + weather on boot

### Deploy backend (from the Mac, works via Tailscale)
```bash
cd ~/Desktop/projektid/home-voice-assistant
rsync -avz -e "sshpass -p \"$PI_SSH_PASS\" ssh -o StrictHostKeyChecking=no" \
  app/ root@100.92.219.95:/opt/home-voice-assistant/app/
sshpass -p "$PI_SSH_PASS" ssh root@100.92.219.95 systemctl restart home-voice-assistant
```
`$PI_SSH_PASS` = the Pi's root password (ask the owner; it's **not** committed).
**Gotcha**: `app/` files belong in `/opt/home-voice-assistant/app/`, but files from
`app/tools/` must be rsync'd to `.../app/tools/` (mind the nested path).

---

## 5. iOS app

### Targets & signing
- `Home` (app), `HomeWidget` (weather + electricity widgets + live activity),
  `ReceiptShare` (share extension for Coop receipts).
- `Packages/HomeCore` — local SwiftPM package with pure logic and models
  (`ResumeDecision`, fridge inventory) plus its tests. Runs via
  `swift test --package-path ios/Packages/HomeCore` on macOS in seconds, no
  simulator. Put new testable logic here, not in the app target.
- Bundle `com.mattiasdaum.home`, team `C57GFXX5X5`, iOS 26 deployment target.
- Project is **generated by XcodeGen** from `ios/project.yml`.
  `xcodegen generate` re-creates `Home.xcodeproj` and is safe (team is baked into
  project.yml). Re-run it after adding new `.swift` files to app targets
  (files under `Packages/` are picked up by SwiftPM automatically).

### Build & install (Mac, USB)
```bash
cd ios
xattr -cr .   # strip iCloud Finder metadata (Desktop is iCloud-synced → breaks codesign)
xcodegen generate
xcodebuild -project Home.xcodeproj -scheme Home -configuration Release \
  -destination 'platform=iOS,id=<UDID>' -derivedDataPath /tmp/HomeDD \
  -allowProvisioningUpdates build
xcrun devicectl device install app --device <UDID> /tmp/HomeDD/Build/Products/Release-iphoneos/Home.app
xcrun devicectl device process launch --terminate-existing --device <UDID> com.mattiasdaum.home
```
- Device UDID: `08AC584F-7C2D-5171-B53C-39894A239516` ("Iti Mari's iPhone").
- If `devicectl install` is flaky, retry — tunnel can drop.
- First install after a rebuild may need the device to **trust** the developer
  (Settings → General → VPN & Device Management).

### Server URLs (API.swift)
- `defaultBases = [http://100.92.219.95:8000, http://192.168.8.147:8000]` — starts
  with Tailscale, falls back to home LAN, then prefers the last working address.
- `API.activeBase` = the address that last answered successfully; preferred on
  subsequent requests and used to build stream/image URLs.
- **ATS**: `Info.plist` has `NSAllowsArbitraryLoads` + `NSExceptionDomains` for
  `100.92.219.95`, `192.168.8.147`, `100.95.105.68`. On iOS 27, the IP exception
  domains are what actually allow plain-HTTP (AVPlayer specifically). If you add a
  new server IP, add it to all three Info.plists (app, widget, share).

### Key files
```
HomeApp/API.swift         API client + models + tool helpers (fridge models live in HomeCore)
HomeApp/Design.swift      Palette (blue/teal), Card, ProgressPill, Haptics, Skeleton
HomeApp/ContentView.swift 7-tab layout (Assistant, Devices, Media, Fridge, Recipes, Shopping, Settings)
HomeApp/DevicesView.swift washer/fridge/vent/weather/electricity/torrents cards
HomeApp/MediaView.swift   poster grid, detail sheet, downloads, episodes, on-device
HomeApp/PlayerView.swift  AVPlayer + subtitle overlay + loading/error
HomeApp/DeviceState.swift shared state so tabs don't reload
HomeApp/DownloadManager.swift / AppLog.swift / Notifications.swift
```

### Design
Liquid Glass look: `glassEffect` cards, `Palette.accent` (blue → teal gradient,
**no purple**), 44 pt touch targets, `PressableButtonStyle` (scale 0.96),
`Haptics` everywhere. Keep it consistent.

---

## 6. Key workflows

### Letterboxd → movie on the TV
1. User adds to Letterboxd watchlist (`daum13`).
2. Backend `_letterboxd_watcher` polls `letterboxd.com/daum13/watchlist/` every
   30 min, parses `data-item-name`, skips titles already in Jellyfin, and adds the
   rest to Radarr (`POST /api/v3/movie` with `searchForMovie: true`).
3. Radarr searches **YTS + The Pirate Bay** (via Prowlarr), grabs H.264 only
   (custom-format rule), sends to Transmission.
4. Transmission downloads to `/mnt/ketas/downloads` → Radarr imports/renames into
   `/mnt/ketas/filmid`.
5. `_jellyfin_refresh_watcher` rescans Jellyfin every 10 min → visible in app/TV.
6. Transmission stops seeding immediately after completion (`ratio-limit` 0.01 +
   `idle-seeding-limit` 0).

### Playing a movie/episode
- App fetches library from Jellyfin; movies fall back to `local_movies` and
  series/episodes to `local_series`/`local_episodes` when the Mac is offline.
  Offline entries have no Jellyfin posters, cast or descriptions.
- `Play` → `GET /api/media/stream?path=<path>` — Pi serves the file directly.
- Subtitles: app fetches `/api/media/subtitles?path=` (WebVTT) and overlays.

### Coop receipt → fridge inventory
- Share extension uploads the PDF to `/api/receipts/import`, or email/`data/receipts/`
  watcher imports it. Parser handles the Coop "Tšekk nr" format. SQLite
  `fridge_items` stores one package per receipt line, including repeated barcodes.
  The original `inventory` table is retained as a read-only migration archive.
- Fridge tab, widget, recipes, barcode tools, web PWA and voice tools all read
  the same local inventory. hOn can be imported explicitly by cloud item id;
  imports never write or delete cloud data and do not resurrect removed items.

---

## 7. Known issues & gotchas

- **API is unauthenticated** — Tailscale limits reachability but does not
  authorize callers. Do not expose :8000 publicly or to untrusted peers;
  `/api/tools/{name}` permits device control, file reads and media deletion.
  Coordinated client/server authentication is tracked in `PLAN.md`.
- **SmartThings PAT expires every 24 h** — washer breaks daily until the user
  generates a new PAT (`account.smartthings.com/tokens`) and it's put in `.env`.
  (OAuth is the long-term fix, deferred.)
- **Double NAT** (see §1): TP-Link should be in AP mode. Until then, use Tailscale.
- **Mac must be on for Jellyfin metadata/posters** — streaming works without it
  (Pi scans movies and series/episodes, with titles but no posters).
- **10-bit HEVC/HDR/AV1** play on iPhone but **not** the TV. Radarr avoids
  downloading them, but pre-existing files remain (flagged with 🔴 badges).
- **Offline transcoded MP4 downloads are progressive**; unsupported-audio
  in-app playback uses HLS, while native AAC/AC3 files support byte-range seeking.
- **XviD `.avi`** files won't play on iPhone (no transcode for those).
- **NTFS corruption**: `/mnt/ketas/serials/Sherlock/` has a stale
  `Fantastic.Beasts…[rarbg]` folder that returns `Input/output error` on delete.
  Drive may need `chkdsk` on a Windows machine.
- **Jellyfin v12 gotcha**: the single-item endpoint `GET /Items/{id}` returns 400.
  Use the list endpoint `GET /Items?Ids={id}&Fields=…` (`_get_item` helper does this).
- **Codesign** fails if built inside the iCloud-synced Desktop folder — always
  `xattr -cr .` and use an out-of-tree `-derivedDataPath` (e.g. `/tmp/HomeDD`).

---

## 8. Conventions

- The app UI and default assistant replies are **English**; iOS and web
  speech recognition/TTS default to English (`en-US`). The assistant can match
  other languages when the user writes in them.
- Tool errors return `{"ok":false,"error":…}` — never raise out of `run_tool`.
- Cache device data (weather 5 min, electricity 60 s, fridge 180 s, washer 15 s).
- The LLM only sees tool *schemas*; `run_tool` forwards supplied arguments
  without schema validation. Handlers must validate inputs (especially file
  paths and destructive actions); add centralized validation before relying on
  schemas as a security boundary.
- Commit changes to git (`master`) and push to `origin` (GitHub `daum88/home-app`).
- After backend changes: rsync to the Pi + `systemctl restart home-voice-assistant`.
- After iOS changes: `xcodegen generate` (if new files) → build → `devicectl install`.
