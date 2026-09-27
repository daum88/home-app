# Session handoff — Home app

This document describes the **entire working-tree change set** accumulated during this session, from the original `1410383` baseline through the documentation handoff. It is for the next agent and for review before deployment. See `PLAN.md` for the longer backlog and [`DESIGN_BRIEF.md`](DESIGN_BRIEF.md) for the **unapproved** UI proposal.

## Product and decisions

Home is a Raspberry Pi/FastAPI household backend with a SwiftUI iPhone app, widget/Live Activity, receipt share extension and web fallback. It integrates devices, a local food inventory, shopping, recipes, receipts and self-hosted media. Jellyfin on the Mac supplies metadata; the Pi serves files. The **UI and default assistant responses are English**. SQLite is now the only active fridge inventory source; hOn is an optional, explicit, **read-only cloud-to-local import**. Do not silently switch back to hOn as the app's primary database or automatically delete cloud items.

## Implemented in the working tree

### Inventory and receipts

- `app/db.py` adds package-level `fridge_items` with stable local IDs, quantities, positions and expiries. It copies existing `inventory` rows non-destructively and keeps that table as an archive. Repeated barcodes are now distinct packages. Receipt number + line index makes retries idempotent; legacy and hOn import markers prevent removed items from reappearing on restart or later import.
- `app/tools/local_inventory.py` backs the existing `fridge_inventory_list/add/remove` tool names with SQLite and adds an explicit `fridge_inventory_import_hon` tool. hOn imports do not write back to hOn and do not overwrite local edits. An item already present in both older systems can still appear twice: import is deliberately manual and warns the user.
- Receipt, barcode, recipe and expiry paths use the same local inventory. The Fridge tab, widget and PWA consume it. Automatic hOn writes were removed from receipt/barcode imports; the hOn integration remains available for explicit import.
- Failed-receipt filenames are restricted to the failed-receipts folder. Barcode-less receipt rows no longer overwrite one another.

### Media and backend reliability

- Media and subtitle routes reject paths outside `FS_ROOT`, including symlink escapes. Deletion refuses to remove a top-level collection. Single HTTP byte ranges support seeking/suffix ranges and return `416` for invalid ranges.
- `app/tools/jellyfin.py` reuses a bounded HTTP client during app lifespan and coalesces simultaneous cold poster requests. Filesystem movie scans, codec probing and deletion run off the event loop. Pi-local Series and Episodes tools provide browsing/playback paths while Jellyfin is unavailable; posters/cast still require Jellyfin.
- HLS sessions are bounded to four, coalesced by path, terminated and reaped on shutdown, and owned stale directories are removed on startup. Subtitle lookup/conversion is in `app/media_subtitles.py`. The offline video remux and real codecs still require live-device acceptance.
- SQLite enables WAL at initialization rather than for every query. Chat history I/O is off the event loop and saved as one exchange. Clients no longer send ignored chat-history payloads. Optional background watchers start only for configured integrations; short weather forecasts no longer crash.

### iOS, web and maintenance

- The Assistant model and already-visited tab views survive tab switches. iOS prefers the last working server. Media has retry/action feedback, and the player uses a tested resume decision that works regardless of whether the saved position or video readiness arrives first. Downloads now reject HTTP errors. Movie-library notification polling was reduced.
- Fridge and Shopping distinguish loading, empty and offline states. Shopping preserves typed text when Add fails and confirms Clear. Media's Series tab uses the local fallback rather than displaying movies. The PWA reads one inventory list for fridge and expiry and replaces unsafe dynamic torrent inline handlers with event listeners.
- English copy, speech and default prompt were aligned across the app and web. Dead app-only models/helpers and duplicate formatting were removed. `ContinueWatchingRow.swift` and `media_subtitles.py` begin splitting the large view/route files; the rest should wait for view-level coverage.
- `ios/HomeTests/` adds iOS model/resume tests; `web/app.test.cjs` adds DOM behavior tests; `tests/` adds offline SQLite, integration-mock, media, HLS, Jellyfin and migration tests. `.github/workflows/ci.yml` runs Python, web and iOS jobs. `scripts/device_check.py` and [`DEVICE_CHECKLIST.md`](DEVICE_CHECKLIST.md) specify read-only Pi checks and manual iPhone acceptance.
- [`DESIGN_BRIEF.md`](DESIGN_BRIEF.md) captures the user's preference for stronger morphing transitions, paperback/analog typography, better icons and reliable Live Activities. **It is a proposal only; no wholesale UI redesign was approved or implemented.**

## Validation and limits

Local validation passed: **28 Python tests**, **4 web DOM tests**, and **4 XCTest cases** on the iPhone 17 Pro / iOS 26.1 simulator; Python compilation, targeted Ruff checks (`F401`, `F821`, `F841`), JavaScript syntax and `git diff --check` also passed. CI has **not** run on GitHub; the macOS runner/Xcode configuration must be verified there. The simulator had **no reachable Pi/Jellyfin** while reviewing screens. No household device, Pi migration, real iPhone notification, background Live Activity or live media stream was validated. Do not treat simulator passes as deployment approval.

## Before merging or deployment

1. **Security (P0):** the API is unauthenticated; a peer that can reach port 8000 can run device/file/media tools. Add authorization spanning app, widget, share extension, web, playback and image URLs. Bound PDF/STT uploads; block SSRF and redirects to private services in recipe URL imports; finish the web HTML/CSP audit.
2. **Data safety (P0 for deployment):** make a SQLite backup on the Pi, compare existing local/hOn counts, and review duplicates before triggering manual hOn import. Existing historic barcode upserts cannot reconstruct packages already overwritten in the old database. Do not delete legacy tables or hOn data. See [`DEVICE_CHECKLIST.md`](DEVICE_CHECKLIST.md).
3. **Real-world validation:** run the checklist on the Pi and a real iPhone only with the owner's approval. Confirm receipt/share flows, local/movie/series fallback, subtitle and HLS seeking, ffmpeg process recovery, device-offline behavior, tab memory use and widget inventory. Verify the new CI workflow on GitHub before relying on it.
4. **Live Activities:** washer updates currently originate from app-side status reads and use `pushType: nil`; do not advertise a continuously fresh background countdown until an APNs/backend strategy has been designed and tested on device.
5. **UI and architecture:** obtain owner approval for the design brief's prototypes before changing navigation. Add view-level/UI tests and then split remaining `MediaView.swift`/`main.py` responsibilities. Other follow-ups: cached-poster MIME metadata, bounded subtitle search, stronger device recovery guidance, shared server settings across extensions and further real-device performance profiling.

**Release state:** code and docs are local repository work until a separately approved deploy/install. This handoff does not authorize pushing, deploying to the Pi, installing on an iPhone, running destructive device controls, or implementing the proposed redesign.
