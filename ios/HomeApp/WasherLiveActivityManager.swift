import ActivityKit

/// Starts/updates/ends the washer Live Activity (Dynamic Island + lock screen).
@MainActor
final class WasherLiveActivityManager {
    static let shared = WasherLiveActivityManager()
    private var activity: Activity<WasherAttributes>?

    func sync(machineState: String?, progress: Double?, remainingMinutes: Int?) {
        let state = WasherAttributes.ContentState(
            machineState: machineState ?? "unknown",
            progress: progress ?? 0,
            remainingMinutes: remainingMinutes
        )
        let running = ["run", "running", "washing"].contains(machineState ?? "")

        if running {
            if let activity {
                Task { await activity.update(using: state) }
            } else {
                do {
                    activity = try Activity.request(
                        attributes: WasherAttributes(washerName: "Washer"),
                        contentState: state,
                        pushType: nil
                    )
                } catch {
                    // Live Activity unavailable (e.g. simulator without Dynamic Island)
                }
            }
        } else if let activity {
            Task { await activity.end(using: state, dismissalPolicy: .immediate) }
            self.activity = nil
        }
    }
}
