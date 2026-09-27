# UI redesign — implementation status

Implements the visual/interaction direction from `docs/DESIGN_BRIEF.md` across
the whole SwiftUI app. Builds on top of the other agent's functional work
(`ce73d43`) — no functional/backend changes were reverted.

## Done

- **Origin-aware morphing transitions** (iOS 18 zoom): movie poster → detail,
  fridge row → item detail, and washer tile → washer detail now expand from the
  source they were tapped, using `matchedTransitionSource` +
  `.navigationTransition(.zoom)`. The detail screens were converted from sheets
  to `NavigationStack` pushes for a shared transition namespace.
- **Palette — paper / ink / light.** `Theme` now uses warm paper canvas
  (`#F5F2EB`), raised surface (`#FCFAF5`), charcoal-green ink (`#182522`),
  deep teal accent (`#276B67`), copper highlight (`#BA8550`), plus fixed
  semantic `success / warning / danger`. `Palette.accent` = deep teal.
- **Flat design.** Icon tiles are now plain tinted glyphs (no square tile behind
  every icon); cards are matte paper surfaces with hairline borders and fewer
  shadows.
- **Four-tab navigation.** Home / Media / Food / Assistant with an anchored
  matte bottom bar (no floating capsule). Settings moved behind a gear in Home.
- **New Food tab.** Expiring soon, fridge overview, shopping quick-add, and
  recipe ideas on one dashboard; Fridge / Shopping / Recipes / Spending open
  from it (barcode scan in the toolbar).
- **Home ("Now").** Serif greeting + date, settings gear, contextual
  "Notify me when done" on a running washer, washer controls hidden when the
  washer isn't configured, semantic state colors.
- **Media.** Continue Watching stays first; Movies/Series are the primary
  shelves; Downloads and On-device files are clear toolbar destinations instead
  of a four-way segmented control.
- **Assistant.** Smaller flat ink orb, serif greeting, 2×2 contextual shortcut
  cards instead of a clipped horizontal strip.
- **Typography.** System serif `.display()` for greetings/section leads;
  `.monospacedDigit()` on instrument values.
- **Settings.** Plain-language connection test showing the active server.
- **Accessibility.** `accessibilityReduceMotion` respected by the entrance
  motion and the idle orb pulse.

## Deferred (needs device/user input)

- **Remaining morphs** (movie detail → player, recipe cover → Cook Mode,
  assistant shortcut → conversation): the full-screen and cross-navigation
  handoffs need further work; the three core push morphs are in.
- **Trustworthy Live Activity** (APNs push updates): requires the APNs `.p8`
  key + backend push; the current app-side `pushType: nil` activity is
  unchanged and only refreshes in the foreground.
- **Paper grain texture** and **dark "media night" surface**: skipped to keep
  the palette flat; can be layered in later.

## Validation

`xcodegen generate` + `xcodebuild` (generic + Release device) both pass. The
app was installed on the iPhone; final visual confirmation and real-device
acceptance remain (`docs/DEVICE_CHECKLIST.md`).
