import Foundation

/// Minimal API client for the widget (separate process from the app).
enum Server {
    /// Candidate servers, tried in order (Tailscale works from anywhere).
    static let bases = [
        "http://100.92.219.95:8000",
        "http://192.168.8.147:8000"
    ]

    struct Envelope<T: Decodable>: Decodable {
        let ok: Bool
        let data: T?
        let error: String?
    }

    struct ExpiringItem: Decodable, Identifiable {
        var id: Int
        var name: String
        var expiresOn: String?
        var daysLeft: Int?
    }
    struct ExpiringList: Decodable { var items: [ExpiringItem] }

    struct WeatherNow: Decodable {
        var temperature: Double?
        var condition: String?
        var isDay: Int?
        var tempMax: Double?
        var tempMin: Double?
    }

    struct ElectricityHour: Decodable {
        var hour: String
        var price: Double
    }
    struct Electricity: Decodable {
        var currentCentsPerKwh: Double?
        var todayMin: Double?
        var todayMax: Double?
        var todayHours: [ElectricityHour]?
    }

    static func run<T: Decodable>(_ name: String, args: [String: Any] = [:]) async throws -> T {
        var lastError: Error = URLError(.badURL)
        for base in bases {
            guard let url = URL(string: base + "/api/tools/" + name) else { continue }
            var req = URLRequest(url: url)
            req.httpMethod = "POST"
            req.timeoutInterval = 10
            req.setValue("application/json", forHTTPHeaderField: "Content-Type")
            req.httpBody = try JSONSerialization.data(withJSONObject: ["args": args])
            do {
                let (data, resp) = try await URLSession.shared.data(for: req)
                if let http = resp as? HTTPURLResponse, !(200..<300).contains(http.statusCode) {
                    throw URLError(.badServerResponse)
                }
                let decoder = JSONDecoder()
                decoder.keyDecodingStrategy = .convertFromSnakeCase
                let env = try decoder.decode(Envelope<T>.self, from: data)
                if !env.ok { throw URLError(.badServerResponse) }
                guard let d = env.data else { throw URLError(.cannotParseResponse) }
                return d
            } catch let e as URLError {
                lastError = e
            } catch {
                throw error
            }
        }
        throw lastError
    }

    static func expiringItems() async -> [ExpiringItem] {
        ((try? await run("inventory_expiring", args: ["days": 7])) as ExpiringList?)?.items ?? []
    }

    static func weather() async -> WeatherNow? {
        try? await run("weather_now") as WeatherNow
    }

    static func electricity() async -> Electricity? {
        try? await run("electricity_price") as Electricity
    }
}
