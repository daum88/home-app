import Foundation

public struct ResumeDecision {
    private var position: Double?
    private var duration: Double?
    public private(set) var didSeek = false

    public init() {}

    public mutating func receivePosition(_ value: Double) -> Double? {
        position = value
        return seekTarget()
    }

    public mutating func receiveDuration(_ value: Double) -> Double? {
        duration = value
        return seekTarget()
    }

    private mutating func seekTarget() -> Double? {
        guard !didSeek, let position, let duration,
              position.isFinite, duration.isFinite,
              position > 5, duration > 0, position < duration - 10 else { return nil }
        didSeek = true
        return position
    }
}
