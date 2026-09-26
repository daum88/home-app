import SwiftUI

/// Holds device/status data across tab switches so the Devices screen doesn't
/// re-fetch everything every time you switch tabs. Loads once, then only
/// refreshes on pull-to-refresh, the refresh button, or if data is stale.
@MainActor
final class DeviceState: ObservableObject {
    @Published var washer: WasherStatus?
    @Published var fridge: FridgeStatus?
    @Published var vent: VentStatus?
    @Published var torrents: [Torrent] = []
    @Published var weather: WeatherNow?
    @Published var electricity: ElectricityPrice?
    @Published var loaded = false
    @Published var errorMessage: String?

    private var lastLoad: Date?

    /// Load only if never loaded, forced, or stale (>2 min).
    func loadIfNeeded(force: Bool = false) async {
        let now = Date()
        if !force, loaded, let last = lastLoad, now.timeIntervalSince(last) < 120 { return }
        await loadAll()
    }

    func loadAll() async {
        async let a: Void = loadWasher()
        async let b: Void = loadFridge()
        async let c: Void = loadVent()
        async let d: Void = loadTorrents()
        async let e: Void = loadWeather()
        async let g: Void = loadElectricity()
        _ = await (a, b, c, d, e, g)
        loaded = true
        lastLoad = Date()
    }

    func loadWeather() async {
        if let w: WeatherNow = try? await API.run("weather_now") { weather = w }
    }
    func loadElectricity() async {
        if let e: ElectricityPrice = try? await API.run("electricity_price") { electricity = e }
    }
    func loadWasher() async {
        if let w: WasherStatus = try? await API.run("washer_status") {
            washer = w
            WasherLiveActivityManager.shared.sync(machineState: w.machineState, progress: w.progress, remainingMinutes: w.remainingMinutes)
        }
    }
    func loadFridge() async {
        if let f: FridgeStatus = try? await API.run("fridge_status") { fridge = f }
    }
    func loadVent() async {
        if let v: VentStatus = try? await API.run("ventilation_status") { vent = v }
    }
    func loadTorrents() async {
        if let list: TorrentList = try? await API.run("list_torrents") { torrents = list.torrents }
    }

    func run(_ tool: String) async {
        Haptics.impact(.medium)
        do { _ = try await API.run(tool) as EmptyResult; Haptics.success() }
        catch { errorMessage = error.localizedDescription; Haptics.error() }
        await loadWasher()
    }

    func setVent(_ level: String) async {
        Haptics.impact(.medium)
        do { _ = try await API.run("ventilation_set", args: ["level": level]) as EmptyResult; Haptics.success() }
        catch { errorMessage = error.localizedDescription; Haptics.error() }
        await loadVent()
    }
}
