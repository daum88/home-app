# Real-device acceptance checklist

Run this **after backing up the Pi database and with the owner's approval**.
CI and the iOS simulator cannot validate SmartThings, hOn, the media drive, or
notifications on a real iPhone. Do not run destructive tools as a smoke test.

## Before deployment

- [ ] Back up `/opt/home-voice-assistant/data/home.db` (SQLite backup API while the service is live).
- [ ] Record counts of the existing SQLite and hOn inventory; review possible duplicate
      cloud/receipt items before using **Import hOn items**.
- [ ] Confirm the Pi has free disk space and that `FS_ROOT` points at the intended media drive.

## On the Pi and phone

- [ ] Deploy/restart the service only with approval. Run
      `python scripts/device_check.py --base http://127.0.0.1:8000 --devices`
      on the Pi. `--devices` performs status reads only.
- [ ] In the iOS app, add a disposable local fridge item. Confirm it appears in
      Fridge, the web PWA, and the expiry widget; remove it and check it disappears.
- [ ] Trigger **Import hOn items** once, review counts and duplicates, and confirm
      a second import adds zero items. Confirm deleting an imported item locally
      does not delete anything in hOn or restore it on another import.
- [ ] Scan a grocery barcode and import one known Coop PDF. Verify each item
      appears once locally, with the correct location and expiry; importing the
      same receipt again should report "Already imported".
- [ ] With the Mac/Jellyfin offline, open both Movies and Series; confirm titles,
      episodes, and playback from the Pi. With Jellyfin online, check posters
      and movie details return.
- [ ] Pause a supported video, leave the player, reopen it, and verify resume
      regardless of whether the playback response arrives before or after video
      readiness. Seek in a direct stream and in an HLS-transcoded stream.
- [ ] Interrupt playback, restart the service, and check `.hls` does not retain
      old segment folders or orphan ffmpeg processes.
- [ ] Switch repeatedly between Media, Fridge, Shopping and Assistant: the
      screens should retain their loaded state and chat; force a server outage
      and verify actionable English error/retry messages.
- [ ] Exercise the receipt share extension and check the widgets on a real
      iPhone. Do **not** start/stop the washer or change ventilation settings
      solely for a smoke test.

Record pass/fail, device/iOS/Pi versions and any failures before considering
this release deployed. Never copy credentials or receipt contents into logs.
