import SwiftUI
import UserNotifications

struct DevicesView: View {
    @ObservedObject var state: DeviceState
    @State private var showVent = false
    @State private var magnet = ""
    @State private var showWeather = false
    @State private var showWasher = false
    @State private var showFridge = false
    @State private var selectedHour: ElectricityHour?
    @State private var showMedia = false
    @State private var showVentSheet = false

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 14) {
                    if let errorMessage = state.errorMessage {
                        HStack(spacing: 8) {
                            Image(systemName: "exclamationmark.triangle.fill").foregroundStyle(Theme.coral)
                            Text(errorMessage).font(.footnote)
                        }
                        .padding(12)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(Theme.coral.opacity(0.12),
                                    in: RoundedRectangle(cornerRadius: 14, style: .continuous))
                    }
                    weatherCard.onTapGesture { showWeather = true }.entrance(0)
                    washerCard.onTapGesture { showWasher = true }.entrance(1)
                    fridgeCard.onTapGesture { showFridge = true }.entrance(2)
                    electricityCard.entrance(3)
                    mediaCard.entrance(4)
                    ventCard.entrance(5)
                    torrentCard.entrance(6)
                }
                .padding(.horizontal, 16)
                .padding(.top, 8)
                .padding(.bottom, 24)
            }
            .matteBackground()
            .navigationTitle("Devices")
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button { Task { await state.loadIfNeeded(force: true) } } label: { Image(systemName: "arrow.clockwise") }
                }
            }
            .task { await state.loadIfNeeded() }
            .refreshable { await state.loadIfNeeded(force: true) }
            .confirmationDialog("Fan speed", isPresented: $showVent, titleVisibility: .visible) {
                Button("Off") { Task { await state.setVent("off") } }
                Button("Low") { Task { await state.setVent("low") } }
                Button("Normal") { Task { await state.setVent("normal") } }
                Button("High") { Task { await state.setVent("high") } }
            }
            .sheet(isPresented: $showWeather) { WeatherSheet() }
            .sheet(isPresented: $showWasher) { if let washer = state.washer { WasherSheet(washer: washer) } }
            .sheet(isPresented: $showFridge) { if let fridge = state.fridge { FridgeSheet(fridge: fridge) } }
            .sheet(isPresented: $showMedia) { MediaView() }
            .sheet(isPresented: $showVentSheet) { if let vent = state.vent { VentSheet(vent: vent, onChanged: { state.vent = $0 }) } }
        }
    }

    private var washerRunning: Bool { ["run", "running", "washing"].contains(state.washer?.machineState ?? "") }

    // ── Washer ────────────────────────────────────────────────────────────────
    private var washerStateText: String {
        guard let w = state.washer else { return state.loaded ? "—" : "…" }
        if washerRunning { return "Running" }
        if w.machineState == "ready" { return "Ready" }
        return w.machineState?.capitalized ?? "—"
    }

    private var washerStateColor: Color {
        if washerRunning { return Theme.green }
        if state.washer?.machineState == "ready" { return Theme.blue }
        return .secondary
    }

    private var washerCard: some View {
        Card {
            HStack(alignment: .top, spacing: 12) {
                IconTile(systemName: "washer", colors: [Theme.blue, Theme.indigo])
                VStack(alignment: .leading, spacing: 2) {
                    Text("Washer").font(.headline)
                    if state.washer == nil && !state.loaded {
                        SkeletonTile(height: 12).frame(width: 100)
                    } else {
                        Text(washerSubtitle).font(.subheadline).foregroundStyle(.secondary)
                    }
                }
                Spacer()
                PillStatus(text: washerStateText, color: washerStateColor)
            }
            if washerRunning, let w = state.washer, let p = w.progress {
                VStack(alignment: .leading, spacing: 6) {
                    ProgressPill(progress: p / 100)
                    HStack {
                        Text("\(Int(p))%").contentTransition(.numericText())
                        Spacer()
                        if let m = w.remainingMinutes { Text("~\(m) min left\(finishSuffix(w.completionTime))") }
                    }
                    .font(.caption).foregroundStyle(.secondary)
                }
                .padding(.top, 4)
                .animation(.easeInOut(duration: 0.3), value: p)
            }
            if state.electricity?.currentCentsPerKwh != nil {
                Label("~0.9 kWh · ~\(String(format: "%.2f", washCost)) €/wash", systemImage: "bolt.badge.clock.fill")
                    .font(.caption).foregroundStyle(.secondary)
            }
            HStack(spacing: 10) {
                GlassActionButton(label: "Start", systemName: "play.fill", tint: .green) { Task { await state.run("washer_start") } }
                GlassActionButton(label: "Pause", systemName: "pause.fill", tint: .orange) { Task { await state.run("washer_pause") } }
                GlassActionButton(label: "Stop", systemName: "stop.fill", tint: .red) { Task { await state.run("washer_stop") } }
            }
        }
    }

    private var washerSubtitle: String {
        guard let w = state.washer else { return state.loaded ? "Not configured" : "Loading…" }
        if washerRunning {
            if let m = w.remainingMinutes { return "\(m) min left · \(Int(w.progress ?? 0))%" }
            return "\(Int(w.progress ?? 0))%"
        }
        var parts: [String] = []
        if let c = w.currentCycle { parts.append(c) }
        if let t = w.waterTemp { parts.append("\(t)°") }
        if let s = w.spinLevel { parts.append("\(s) rpm") }
        return parts.isEmpty ? "Ready" : parts.joined(separator: " · ")
    }

    // ── Fridge ────────────────────────────────────────────────────────────────
    private var fridgeCard: some View {
        Card {
            HStack(alignment: .top, spacing: 12) {
                IconTile(systemName: "refrigerator", colors: [Theme.cyan, Theme.blue])
                VStack(alignment: .leading, spacing: 2) {
                    Text("Fridge").font(.headline)
                    if state.fridge == nil && !state.loaded {
                        SkeletonTile(height: 12).frame(width: 100)
                    } else {
                        Text(fridgeDoorText).font(.subheadline).foregroundStyle(.secondary)
                    }
                }
                Spacer()
                if let f = state.fridge, f.fridgeDoorOpen == true { PillStatus(text: "Door open", color: .red) }
            }
            HStack(spacing: 12) {
                StatTile(label: "Fridge", value: temp(state.fridge?.fridgeTemp), symbol: "thermometer.medium", tint: Theme.cyan)
                StatTile(label: "Freezer", value: temp(state.fridge?.freezerTemp), symbol: "snowflake", tint: Theme.blue)
            }
            if let f = state.fridge, f.fridgeSetTemp != nil || f.freezerSetTemp != nil {
                HStack(spacing: 12) {
                    Label("Set \(Int(f.fridgeSetTemp ?? 0))° / \(Int(f.freezerSetTemp ?? 0))°", systemImage: "slider.horizontal.3")
                        .font(.caption).foregroundStyle(.secondary)
                    Spacer()
                    if f.superCool == true { Label("Super cool", systemImage: "snowflake").font(.caption).foregroundStyle(.cyan) }
                    if f.superFreeze == true { Label("Freeze", systemImage: "snowflake.circle").font(.caption).foregroundStyle(.blue) }
                }
            }
        }
    }

    private var fridgeDoorText: String {
        guard let f = state.fridge else { return state.loaded ? "Not configured" : "Loading…" }
        if f.fridgeDoorOpen == true { return "Fridge door open" }
        if f.freezerDoorOpen == true { return "Freezer door open" }
        return "Doors closed"
    }

    private func temp(_ v: Double?) -> String { v.map { "\(Int($0))°" } ?? "—" }

    private func finishSuffix(_ iso: String?) -> String {
        guard let iso else { return "" }
        let f = ISO8601DateFormatter()
        guard let d = f.date(from: iso) else { return "" }
        let t = DateFormatter()
        t.dateFormat = "HH:mm"
        return " · finishes \(t.string(from: d))"
    }

    // ── Weather ───────────────────────────────────────────────────────────────
    private var weatherGradient: [Color] {
        guard let c = state.weather?.condition?.lowercased() else { return [.blue, .indigo] }
        if c.contains("clear") || c.contains("sun") { return [Color(red: 1.0, green: 0.72, blue: 0.25), .pink] }
        if c.contains("snow") { return [.cyan, .blue] }
        if c.contains("rain") || c.contains("drizzle") || c.contains("shower") || c.contains("thunder") { return [.blue, .indigo] }
        if c.contains("fog") { return [.gray, .teal] }
        return [.teal, .blue]
    }

    private var weatherSymbol: String {
        guard let c = state.weather?.condition?.lowercased() else { return "cloud.sun.fill" }
        if c.contains("clear") || c.contains("sun") { return (state.weather?.isDay ?? 1) == 0 ? "moon.stars.fill" : "sun.max.fill" }
        if c.contains("partly") { return "cloud.sun.fill" }
        if c.contains("snow") { return "cloud.snow.fill" }
        if c.contains("thunder") { return "cloud.bolt.rain.fill" }
        if c.contains("rain") || c.contains("drizzle") || c.contains("shower") { return "cloud.rain.fill" }
        if c.contains("fog") { return "cloud.fog.fill" }
        return "cloud.fill"
    }

    private var weatherCard: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack {
                Label("Aadli 2 · Ülenurme", systemImage: "location.fill").font(.caption)
                Spacer()
                Text("Open-Meteo").font(.caption2).opacity(0.8)
            }
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 2) {
                    Text(state.weather.map { "\(Int($0.temperature ?? 0))°" } ?? "—")
                        .font(.system(size: 56, weight: .bold, design: .rounded))
                        .contentTransition(.numericText())
                        .animation(.spring(response: 0.5, dampingFraction: 0.8), value: state.weather?.temperature)
                    if state.weather == nil && !state.loaded {
                        SkeletonTile(height: 12).frame(width: 110)
                    } else {
                        Text(state.weather?.condition?.capitalized ?? "Not configured")
                            .font(.subheadline)
                    }
                }
                Spacer()
                Image(systemName: weatherSymbol)
                    .font(.system(size: 46))
                    .symbolRenderingMode(.multicolor)
            }
            if let w = state.weather {
                HStack {
                    weatherStat("High", "\(Int(w.tempMax ?? 0))°")
                    Spacer()
                    weatherStat("Low", "\(Int(w.tempMin ?? 0))°")
                    Spacer()
                    weatherStat("Feels", "\(Int(w.feelsLike ?? 0))°")
                    Spacer()
                    weatherStat("Humidity", "\(w.humidity ?? 0)%")
                    Spacer()
                    weatherStat("Wind", "\(Int(w.windKmh ?? 0)) km/h")
                }
            }
        }
        .foregroundStyle(.white)
        .padding(18)
        .background(LinearGradient(colors: weatherGradient, startPoint: .topLeading, endPoint: .bottomTrailing),
                    in: RoundedRectangle(cornerRadius: 20, style: .continuous))
        .onTapGesture { showWeather = true }
    }

    private func weatherStat(_ label: String, _ value: String) -> some View {
        VStack(spacing: 2) {
            Text(value).font(.subheadline.weight(.semibold))
            Text(label).font(.caption2).opacity(0.85)
        }
    }

    // ── Electricity ───────────────────────────────────────────────────────────
    private var electricityCard: some View {
        Card {
            VStack(alignment: .leading, spacing: 14) {
                HStack(spacing: 12) {
                    IconTile(systemName: "bolt.fill", colors: [Theme.yellow, Theme.amber])
                    VStack(alignment: .leading, spacing: 1) {
                        Text("Electricity").font(.headline).tracking(-0.01)
                        Text("Nord Pool · Estonia").font(.caption).foregroundStyle(.secondary)
                    }
                    Spacer()
                    VStack(alignment: .trailing, spacing: 0) {
                        Text(state.electricity.map { String(format: "%.1f", $0.currentCentsPerKwh ?? 0) } ?? "—")
                            .font(.system(size: 28, weight: .bold, design: .rounded))
                            .contentTransition(.numericText())
                            .animation(.spring(response: 0.5, dampingFraction: 0.8), value: state.electricity?.currentCentsPerKwh)
                        Text("¢/kWh now").font(.caption2).foregroundStyle(.secondary)
                    }
                }

                if let e = state.electricity, let hours = e.upcomingHours, !hours.isEmpty {
                    VStack(alignment: .leading, spacing: 6) {
                        HStack {
                            Text("Next 24 hours").font(.caption2).foregroundStyle(.secondary)
                            Spacer()
                            if let sh = selectedHour {
                                Text("\(sh.hour) · \(String(format: "%.1f", sh.price))¢")
                                    .font(.caption2.weight(.semibold))
                            }
                        }
                        HStack(alignment: .bottom, spacing: 2) {
                            ForEach(hours) { h in
                                RoundedRectangle(cornerRadius: 2)
                                    .fill(priceColor(h.price))
                                    .frame(height: max(4, CGFloat(h.price / (hours.map(\.price).max() ?? 1)) * 64))
                                    .opacity(selectedHour?.id == h.id ? 1 : 0.7)
                                    .overlay(selectedHour?.id == h.id ? RoundedRectangle(cornerRadius: 2).stroke(Color.primary, lineWidth: 1) : nil)
                                    .onTapGesture { withAnimation(.spring(response: 0.3, dampingFraction: 0.8)) { selectedHour = h }; Haptics.selection() }
                            }
                        }
                        .frame(height: 66, alignment: .bottom)
                        HStack(spacing: 0) {
                            Text(hours.first?.hour ?? "").font(.caption2).foregroundStyle(.secondary)
                            Spacer()
                            Text(hourLabel(hours, 6)).font(.caption2).foregroundStyle(.secondary)
                            Spacer()
                            Text(hourLabel(hours, 12)).font(.caption2).foregroundStyle(.secondary)
                            Spacer()
                            Text(hourLabel(hours, 18)).font(.caption2).foregroundStyle(.secondary)
                            Spacer()
                            Text(hours.last?.hour ?? "").font(.caption2).foregroundStyle(.secondary)
                        }
                    }

                    HStack(spacing: 8) {
                        statChip("Today", "\(String(format: "%.1f", e.todayMin ?? 0))–\(String(format: "%.1f", e.todayMax ?? 0))¢", .gray)
                        statChip("Tomorrow", "\(String(format: "%.1f", e.tomorrowMin ?? 0))–\(String(format: "%.1f", e.tomorrowMax ?? 0))¢", .blue)
                        statChip("Avg", "\(String(format: "%.1f", e.todayAvg ?? 0))¢", .orange)
                    }

                    if state.washer != nil, !washerRunning, let ch = e.cheapestHours?.first {
                        HStack(spacing: 10) {
                            Image(systemName: "washer").font(.system(size: 20)).foregroundStyle(.blue)
                            VStack(alignment: .leading, spacing: 1) {
                                Text("Cheapest: \(ch.hour) · \(String(format: "%.1f", ch.price))¢")
                                    .font(.caption.weight(.semibold))
                                Text("a wash ≈ \(String(format: "%.2f", washCost)) €").font(.caption2).foregroundStyle(.secondary)
                            }
                            Spacer()
                            Button { scheduleCheapest() } label: {
                                Label("Schedule", systemImage: "clock.badge.checkmark").font(.caption.weight(.semibold))
                            }
                            .buttonStyle(.bordered).buttonBorderShape(.capsule).tint(.green)
                            .controlSize(.small)
                        }
                        .padding(10)
                        .background(Color.green.opacity(0.12), in: RoundedRectangle(cornerRadius: 14, style: .continuous))
                    }
                }
            }
        }
    }

    private func statChip(_ label: String, _ value: String, _ tint: Color) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(label).font(.caption2).foregroundStyle(.secondary)
            Text(value).font(.caption.weight(.semibold)).lineLimit(1).minimumScaleFactor(0.8)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(8)
        .background(tint.opacity(0.12), in: RoundedRectangle(cornerRadius: 10, style: .continuous))
    }

    private var washCost: Double {
        0.9 * (state.electricity?.currentCentsPerKwh ?? 0) / 100
    }

    private func scheduleCheapest() {
        guard let ch = state.electricity?.cheapestHours?.first,
              let hh = Int(ch.hour.prefix(2)) else { return }
        let cal = Calendar.current
        var date = cal.date(bySettingHour: hh, minute: 0, second: 0, of: Date()) ?? Date()
        if date <= Date() { date = cal.date(byAdding: .day, value: 1, to: date) ?? date }
        let fire = date.addingTimeInterval(-5 * 60)

        UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound]) { granted, _ in
            guard granted else { return }
            let content = UNMutableNotificationContent()
            content.title = "Odav elekter 🧺"
            content.body = "Cheapest electricity at \(ch.hour) (\(String(format: "%.1f", ch.price))¢/kWh). Start the washer?"
            content.sound = .default
            let comps = cal.dateComponents([.year, .month, .day, .hour, .minute], from: fire)
            let trigger = UNCalendarNotificationTrigger(dateMatching: comps, repeats: false)
            let req = UNNotificationRequest(identifier: "washer-cheapest", content: content, trigger: trigger)
            UNUserNotificationCenter.current().removePendingNotificationRequests(withIdentifiers: ["washer-cheapest"])
            UNUserNotificationCenter.current().add(req) { _ in
                DispatchQueue.main.async { Haptics.success() }
            }
        }
    }

    private func priceColor(_ p: Double) -> Color {
        if p < 6 { return Theme.green }
        if p < 12 { return Theme.yellow }
        if p < 20 { return Theme.amber }
        return Theme.red
    }

    private func hourLabel(_ hours: [ElectricityHour], _ index: Int) -> String {
        hours.indices.contains(index) ? hours[index].hour : ""
    }

    // ── Media library (Jellyfin) ────────────────────────────────────────────
    private var mediaCard: some View {
        Card {
            HStack(spacing: 12) {
                IconTile(systemName: "film.stack.fill", colors: [Theme.indigo, Theme.purple])
                VStack(alignment: .leading, spacing: 2) {
                    Text("Media library").font(.headline)
                    Text("Jellyfin").font(.subheadline).foregroundStyle(.secondary)
                }
                Spacer()
                Image(systemName: "chevron.right").font(.caption).foregroundStyle(.secondary)
            }
        }
        .onTapGesture { showMedia = true }
    }

    // ── Ventilation ───────────────────────────────────────────────────────────
    private var ventCard: some View {
        Card {
            HStack(alignment: .top, spacing: 12) {
                IconTile(systemName: "fan", colors: [Theme.amber, Theme.coral])
                VStack(alignment: .leading, spacing: 2) {
                    Text("Ventilation").font(.headline)
                    if state.vent == nil && !state.loaded {
                        SkeletonTile(height: 12).frame(width: 100)
                    } else {
                        Text(state.vent == nil ? "Not configured" : (state.vent?.userMode?.capitalized ?? "—"))
                            .font(.subheadline).foregroundStyle(.secondary)
                    }
                }
                Spacer()
                Button { showVent = true } label: {
                    Label("Boost", systemImage: "wind").font(.caption.weight(.semibold))
                }
                .buttonStyle(.bordered)
                .buttonBorderShape(.capsule)
                .tint(.orange)
            }
            HStack(spacing: 12) {
                StatTile(label: "Airflow", value: state.vent?.airflow ?? "—", symbol: "wind", tint: Theme.amber)
                StatTile(label: "CO₂", value: state.vent.map { "\($0.co2 ?? 0) ppm" } ?? "—", symbol: "aqi.medium", tint: Theme.coral)
            }
            if let v = state.vent {
                HStack(spacing: 12) {
                    Label("\(temp(v.supplyTemp)) supply", systemImage: "thermometer.medium").font(.caption).foregroundStyle(.secondary)
                    Spacer()
                    if let d = v.filterDaysLeft { Label("Filter \(d)d", systemImage: "line.3.horizontal.decrease.circle").font(.caption).foregroundStyle(.secondary) }
                }
            }
        }
        .onTapGesture { showVentSheet = true }
    }

    // ── Torrents ──────────────────────────────────────────────────────────────
    private var torrentCard: some View {
        Card {
            HStack(alignment: .top, spacing: 12) {
                IconTile(systemName: "arrow.down.circle.fill", colors: [Theme.purple, Theme.blue])
                VStack(alignment: .leading, spacing: 2) {
                    Text("Downloads").font(.headline)
                    Text(state.torrents.isEmpty ? "No active torrents" : "\(state.torrents.count) active")
                        .font(.subheadline).foregroundStyle(.secondary)
                }
                Spacer()
            }
            ForEach(state.torrents) { t in
                VStack(alignment: .leading, spacing: 5) {
                    HStack {
                        Text(t.name).font(.subheadline).lineLimit(1)
                        Spacer()
                        Text("\(Int(t.progress))%").font(.caption).foregroundStyle(.secondary)
                    }
                    ProgressView(value: t.progress / 100).tint(.purple)
                    Text(t.status).font(.caption2).foregroundStyle(.secondary)
                }
                .padding(.vertical, 4)
            }
            HStack(spacing: 10) {
                TextField("Paste magnet link…", text: $magnet)
                    .font(.subheadline)
                    .padding(.horizontal, 12).padding(.vertical, 10)
                    .background(Color(.tertiarySystemGroupedBackground), in: Capsule())
                Button("Add") {
                    guard !magnet.isEmpty else { return }
                    Task {
                        _ = try? await API.run("add_torrent", args: ["magnet_uri": magnet]) as AddResult
                        magnet = ""
                        await state.loadTorrents()
                    }
                }
                .buttonStyle(.borderedProminent).buttonBorderShape(.capsule).disabled(magnet.isEmpty)
            }
        }
    }
}

// Shared decodable helpers for tool calls that return non-empty data.
struct EmptyResult: Decodable {}
struct AddResult: Decodable { var name: String?; var ok: Bool?; var itemId: Int? }
struct RemoveResult: Decodable { var removed: Bool?; var itemId: Int? }

struct WasherSheet: View {
    let washer: WasherStatus
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            List {
                Section("State") {
                    LabeledContent("Status", value: washer.machineState?.capitalized ?? "—")
                    LabeledContent("Job", value: washer.jobState ?? "—")
                    if let p = washer.progress { LabeledContent("Progress", value: "\(Int(p))%") }
                    if let m = washer.remainingMinutes { LabeledContent("Remaining", value: "\(m) min") }
                    if let c = washer.completionTime { LabeledContent("Finished", value: String(c.prefix(16))) }
                }
                Section("Cycle") {
                    LabeledContent("Program", value: washer.currentCycle ?? "—")
                    LabeledContent("Water temp", value: washer.waterTemp.map { "\($0)°" } ?? "—")
                    LabeledContent("Spin", value: washer.spinLevel.map { "\($0) rpm" } ?? "—")
                    LabeledContent("Rinses", value: washer.rinseCycles ?? "—")
                    LabeledContent("Dry level", value: washer.dryLevel ?? "—")
                }
                if let jobs = washer.scheduledJobs, !jobs.isEmpty {
                    Section("Phases") {
                        ForEach(jobs, id: \.jobName) { j in
                            LabeledContent(j.jobName?.capitalized ?? "?", value: "\(j.timeInMin ?? 0) min")
                        }
                    }
                }
                Section("Control") {
                    LabeledContent("Power", value: washer.powerSwitch ?? "—")
                    LabeledContent("Remote control", value: washer.remoteControlEnabled == "true" ? "On" : "Off")
                }
            }
            .navigationTitle("Washer")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .topBarTrailing) { Button("Done") { dismiss() } } }
        }
    }
}

struct FridgeSheet: View {
    let fridge: FridgeStatus
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            List {
                Section("Temperatures") {
                    LabeledContent("Fridge", value: "\(Int(fridge.fridgeTemp ?? 0))°")
                    LabeledContent("Freezer", value: "\(Int(fridge.freezerTemp ?? 0))°")
                    LabeledContent("Fridge target", value: "\(Int(fridge.fridgeSetTemp ?? 0))°")
                    LabeledContent("Freezer target", value: "\(Int(fridge.freezerSetTemp ?? 0))°")
                }
                Section("Status") {
                    LabeledContent("Connection", value: fridge.connected == true ? "Connected" : "Offline")
                    LabeledContent("Fridge door", value: fridge.fridgeDoorOpen == true ? "Open" : "Closed")
                    LabeledContent("Freezer door", value: fridge.freezerDoorOpen == true ? "Open" : "Closed")
                    LabeledContent("Super cool", value: fridge.superCool == true ? "On" : "Off")
                    LabeledContent("Super freeze", value: fridge.superFreeze == true ? "On" : "Off")
                    LabeledContent("Power", value: fridge.on == true ? "On" : "Off")
                }
            }
            .navigationTitle("Fridge")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .topBarTrailing) { Button("Done") { dismiss() } } }
        }
    }
}

struct WeatherSheet: View {
    @State private var forecast: WeatherForecast?
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            Group {
                if let f = forecast {
                    List(f.days) { day in
                        HStack {
                            Text(shortDate(day.date)).font(.subheadline.weight(.semibold)).frame(width: 46, alignment: .leading)
                            Text(day.condition?.capitalized ?? "").font(.caption).foregroundStyle(.secondary)
                            Spacer()
                            Text("\(Int(day.max ?? 0))° / \(Int(day.min ?? 0))°").font(.subheadline.weight(.semibold))
                            if let p = day.precipProb, p > 0 {
                                Text("\(p)%").font(.caption).foregroundStyle(.blue).frame(width: 40, alignment: .trailing)
                            }
                        }
                    }
                } else {
                    ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity)
                }
            }
            .navigationTitle("Forecast")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .topBarTrailing) { Button("Done") { dismiss() } } }
            .task { forecast = try? await API.run("weather_forecast", args: ["days": 7]) }
        }
    }

    private func shortDate(_ iso: String?) -> String {
        guard let iso else { return "—" }
        let f = DateFormatter(); f.dateFormat = "yyyy-MM-dd"
        if let d = f.date(from: iso) { f.dateFormat = "EEE"; return f.string(from: d) }
        return String(iso.prefix(10))
    }
}

struct VentSheet: View {
    let vent: VentStatus
    var onChanged: (VentStatus) -> Void = { _ in }
    @Environment(\.dismiss) private var dismiss
    @State private var status: VentStatus

    init(vent: VentStatus, onChanged: @escaping (VentStatus) -> Void = { _ in }) {
        self.vent = vent
        self.onChanged = onChanged
        _status = State(initialValue: vent)
    }

    var body: some View {
        NavigationStack {
            List {
                Section("Temperatures") {
                    LabeledContent("Supply", value: temp(status.supplyTemp))
                    LabeledContent("Extract", value: temp(status.extractTemp))
                    LabeledContent("Setpoint", value: temp(status.tempSetpoint))
                }
                Section("Air quality") {
                    LabeledContent("Humidity", value: status.humidity.map { "\($0)%" } ?? "—")
                    LabeledContent("CO₂", value: status.co2.map { "\($0) ppm" } ?? "—")
                    LabeledContent("Airflow", value: status.airflow ?? "—")
                    LabeledContent("Mode", value: status.userMode ?? "—")
                }
                Section("Fan speed") {
                    HStack {
                        ForEach(["off", "low", "normal", "high"], id: \.self) { lvl in
                            Button(lvl.capitalized) { Task { await set(lvl) } }
                                .buttonStyle(.bordered).buttonBorderShape(.capsule)
                        }
                    }
                }
                Section("Mode") {
                    ForEach(["auto", "manual", "away", "holiday", "crowded", "refresh"], id: \.self) { m in
                        Button(m.capitalized) { Task { await set(m) } }
                    }
                }
                if let d = status.filterDaysLeft {
                    Section("Filter") { LabeledContent("Life left", value: "\(d) days") }
                }
            }
            .navigationTitle("Ventilation")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .topBarTrailing) { Button("Done") { dismiss() } } }
        }
    }

    private func temp(_ v: Double?) -> String { v.map { "\(Int($0))°" } ?? "—" }

    private func set(_ value: String) async {
        _ = try? await API.run("ventilation_set", args: ["level": value]) as EmptyResult
        if let s: VentStatus = try? await API.run("ventilation_status") { status = s; onChanged(s) }
    }
}
