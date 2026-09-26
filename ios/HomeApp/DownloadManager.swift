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

    func isDownloaded(_ filename: String) -> Bool {
        items.contains { $0.filename == filename }
    }

    /// Download a remote file into the local Downloads directory.
    func download(name: String, filename: String, remoteURL: URL) async throws {
        let safeName = filename.isEmpty ? name : filename
        let dest = dir.appendingPathComponent(safeName)
        if FileManager.default.fileExists(atPath: dest.path) { refresh(); return }

        activeDownloads.insert(safeName)
        defer { activeDownloads.remove(safeName); refresh() }

        let (tmp, _) = try await URLSession.shared.download(from: remoteURL)
        try? FileManager.default.removeItem(at: dest)
        try FileManager.default.moveItem(at: tmp, to: dest)
    }

    func delete(_ item: DownloadedItem) {
        try? FileManager.default.removeItem(at: item.url)
        refresh()
    }
}
