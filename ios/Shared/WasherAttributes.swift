import ActivityKit

/// Shared between the app and the widget target so the Live Activity types match.
struct WasherAttributes: ActivityAttributes {
    public struct ContentState: Codable, Hashable {
        var machineState: String
        var progress: Double
        var remainingMinutes: Int?
    }
    var washerName: String
}
