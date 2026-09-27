import Foundation

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
    /// Download progress by destination filename (0…1).
    @Published var progress: [String: Double] = [:]

    private var session: URLSession!
    private var continuations: [String: CheckedContinuation<Void, Error>] = [:]
    private var destinations: [Int: URL] = [:]
    private var names: [Int: String] = [:]

    override init() {
        super.init()
        let config = URLSessionConfiguration.background(withIdentifier: "com.mattiasdaum.home.downloads")
        config.sessionSendsLaunchEvents = true
        config.isDiscretionary = false
        session = URLSession(configuration: config, delegate: self, delegateQueue: nil)
    }

    private var dir: URL {
        let d = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("Downloads", isDirectory: true)
        try? FileManager.default.createDirectory(at: d, withIntermediateDirectories: true)
        return d
    }

    func refresh() {
        let urls = (try? FileManager.default.contentsOfDirectory(at: dir, includingPropertiesForKeys: [.fileSizeKey, .contentModificationDateKey])) ?? []
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
        let safeName = filename.isEmpty ? name : filename
        let dest = dir.appendingPathComponent(safeName)
        if FileManager.default.fileExists(atPath: dest.path) { refresh(); return }

        activeDownloads.insert(safeName)
        progress[safeName] = 0

        do {
            try await withCheckedThrowingContinuation { (cont: CheckedContinuation<Void, Error>) in
                continuations[safeName] = cont
                let task = session.downloadTask(with: URLRequest(url: remoteURL))
                destinations[task.taskIdentifier] = dest
                names[task.taskIdentifier] = safeName
                task.resume()
            }
        } catch {
            activeDownloads.remove(safeName)
            progress[safeName] = nil
            throw error
        }
        activeDownloads.remove(safeName)
        progress[safeName] = nil
        refresh()
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
        Task { @MainActor [weak self] in
            guard let self, let dest = self.destinations[downloadTask.taskIdentifier] else { return }
            try? FileManager.default.removeItem(at: dest)
            try? FileManager.default.moveItem(at: location, to: dest)
        }
    }

    nonisolated func urlSession(_ session: URLSession, task: URLSessionTask, didCompleteWithError error: Error?) {
        Task { @MainActor [weak self] in
            guard let self, let name = self.names[task.taskIdentifier] else { return }
            if let cont = self.continuations[name] {
                self.continuations[name] = nil
                if let error {
                    cont.resume(throwing: error)
                } else {
                    cont.resume()
                }
            }
            self.names[task.taskIdentifier] = nil
            self.destinations[task.taskIdentifier] = nil
        }
    }

    nonisolated func urlSessionDidFinishEvents(forBackgroundURLSession session: URLSession) {}
}
