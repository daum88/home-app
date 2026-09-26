import Foundation

enum APIError: LocalizedError {
    case badURL
    case server(String)
    case decode(String)

    var errorDescription: String? {
        switch self {
        case .badURL: return "Bad URL"
        case .server(let m): return m
        case .decode(let m): return "Decode error: \(m)"
        }
    }
}

// Generic tool envelope: { ok, data, error }
struct ToolEnvelope<T: Decodable>: Decodable {
    let ok: Bool
    let data: T?
    let error: String?
}

// ── Device models ────────────────────────────────────────────────────────────
struct WasherStatus: Decodable {
    var machineState: String?
    var jobState: String?
    var progress: Double?
    var remainingMinutes: Int?
    var completionTime: String?
    var currentCycle: String?
    var waterTemp: String?
    var spinLevel: String?
    var rinseCycles: String?
    var dryLevel: String?
    var powerSwitch: String?
    var remoteControlEnabled: String?
    var scheduledJobs: [ScheduledJob]?

    struct ScheduledJob: Decodable {
        var jobName: String?
        var timeInMin: Int?
    }

    enum CodingKeys: String, CodingKey {
        case machineState, jobState, progress, remainingMinutes, completionTime
        case currentCycle, waterTemp, spinLevel, rinseCycles, dryLevel
        case powerSwitch = "switch"
        case remoteControlEnabled
        case scheduledJobs
    }
}

struct WeatherForecastDay: Decodable, Identifiable {
    var id: String { date ?? UUID().uuidString }
    var date: String?
    var max: Double?
    var min: Double?
    var condition: String?
    var precipProb: Int?
}
struct WeatherForecast: Decodable { var days: [WeatherForecastDay] }

struct FridgeStatus: Decodable {
    var connected: Bool?
    var fridgeTemp: Double?
    var freezerTemp: Double?
    var fridgeSetTemp: Double?
    var freezerSetTemp: Double?
    var fridgeDoorOpen: Bool?
    var freezerDoorOpen: Bool?
    var superCool: Bool?
    var superFreeze: Bool?
    var on: Bool?
}

struct VentStatus: Decodable {
    var supplyTemp: Double?
    var extractTemp: Double?
    var co2: Int?
    var humidity: Int?
    var airflow: String?
    var userMode: String?
    var tempSetpoint: Double?
    var filterDaysLeft: Int?
    var iaqLevel: String?
}

struct Torrent: Decodable, Identifiable {
    var id: Int
    var name: String
    var status: String
    var progress: Double
    var eta: String?
    var size: String?
}
struct TorrentList: Decodable { var torrents: [Torrent] }

// ── Fridge inventory ─────────────────────────────────────────────────────────
struct FridgeItem: Decodable, Identifiable {
    var id: Int
    var name: String
    var quantity: Double?
    var unit: String?
    var expiresOn: String?
    var position: String?
}
struct FridgeInventory: Decodable { var items: [FridgeItem] }

struct PriceHistoryEntry: Decodable, Identifiable {
    var barcode: String?
    var name: String?
    var price: Double
    var boughtOn: String?
    var id: String { "\(boughtOn ?? "")-\(price)" }
}
struct PriceTrend: Decodable {
    var name: String?
    var latest: Double?
    var latestDate: String?
    var min: Double?
    var max: Double?
    var avg: Double?
    var history: [PriceHistoryEntry]?
}

struct ShoppingItem: Decodable, Identifiable { var id: Int; var name: String; var addedOn: String? }
struct ShoppingList: Decodable { var items: [ShoppingItem] }

struct WeatherNow: Decodable {
    var temperature: Double?
    var feelsLike: Double?
    var humidity: Int?
    var windKmh: Double?
    var condition: String?
    var isDay: Int?
    var tempMax: Double?
    var tempMin: Double?
}

struct KodiStatus: Decodable { var playing: String?; var paused: Bool?; var percentage: Double? }

struct JellyfinStatus: Decodable { var server: String?; var version: String? }
struct JellyfinItem: Decodable, Identifiable {
    var id: String
    var name: String
    var type: String?
    var year: Int?
    var series: String?
    var season: Int?
    var episode: Int?
    var runtimeMin: Int?
    var rating: Double?
    var officialRating: String?
    var premiereDate: String?
    var genres: [String]?
    var overview: String?
    var image: String?
    var path: String?
    var sizeMB: Double?
    var videoCodec: String?
    var bitDepth: Int?
    var resolution: String?
    var hdr: Bool?
}
struct JellyfinItemList: Decodable { var items: [JellyfinItem] }
struct JellyfinSearchResults: Decodable { var results: [JellyfinItem] }
struct JellyfinDeleteResult: Decodable { var deleted: Bool; var name: String?; var path: String? }

struct JellyfinEpisode: Decodable, Identifiable {
    var id: String
    var name: String
    var season: Int?
    var episode: Int?
    var path: String?
    var sizeMB: Double?
}
struct JellyfinEpisodeList: Decodable { var episodes: [JellyfinEpisode] }

struct JellyfinItemDetail: Decodable {
    var id: String
    var name: String?
    var year: Int?
    var runtimeMin: Int?
    var rating: Double?
    var officialRating: String?
    var premiereDate: String?
    var genres: [String]?
    var overview: String?
    var image: String?
    var cast: [String]?
    var director: String?
    var videoCodec: String?
    var bitDepth: Int?
    var resolution: String?
    var hdr: Bool?
    var sizeMB: Double?
}

struct StreamURLResult: Decodable { var url: String; var name: String? }
struct DownloadURLResult: Decodable { var url: String; var name: String?; var filename: String?; var size: Int64? }

struct DiskUsage: Decodable {
    var root: String?
    var totalGB: Double?
    var usedGB: Double?
    var freeGB: Double?
}

struct SavedRecipe: Decodable, Identifiable {
    var id: String
    var name: String
    var ingredients: [String]?
    var instructions: String?
    var url: String?
    var thumb: String?
    var source: String?
    var savedOn: String?
}
struct SavedRecipeList: Decodable { var recipes: [SavedRecipe] }

struct RecipeSuggestion: Decodable, Identifiable {
    var id: String
    var name: String
    var ingredients: [String]?
    var instructions: String?
    var thumb: String?
    var category: String?
    var area: String?
}
struct RecipeSuggestions: Decodable { var recipes: [RecipeSuggestion] }

struct ElectricityHour: Decodable, Identifiable {
    var hour: String
    var price: Double
    var id: String { hour }
}

struct ElectricityPrice: Decodable {
    var currentCentsPerKwh: Double?
    var todayMin: Double?
    var todayMax: Double?
    var todayAvg: Double?
    var todayHours: [ElectricityHour]?
    var upcomingHours: [ElectricityHour]?
    var tomorrowHours: [ElectricityHour]?
    var tomorrowMin: Double?
    var tomorrowMax: Double?
    var nextHours: [ElectricityHour]?
    var cheapestHours: [ElectricityHour]?
}

struct ChatResponse: Decodable { var reply: String }

struct ReceiptItem: Decodable {
    var name: String
    var category: String?
    var expiresOn: String?
}
struct ReceiptImport: Decodable {
    var alreadyImported: Bool?
    var receiptNo: String?
    var items: [ReceiptItem]?
}

struct BarcodeProduct: Decodable {
    var barcode: String
    var name: String
    var brands: String?
    var category: String?
    var image: String?
    var shelfLifeDays: Int?
}

struct SpendingMonth: Decodable, Identifiable { var month: String; var total: Double; var count: Int; var id: String { month } }
struct SpendingStore: Decodable, Identifiable { var store: String; var total: Double; var count: Int; var id: String { store } }
struct SpendingReceipt: Decodable, Identifiable {
    var receiptNo: String
    var store: String?
    var receiptDate: String?
    var total: Double?
    var itemCount: Int?
    var importedOn: String?
    var id: String { receiptNo }
}
struct SpendingStats: Decodable { var monthly: [SpendingMonth]; var stores: [SpendingStore]?; var recent: [SpendingReceipt]? }

// ── API client ───────────────────────────────────────────────────────────────
enum API {
    /// Candidate server addresses, tried in order.
    /// Tailscale (100.x) works from anywhere; the LAN IP is the fallback at home.
    static let defaultBases = [
        "http://100.92.219.95:8000",   // Tailscale (Pi)
        "http://192.168.8.147:8000"    // Home LAN (Pi)
    ]

    /// Custom override from Settings. Empty = auto (Tailscale → LAN).
    static var base: String {
        get { UserDefaults.standard.string(forKey: "serverURL") ?? "" }
        set { UserDefaults.standard.set(newValue, forKey: "serverURL") }
    }

    static var bases: [String] {
        let custom = base.trimmingCharacters(in: .whitespacesAndNewlines)
        if !custom.isEmpty { return [custom] + defaultBases }
        return defaultBases
    }

    /// The address that last answered successfully — used to build image URLs.
    static var activeBase: String = defaultBases.first ?? ""

    /// Build an absolute URL for a backend-served asset (e.g. a poster).
    static func imageURL(_ path: String) -> URL? {
        guard path.hasPrefix("/") else { return URL(string: path) }
        return URL(string: activeBase + path)
    }

    private static func sendOnce<T: Decodable>(_ req: URLRequest) async throws -> T {
        let (data, resp) = try await URLSession.shared.data(for: req)
        if let http = resp as? HTTPURLResponse, !(200..<300).contains(http.statusCode) {
            let detail: String
            if let e = try? JSONDecoder().decode([String: String].self, from: data) {
                detail = e["detail"] ?? e["error"] ?? "Error \(http.statusCode)"
            } else {
                detail = "Error \(http.statusCode)"
            }
            AppLog.error("HTTP \(http.statusCode) \(req.url?.path ?? "?"): \(detail)")
            throw APIError.server(detail)
        }
        do {
            let decoder = JSONDecoder()
            decoder.keyDecodingStrategy = .convertFromSnakeCase
            return try decoder.decode(T.self, from: data)
        } catch {
            throw APIError.decode(String(describing: error))
        }
    }

    private static func send<T: Decodable>(_ path: String, method: String = "GET", body: Data? = nil, contentType: String? = nil, timeout: TimeInterval = 6) async throws -> T {
        var lastError: Error = APIError.server("No server reachable")
        for b in bases {
            guard let url = URL(string: b + path) else { continue }
            var req = URLRequest(url: url)
            req.httpMethod = method
            req.timeoutInterval = timeout
            if let contentType { req.setValue(contentType, forHTTPHeaderField: "Content-Type") }
            req.httpBody = body
            do {
                activeBase = b
                return try await sendOnce(req)
            } catch let e as URLError {
                AppLog.error("\(b + path): \(e.localizedDescription) (code \(e.code.rawValue))")
                lastError = e  // connection-level failure → try the next address
            } catch {
                AppLog.error("\(b + path): \(error.localizedDescription)")
                throw error    // server answered (HTTP/decode) → this address is correct
            }
        }
        throw lastError
    }

    static func post<T: Decodable>(_ path: String, json: [String: Any], timeout: TimeInterval = 6) async throws -> T {
        let body = try JSONSerialization.data(withJSONObject: json)
        return try await send(path, method: "POST", body: body, contentType: "application/json", timeout: timeout)
    }

    static func tool<T: Decodable>(_ name: String, args: [String: Any] = [:]) async throws -> T {
        try await post("/api/tools/\(name)", json: ["args": args])
    }

    /// Run a tool and unwrap the envelope, throwing on `ok: false`.
    static func run<T: Decodable>(_ name: String, args: [String: Any] = [:]) async throws -> T {
        let env: ToolEnvelope<T> = try await tool(name, args: args)
        if !env.ok { throw APIError.server(env.error ?? "\(name) failed") }
        guard let data = env.data else { throw APIError.server("\(name): no data") }
        return data
    }

    static func chat(_ text: String, history: [[String: String]]) async throws -> String {
        let resp: ChatResponse = try await post("/api/chat", json: ["text": text, "history": history], timeout: 120)
        return resp.reply
    }

    static func importReceipt(_ data: Data, filename: String) async throws -> ReceiptImport {
        let boundary = "Boundary-\(UUID().uuidString)"
        var body = Data()
        body.append("--\(boundary)\r\n".data(using: .utf8)!)
        body.append("Content-Disposition: form-data; name=\"file\"; filename=\"\(filename)\"\r\n".data(using: .utf8)!)
        body.append("Content-Type: application/pdf\r\n\r\n".data(using: .utf8)!)
        body.append(data)
        body.append("\r\n--\(boundary)--\r\n".data(using: .utf8)!)
        return try await send("/api/receipts/import", method: "POST", body: body, contentType: "multipart/form-data; boundary=\(boundary)", timeout: 60)
    }
}
