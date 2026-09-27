import AppIntents

/// Siri / Shortcuts: control the home assistant without opening the app.

struct WasherStatusIntent: AppIntent {
    static var title: LocalizedStringResource = "Washer status"
    static var description = IntentDescription("Checks how the washing machine is doing.")

    func perform() async throws -> some IntentResult & ProvidesDialog {
        do {
            let w: WasherStatus = try await API.run("washer_status")
            let state = w.machineState?.capitalized ?? "off"
            let msg = w.remainingMinutes.map { "\(state), \($0) minutes left" } ?? state
            return .result(dialog: "The washer is \(msg).")
        } catch {
            return .result(dialog: "Couldn't reach the washer.")
        }
    }
}

struct StartWasherIntent: AppIntent {
    static var title: LocalizedStringResource = "Start the washer"
    static var description = IntentDescription("Starts the washing machine.")

    func perform() async throws -> some IntentResult & ProvidesDialog {
        do {
            _ = try await API.run("washer_start") as EmptyResult
            return .result(dialog: "Washer started.")
        } catch {
            return .result(dialog: "Couldn't start the washer.")
        }
    }
}

struct AskHomeIntent: AppIntent {
    static var title: LocalizedStringResource = "Ask Home"
    static var description = IntentDescription("Opens the assistant to ask a question.")
    static var openAppWhenRun: Bool = true

    func perform() async throws -> some IntentResult {
        .result()
    }
}

struct HomeShortcuts: AppShortcutsProvider {
    static var appShortcuts: [AppShortcut] {
        AppShortcut(intent: WasherStatusIntent(), phrases: [
            "Check the washer with ${applicationName}",
            "${applicationName} washer status",
        ], shortTitle: "Washer status", systemImageName: "washer.fill")
        AppShortcut(intent: StartWasherIntent(), phrases: [
            "Start the washer with ${applicationName}",
            "Run the washing machine with ${applicationName}",
        ], shortTitle: "Start washer", systemImageName: "play.fill")
        AppShortcut(intent: AskHomeIntent(), phrases: [
            "Ask ${applicationName}",
        ], shortTitle: "Ask Home", systemImageName: "bubble.left.fill")
    }
}
