import Foundation

/// Tracks movies downloaded to the phone and handles saving/deleting them.
@MainActor
final class DownloadManager: ObservableObject {
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

    private let session: URLSession = {
        let config = URLSessionConfiguration.default
        return URLSession(configuration: config)
    }()

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

    /// Download a remote file into the local Downloads directory, reporting progress.
    func download(name: String, filename: String, remoteURL: URL) async throws {
        let safeName = filename.isEmpty ? name : filename
        let dest = dir.appendingPathComponent(safeName)
        if FileManager.default.fileExists(atPath: dest.path) { refresh(); return }

        activeDownloads.insert(safeName)
        progress[safeName] = 0
        defer { activeDownloads.remove(safeName); progress[safeName] = nil; refresh() }

        let delegate = DownloadProgressDelegate { [weak self] p in
            Task { @MainActor in self?.progress[safeName] = p }
        }
        let (tmp, response) = try await session.download(for: URLRequest(url: remoteURL), delegate: delegate)
        guard let http = response as? HTTPURLResponse, (200..<300).contains(http.statusCode) else {
            try? FileManager.default.removeItem(at: tmp)
            throw APIError.server("Download failed: server returned an error")
        }
        try? FileManager.default.removeItem(at: dest)
        try FileManager.default.moveItem(at: tmp, to: dest)
    }

    func delete(_ item: DownloadedItem) {
        try? FileManager.default.removeItem(at: item.url)
        refresh()
    }
}

/// Reports download progress back to the manager.
final class DownloadProgressDelegate: NSObject, URLSessionDownloadDelegate {
    private let onProgress: (Double) -> Void

    init(onProgress: @escaping (Double) -> Void) {
        self.onProgress = onProgress
    }

    func urlSession(_ session: URLSession, downloadTask: URLSessionDownloadTask,
                    didWriteData bytesWritten: Int64, totalBytesWritten: Int64,
                    totalBytesExpectedToWrite: Int64) {
        guard totalBytesExpectedToWrite > 0 else { return }
        onProgress(Double(totalBytesWritten) / Double(totalBytesExpectedToWrite))
    }

    func urlSession(_ session: URLSession, downloadTask: URLSessionDownloadTask,
                    didFinishDownloadingTo location: URL) {
        // The async `download(for:delegate:)` returns the final URL itself.
    }
}
