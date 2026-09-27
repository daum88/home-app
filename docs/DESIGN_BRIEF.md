# Home — design and motion handoff

**Status: proposal only.** This is a design brief for another agent, not approval to change the UI. Review prototypes with the owner before implementing a wholesale restructure. Keep visible UI copy in **English**. Preserve existing backend/device workflows and data; do not fabricate device readings, media artwork, or a successful connection in production.

## 1. North star

Make Home feel like a *living household journal and control room*: the tactility of a well-made paperback, the precision of an analog instrument, and the effortless continuity of a native iPhone app. The user explicitly wants **more animation**, especially an object becoming its destination, not just a fade between unrelated screens. Aim for memorable motion with clear purpose, not permanent movement on every surface.

Borrow principles, not skins:

- **Apple Home:** glanceable device state, room/context grouping, safe controls.
- **Netflix and Jellyfin:** artwork and metadata carry the media experience; clear title/detail/play hierarchy.
- **YouTube:** resume, recent items, and a low-friction route back to what the user was doing.
- **Lightyear:** disciplined typography and numbers, calm surfaces, deliberate information density.
- **Paperback/analog:** paper tone, display serif, chapter-like headings, bookmarks, dials and calibrated marks *only where they communicate real data*.

The app should be unmistakably one product. Media may have a theatrical dark surface, but should share type, accent, icons, motion behavior, and navigation with Home/Food/Assistant. The web fallback should share the language without copying iOS controls pixel-for-pixel.

## 2. What was actually inspected

The iPhone 17 Pro simulator showed Assistant, Devices, Media, Fridge, Recipes, Shopping, and Settings. The backend was unreachable: the Media/Shopping error and the Devices/Fridge loading or unavailable states were inspected, **not** a populated library or live household readings. Re-inspect with safe fixture data and on a real iPhone before approving visuals.

Observed issues to solve:

- Seven cramped tabs inside a floating capsule; Media adds a four-way capsule immediately above its content.
- Assistant spends most of its first screen on whitespace and a large orb while useful suggestions are a clipped horizontal strip.
- Devices stacks a weather hero, generic cards, inner stat cards, and large Start/Pause/Stop tiles. Washer actions remain visible when status says “Not configured.”
- Fridge has four mostly unlabeled toolbar icons in a separate pill. Recipes offers little guidance when empty.
- Media and Shopping wait, then become nearly blank full-screen timeout messages; the Retry action sits close to the tab bar. Failure, empty, and setup-required states need different treatments.
- The immediate first-launch notification permission prompt appears before the user has seen the value of notifications.
- Too many shadows, capsules, cards-within-cards, repeated skeletons, and staggered entrances produce a component-demo feel rather than a composed screen.

## 3. Proposed information architecture

Start with a **four-destination prototype**, then validate it with actual tasks; do not migrate all navigation before the prototype works:

| Destination | Main question | First-screen content | Deeper navigation |
|---|---|---|---|
| Home | What needs my attention? | Compact status/connection header; live washer/door alerts; weather + electricity; a small device grid | Device details, all devices, settings |
| Media | What can I continue or play? | Continue Watching, recently added, then Movies/Series | Search, item/episode details, downloads and on-device files |
| Food | What is in the fridge and what do I need? | Expiring soon, fridge overview, shopping quick-add, recipe suggestions | Full inventory, shopping, recipes, spending, barcode/receipt import |
| Assistant | What can Home do for me? | Input and mic, recent conversation, 2×2 contextual shortcuts | Conversation history and voice settings |

Move Settings behind a labelled gear in Home; put rare data imports in Food's clearly named overflow menu. Shopping must remain a one-tap action within Food, not a buried fourth-level screen. Keep direct access to playback and washer status. Do not add a floating omnipresent AI bubble just to reduce tabs.

## 4. Visual language — paper, ink, light

Treat these as **starting tokens**, to be contrast-tested with real screenshots, not final hex values:

| Role | Suggested direction |
|---|---|
| Day canvas | Warm, quiet paper (`#F5F2EB`), not icy white everywhere |
| Raised surface | Subtle lighter paper (`#FCFAF5`); use grouping and hairlines before shadows |
| Primary ink | Deep charcoal-green (`#182522`) rather than pure black across every surface |
| Brand accent | Confident deep teal (`#276B67`); reserve for selection and meaningful actions |
| Warm secondary | Restrained amber/copper (`#BA8550`) for time, energy and editorial highlights |
| Media night | Near-black green/charcoal (`#101A1A`) with artwork providing color |
| State colors | Success, warning, danger have fixed semantic meaning, not one tint per tile |

Use three surface levels at most: canvas, grouped content, elevated modal/hero. Replace many rounded floating windows with aligned sections, flat interactive rows and fewer, larger image-led moments. Suggested radii: rows 10–14 pt, content surfaces 16–20 pt, artwork as its own shape. A bottom bar should feel anchored, not like another floating pill. Minimize blur and translucent layers; they are not the personality.

Paperback cues: fine paper grain **only** on broad surfaces (low contrast, pre-rendered, no animated noise); chapter/section headings; a slim bookmark or folded-corner progress motif for Continue Watching; restrained divider lines and margin labels. Analog cues: a washer-cycle ring or electricity time scale that conveys a *real value*, not decorative fake knobs. No faux physical control for destructive device commands. Artwork (movie posters, recipe photos, weather conditions) should create visual richness where genuine content exists. Offline local movies need a designed typography-first cover, not a false poster.

### Typography with personality

- **Display:** system serif/New York (`.system(..., design: .serif)`) for a greeting, feature title or editorial section lead—never for dense controls. Avoid licensing/embedding a third-party font until the typography is tested.
- **Utility:** SF Pro for navigation, buttons, descriptions and lists; use Dynamic Type styles rather than fixed sizes everywhere.
- **Instruments:** monospaced digits (or SF Mono sparingly) for time remaining, temperature, prices, percentages and progress. Keep units visually subordinate.
- Pair a strong editorial headline with compact, highly readable body copy. No wall of uppercase micro-labels; do not use seven near-identical large navigation titles on seven tabs.
- Define a small type scale and line-height/truncation rules for narrow phones and Accessibility sizes. Test accented Estonian product names even though UI chrome remains English.

## 5. Motion is part of navigation, not decoration

**Key requirement: origin-aware continuity.** An item should expand from the place the user touched, keep its visual identity, and collapse back to that place on dismissal where possible. Make back gestures interactive; do not flash an empty intermediate screen. Prefer a small shared vocabulary over one custom animation per screen.

| From → to | Suggested transformation | Preserve across transition |
|---|---|---|
| Device tile → device detail | Tile grows into full device panel; symbol and live value travel to the header; secondary controls reveal after geometry settles | Device ID, state and last-updated time |
| Washer running tile → Live Activity | Progress arc, state label and remaining time share the same visual grammar; not literally animate across app/OS boundaries | Value formatting, icon, semantic color |
| Movie poster/Continue card → detail | Poster becomes the detail artwork, progress bookmark remains attached, text and actions enter after artwork settles | Item ID, image, watched/progress state |
| Movie detail → player | Artwork darkens and becomes the player loading backdrop; playback takes over without a white flash; dismissal restores detail | Selected item and AVPlayer ownership |
| Food item → item detail | Row/counter expands; expiry marker travels with it, details unfold rather than opening an unrelated pill sheet | Local item ID and expiry state |
| Recipe cover → Cook Mode | Recipe image/title becomes the cooking-page heading; next step moves like a restrained page turn with a small tactile click | Current step and readable text at all times |
| Assistant shortcut → conversation | Shortcut label becomes a sent message; composer and voice affordance remain anchored | Typed text and conversation |

SwiftUI starting points: use `matchedGeometryEffect` for elements in one view hierarchy; on supported iOS versions explore `matchedTransitionSource` + navigation zoom for push transitions. These APIs are **options**, not a mandate: prototype the actual navigation and test reverse gesture/cancellation before selecting one. A player transition must not recreate AVPlayer or lose resume state merely for an effect. Avoid stacking multiple `NavigationStack`/sheet presentations that break a shared transition namespace.

Motion tokens to prototype: 120–180 ms tactile feedback; roughly 320–550 ms for a spatial morph (longer only for a genuinely cinematic media handoff); subtle numerical interpolation for progress/price; gentle parallax tied to user scroll, not a constantly moving background. A poster grid should **not** stagger hundreds of cells or delay an action. Use haptics to confirm consequential actions, not every animation frame. `@Environment(\.accessibilityReduceMotion)` should replace spatial motion with a short dissolve while preserving the same information and navigation. Reduce Transparency and Low Power Mode also deserve a sensible fallback. Allow **one restrained ambient motion per screen** when it communicates presence (a running cycle hand, listening waveform, or active download indicator); pause it off-screen, in Low Power Mode and under Reduce Motion. No perpetual skeleton shimmer after load and no spinning analog dial when status is unknown.

## 6. Icons and identity

Audit every current icon against its **meaning, recognizability at 20–24 pt, optical weight and accessible name**. Use one SF Symbols rendering policy (weight/filled state) for navigation, consistent size and alignment, and reserve custom vector artwork for a few brand-defining moments (app mark, weather/washer hero, intentional empty-state illustration). Avoid mixing emoji, multiple SF Symbol weights, gradients behind every glyph, and a square tile behind every icon. Test symbols in both appearances on device; provide text for ambiguous import/scan/more actions. The selected tab can use a short symbol transition and subtle indicator—not another capsule.

Create a one-page icon inventory (current → proposed → reason) before redrawing. Animate a symbol only when its state changes (`play` → `pause`, door closes, washer finishes). Do not invent a metaphor if the literal appliance symbol is clearer.

## 7. Live Activities and genuinely live information

Current implementation: `ios/HomeApp/WasherLiveActivityManager.swift` starts a washer activity with `pushType: nil`, and `ios/HomeWidget/WasherLiveActivity.swift` renders lock-screen/Dynamic Island state. Updates come from app-side status reads. **It will not reliably update in the background merely because the app has a foreground timer.** Do not promise a live countdown until device testing and a background update strategy exist.

Priority 1: make the washer activity trustworthy. Show cycle/name, progress or phase, estimated finish and a clearly labelled last update. Handle pause, completion, unavailable state and stale information; end activities reliably. If continuous background freshness is required, design ActivityKit push updates via APNs and secure token lifecycle/server credentials, and test real-device delivery. Confirm actual SmartThings rate limits before increasing polling.

Priority 2, only if useful: a sustained movie download could have a Live Activity with title, progress and completion, **if** Transmission/download progress and background updates are accurate. Do not create an activity for every torrent or use one to duplicate a static reminder. Electricity's upcoming cheap hour is better as a well-timed notification unless it is an active scheduled task. Use Now Playing / system media controls for playback rather than inventing a redundant Live Activity.

Ask for notification permission contextually (“Notify me when the washer finishes”), not on the first frame. Denial must leave the app usable.

## 8. Screen-level behavior and recovery

- **Home/Devices:** replace a full screen of equal-weight cards with one “Now” section and compact grouped devices. Hide or disable washer Start/Pause/Stop when the status is unknown. Distinguish **not configured**, **offline**, **loading**, and **last known**; give a relevant next action.
- **Media:** prioritize Continue Watching and resume, then browse shelves and search. Do not hide the entire library behind a four-way segmented control. With Jellyfin offline, display local files without pretending posters exist. Downloads/on-device files get one clear destination. Keep seeking, subtitles, audio fallback and errors intact.
- **Food:** show expiry, quantities and shopping at a glance; scanner/add actions visible by name or familiar symbol. hOn import is a rare explicit data task, not a primary floating-toolbar action. Receipt and barcode states should explain what was saved locally.
- **Assistant:** shrink the idle orb and empty vertical space; present purposeful shortcut cards, conversation and composer. A quiet waveform/orb may react **while listening**, not forever. Voice state must show permission, listening, processing and error distinctly.
- **Settings:** do not redesign functioning native forms for novelty. Add a plain-language connection test, notification controls and data-source explanation. Settings can move out of the bottom bar.
- **Offline:** show last known values with a timestamp when valid, plus a compact connection banner and Retry. Keep cached media/list content visible; never say “empty” just because a request timed out.

## 9. Handoff sequence and acceptance criteria

1. **Design first, no production refactor yet:** produce a small moodboard with cited principles, the proposed four-tab map, and a component/token sheet. Make populated, loading, empty, offline and active variants of Home, Media, Food and Assistant using clearly marked preview fixtures. Include light/dark and a narrow phone.
2. Prototype **three real morphs** (device → detail, poster → detail → player, food item → detail) with back gestures, interrupted transitions and Reduce Motion. Capture short simulator recordings. Present these to the owner for selection before replacing navigation.
3. Once approved, implement one vertical slice (Home + device detail) against existing APIs; compare before/after task completion and memory. Then Media, Food, Assistant and web. Replace old navigation/components gradually rather than a big-bang view rewrite.
4. Add snapshot/UI checks for the core states and critical actions; run existing Python, web DOM and Swift tests, the unsigned simulator build, and real-device acceptance. Check VoiceOver, Dynamic Type, dark mode, Reduce Motion, Low Power Mode and poor network. Target **no extra wait** or loss of cached content for visual animation.
5. For Live Activities, require a real-device/background test before claiming continuous updates. Keep authentication, inventory safety and backend reliability work in `PLAN.md` separate from visual polish.

A redesign succeeds when a person can identify a running washer, resume a film, add a grocery item and understand an outage faster than today—*and* the transitions feel like the same objects moving through a coherent home, not a collection of animated cards.

## 10. Project entry points for the implementing agent

- `ios/HomeApp/ContentView.swift`: current seven-tab floating capsule, retained-tab behavior.
- `ios/HomeApp/Design.swift`: palette, reusable cards/tiles, motion helper and typography starting point.
- `ios/HomeApp/DevicesView.swift`, `DeviceState.swift`: device hierarchy and state.
- `ios/HomeApp/MediaView.swift`, `ContinueWatchingRow.swift`, `PlayerView.swift`: poster/grid/detail/player continuity.
- `ios/HomeApp/FridgeView.swift`, `ShoppingView.swift`, `CookModeView.swift`: Food flows.
- `ios/HomeApp/AssistantView.swift`, `Notifications.swift`, `SettingsView.swift`: assistant, permission and recovery UX.
- `ios/HomeApp/WasherLiveActivityManager.swift`, `ios/HomeWidget/WasherLiveActivity.swift`, `ios/Shared/WasherAttributes.swift`: current Live Activity contract.
- `web/app.css`, `web/app.js`: web fallback; keep a recognizable sibling visual language.
- `ios/project.yml`: XcodeGen source of truth; regenerate after adding Swift files. `PLAN.md` tracks functional/deployment work. Do not touch production device controls just to demo animation.
