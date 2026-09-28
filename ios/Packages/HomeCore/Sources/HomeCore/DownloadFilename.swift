import Foundation

public enum DownloadFilename {
    public static func resolved(source: String, suggested: String?) -> String {
        let sourceName = (source as NSString).lastPathComponent
        let fallback = sourceName.isEmpty || sourceName == "." || sourceName == ".." ? "download" : sourceName
        guard let suggested, !suggested.isEmpty else { return fallback }
        let name = (suggested as NSString).lastPathComponent
        return name.isEmpty || name == "." || name == ".." ? fallback : name
    }
}
