import Foundation

public struct DownloadCompletion {
    private var fileResult: Result<Void, Error>?
    private var networkCompleted = false

    public init() {}

    public mutating func fileFinished(_ result: Result<Void, Error>) -> Result<Void, Error>? {
        if networkCompleted { return result }
        fileResult = result
        return nil
    }

    public mutating func networkFinished(error: Error?) -> Result<Void, Error>? {
        if let error { return .failure(error) }
        if let fileResult { return fileResult }
        networkCompleted = true
        return nil
    }
}
