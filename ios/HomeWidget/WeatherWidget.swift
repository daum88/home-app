import WidgetKit
import SwiftUI

struct WeatherEntry: TimelineEntry {
    let date: Date
    let weather: Server.WeatherNow?
}

struct WeatherProvider: TimelineProvider {
    func placeholder(in context: Context) -> WeatherEntry {
        WeatherEntry(date: Date(), weather: .init(temperature: 15, condition: "clear sky", isDay: 1, tempMax: 20, tempMin: 8))
    }

    func getSnapshot(in context: Context, completion: @escaping (WeatherEntry) -> Void) {
        completion(placeholder(in: context))
    }

    func getTimeline(in context: Context, completion: @escaping (Timeline<WeatherEntry>) -> Void) {
        Task {
            let weather = await Server.weather()
            let entry = WeatherEntry(date: Date(), weather: weather)
            let next = Calendar.current.date(byAdding: .minute, value: 30, to: Date()) ?? Date()
            completion(Timeline(entries: [entry], policy: .after(next)))
        }
    }
}

struct WeatherWidgetView: View {
    @Environment(\.widgetFamily) private var family
    let entry: WeatherEntry

    var body: some View {
        switch family {
        case .systemSmall: small
        default: medium
        }
    }

    private var small: some View {
        VStack(alignment: .leading, spacing: 2) {
            Label("Ülenurme", systemImage: "location.fill").font(.caption2).foregroundStyle(.secondary)
            Spacer()
            Image(systemName: symbol).font(.system(size: 28)).symbolRenderingMode(.multicolor)
            Text("\(Int(entry.weather?.temperature ?? 0))°")
                .font(.system(size: 42, weight: .bold, design: .rounded))
            Text(entry.weather?.condition?.capitalized ?? "—").font(.caption).foregroundStyle(.secondary).lineLimit(1)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private var medium: some View {
        VStack(alignment: .leading, spacing: 6) {
            Label("Ülenurme", systemImage: "location.fill").font(.caption).foregroundStyle(.secondary)
            Spacer()
            HStack(alignment: .center, spacing: 14) {
                Image(systemName: symbol).font(.system(size: 34)).symbolRenderingMode(.multicolor)
                Text("\(Int(entry.weather?.temperature ?? 0))°")
                    .font(.system(size: 40, weight: .bold, design: .rounded))
                Spacer()
                VStack(alignment: .trailing, spacing: 3) {
                    Text(entry.weather?.condition?.capitalized ?? "—").font(.caption).foregroundStyle(.secondary)
                    Text("H \(Int(entry.weather?.tempMax ?? 0))°   L \(Int(entry.weather?.tempMin ?? 0))°")
                        .font(.caption.weight(.semibold))
                }
            }
        }
    }

    private var symbol: String {
        let c = entry.weather?.condition?.lowercased() ?? ""
        if c.contains("clear") || c.contains("sun") { return (entry.weather?.isDay ?? 1) == 0 ? "moon.stars.fill" : "sun.max.fill" }
        if c.contains("partly") { return "cloud.sun.fill" }
        if c.contains("snow") { return "cloud.snow.fill" }
        if c.contains("thunder") { return "cloud.bolt.rain.fill" }
        if c.contains("rain") || c.contains("drizzle") || c.contains("shower") { return "cloud.rain.fill" }
        if c.contains("fog") { return "cloud.fog.fill" }
        return "cloud.fill"
    }
}

struct WeatherWidget: Widget {
    var body: some WidgetConfiguration {
        StaticConfiguration(kind: "WeatherWidget", provider: WeatherProvider()) { entry in
            WeatherWidgetView(entry: entry)
                .containerBackground(.fill.tertiary, for: .widget)
        }
        .configurationDisplayName("Weather")
        .description("Current weather at home.")
        .supportedFamilies([.systemSmall, .systemMedium])
    }
}
