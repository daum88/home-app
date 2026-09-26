import Foundation

/// Persistent, file-based logger for the app. Writes to Documents/app.log so
/// issues can be reviewed (Settings → Diagnostics) or shared. Also forwards
/// error lines to the backend so they show up in the Pi's logs.
enum AppLog {
    private static let fileURL: URL = {
        let dir = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
        return dir.appendingPathComponent("app.log")
    }()

    private static let dateFormatter: DateFormatter = {
        let f = DateFormatter()
        f.dateFormat = "yyyy-MM-dd HH:mm:ss"
        return f
    }()

    private static let queue = DispatchQueue(label: "app.log")

    static func log(_ message: String, level: String = "INFO") {
        let line = "[\(dateFormatter.string(from: Date())) \(level)] \(message)"
        queue.async {
            print(line)
            if let data = (line + "\n").data(using: .utf8) {
                if let handle = try? FileHandle(forWritingTo: fileURL) {
                    handle.seekToEndOfFile()
                    handle.write(data)
                    try? handle.close()
                } else {
                    try? data.write(to: fileURL)
                }
            }
        }
    }

    static func error(_ message: String) {
        log(message, level: "ERROR")
        postToServer(message)
    }

    static func contents() -> String {
        (try? String(contentsOf: fileURL, encoding: .utf8)) ?? "No log entries yet."
    }

    static func clear() {
        try? FileManager.default.removeItem(at: fileURL)
    }

    /// Fire-and-forget forward of an error line to the backend's /api/log.
    private static func postToServer(_ message: String) {
        let base = API.activeBase
        guard let url = URL(string: base + "/api/log") else { return }
        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.timeoutInterval = 5
        req.httpBody = try? JSONSerialization.data(withJSONObject: ["message": message])
        URLSession.shared.dataTask(with: req) { _, _, _ in }.resume()
    }
}
