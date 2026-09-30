import Foundation
import HomeCore

private enum DownloadFailure: LocalizedError {
    case invalidResponse
    case server(Int)

    var errorDescription: String? {
        switch self {
        case .invalidResponse: "The server did not return a valid download."
        case .server(let status): "Download failed (HTTP \(status))."
        }
    }
}

private func downloadDirectory() throws -> URL {
    let directory = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
        .appendingPathComponent("Downloads", isDirectory: true)
    try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    return directory
}

/// Tracks movies downloaded to the phone and handles saving/deleting them.
/// Uses a background URLSession so downloads continue when the app is closed.
@MainActor
final class DownloadManager: NSObject, ObservableObject {
    static let shared = DownloadManager()

    struct DownloadedItem: Identifiable {
        var id: String { filename }
        var name: String
        var filename: String
        var size: Int64
        var date: Date
        var url: URL
    }

    @Published var items: [DownloadedItem] = []
    @Published var activeDownloads: Set<String> = []
    /// Download progress by source filename (0…1).
    @Published var progress: [String: Double] = [:]

    private var session: URLSession!
    private var continuations: [Int: CheckedContinuation<Void, Error>] = [:]
    private var names: [Int: String] = [:]
    private var completions: [Int: DownloadCompletion] = [:]

    override init() {
        super.init()
        let config = URLSessionConfiguration.background(withIdentifier: "com.mattiasdaum.home.downloads")
        config.sessionSendsLaunchEvents = true
        config.isDiscretionary = false
        session = URLSession(configuration: config, delegate: self, delegateQueue: nil)
        cleanTemporaryFiles()
    }

    /// Remove stale partial-download files from the app's temp folder.
    /// Background downloads leave these behind when interrupted, which is what
    /// bloats the app's storage after repeated/failed downloads.
    func cleanTemporaryFiles() {
        let tmp = FileManager.default.temporaryDirectory
        let urls = (try? FileManager.default.contentsOfDirectory(at: tmp, includingPropertiesForKeys: nil)) ?? []
        for url in urls {
            try? FileManager.default.removeItem(at: url)
        }
    }

    func refresh() {
        guard let directory = try? downloadDirectory() else { items = []; return }
        let urls = (try? FileManager.default.contentsOfDirectory(at: directory, includingPropertiesForKeys: [.fileSizeKey, .contentModificationDateKey])) ?? []
        items = urls.compactMap { url in
            guard let attrs = try? url.resourceValues(forKeys: [.fileSizeKey, .contentModificationDateKey]) else { return nil }
            return DownloadedItem(
                name: url.deletingPathExtension().lastPathComponent,
                filename: url.lastPathComponent,
                size: Int64(attrs.fileSize ?? 0),
                date: attrs.contentModificationDate ?? Date(),
                url: url
            )
        }
        .sorted { $0.date > $1.date }
    }

    /// Download a remote file into the local Downloads directory.
    func download(name: String, filename: String, remoteURL: URL) async throws {
        let sourceName = DownloadFilename.resolved(source: filename.isEmpty ? name : filename, suggested: nil)
        let dest = try downloadDirectory().appendingPathComponent(sourceName)
        if FileManager.default.fileExists(atPath: dest.path) { refresh(); return }
        guard !activeDownloads.contains(sourceName) else { return }  // don't start a duplicate

        activeDownloads.insert(sourceName)
        progress[sourceName] = 0
        defer {
            activeDownloads.remove(sourceName)
            progress[sourceName] = nil
        }

        try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Void, Error>) in
            let task = session.downloadTask(with: URLRequest(url: remoteURL))
            let id = task.taskIdentifier
            continuations[id] = continuation
            names[id] = sourceName
            task.taskDescription = sourceName
            task.resume()
        }
        refresh()
    }

    private func fileFinished(_ result: Result<Void, Error>, taskID: Int) {
        var completion = completions[taskID] ?? DownloadCompletion()
        let outcome = completion.fileFinished(result)
        completions[taskID] = completion
        if let outcome { finish(outcome, taskID: taskID) }
    }

    private func taskCompleted(error: Error?, taskID: Int) {
        var completion = completions[taskID] ?? DownloadCompletion()
        let outcome = completion.networkFinished(error: error)
        completions[taskID] = completion
        if let outcome { finish(outcome, taskID: taskID) }
    }

    private func finish(_ result: Result<Void, Error>, taskID: Int) {
        completions[taskID] = nil
        names[taskID] = nil
        if case .success = result { refresh() }
        continuations.removeValue(forKey: taskID)?.resume(with: result)
    }

    func delete(_ item: DownloadedItem) {
        try? FileManager.default.removeItem(at: item.url)
        refresh()
    }
}

extension DownloadManager: URLSessionDownloadDelegate {
    nonisolated func urlSession(_ session: URLSession, downloadTask: URLSessionDownloadTask,
                                didWriteData bytesWritten: Int64, totalBytesWritten: Int64,
                                totalBytesExpectedToWrite: Int64) {
        guard totalBytesExpectedToWrite > 0 else { return }
        let fraction = Double(totalBytesWritten) / Double(totalBytesExpectedToWrite)
        Task { @MainActor [weak self] in
            if let name = self?.names[downloadTask.taskIdentifier] {
                self?.progress[name] = fraction
            }
        }
    }

    nonisolated func urlSession(_ session: URLSession, downloadTask: URLSessionDownloadTask,
                                didFinishDownloadingTo location: URL) {
        let result: Result<Void, Error>
        do {
            guard let response = downloadTask.response as? HTTPURLResponse else {
                throw DownloadFailure.invalidResponse
            }
            guard (200..<300).contains(response.statusCode) else {
                throw DownloadFailure.server(response.statusCode)
            }
            let suggested = response.value(forHTTPHeaderField: "Content-Disposition") == nil
                ? nil : response.suggestedFilename
            let filename = DownloadFilename.resolved(source: downloadTask.taskDescription ?? "download", suggested: suggested)
            let destination = try downloadDirectory().appendingPathComponent(filename)
            if !FileManager.default.fileExists(atPath: destination.path) {
                try FileManager.default.moveItem(at: location, to: destination)
            }
            result = .success(())
        } catch {
            result = .failure(error)
        }
        let id = downloadTask.taskIdentifier
        Task { @MainActor [weak self] in
            self?.fileFinished(result, taskID: id)
        }
    }

    nonisolated func urlSession(_ session: URLSession, task: URLSessionTask, didCompleteWithError error: Error?) {
        let id = task.taskIdentifier
        Task { @MainActor [weak self] in
            self?.taskCompleted(error: error, taskID: id)
        }
    }

    nonisolated func urlSessionDidFinishEvents(forBackgroundURLSession session: URLSession) {}
}
