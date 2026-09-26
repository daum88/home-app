import WidgetKit
import SwiftUI

struct ElectricityEntry: TimelineEntry {
    let date: Date
    let electricity: Server.Electricity?
}

struct ElectricityProvider: TimelineProvider {
    func placeholder(in context: Context) -> ElectricityEntry {
        ElectricityEntry(date: Date(), electricity: .init(currentCentsPerKwh: 12.5, todayMin: 4, todayMax: 22, todayHours: []))
    }

    func getSnapshot(in context: Context, completion: @escaping (ElectricityEntry) -> Void) {
        completion(placeholder(in: context))
    }

    func getTimeline(in context: Context, completion: @escaping (Timeline<ElectricityEntry>) -> Void) {
        Task {
            let electricity = await Server.electricity()
            let entry = ElectricityEntry(date: Date(), electricity: electricity)
            let next = Calendar.current.date(byAdding: .minute, value: 30, to: Date()) ?? Date()
            completion(Timeline(entries: [entry], policy: .after(next)))
        }
    }
}

struct ElectricityWidgetView: View {
    @Environment(\.widgetFamily) private var family
    let entry: ElectricityEntry

    var body: some View {
        switch family {
        case .systemSmall: small
        default: medium
        }
    }

    private var small: some View {
        VStack(alignment: .leading, spacing: 2) {
            Label("Electricity", systemImage: "bolt.fill").font(.caption2).foregroundStyle(.yellow)
            Spacer()
            Text(String(format: "%.1f", entry.electricity?.currentCentsPerKwh ?? 0))
                .font(.system(size: 42, weight: .bold, design: .rounded))
            Text("¢/kWh now").font(.caption).foregroundStyle(.secondary)
            if let mn = entry.electricity?.todayMin, let mx = entry.electricity?.todayMax {
                Text("\(String(format: "%.0f", mn))–\(String(format: "%.0f", mx))¢ today")
                    .font(.caption).foregroundStyle(.secondary)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private var medium: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Label("Electricity", systemImage: "bolt.fill").font(.subheadline.weight(.semibold)).foregroundStyle(.yellow)
                Spacer()
                Text(String(format: "%.1f¢", entry.electricity?.currentCentsPerKwh ?? 0))
                    .font(.subheadline.weight(.bold))
            }
            if let hours = entry.electricity?.todayHours, !hours.isEmpty {
                HStack(alignment: .bottom, spacing: 2) {
                    ForEach(hours, id: \.hour) { h in
                        RoundedRectangle(cornerRadius: 1.5)
                            .fill(priceColor(h.price))
                            .frame(height: max(3, CGFloat(h.price / (hours.map(\.price).max() ?? 1)) * 40))
                    }
                }
                .frame(height: 42, alignment: .bottom)
            }
            Spacer()
            if let mn = entry.electricity?.todayMin, let mx = entry.electricity?.todayMax {
                Text("Today: \(String(format: "%.0f", mn))¢ min · \(String(format: "%.0f", mx))¢ max")
                    .font(.caption).foregroundStyle(.secondary)
            }
        }
    }

    private func priceColor(_ p: Double) -> Color {
        if p < 6 { return .green }
        if p < 12 { return .yellow }
        if p < 20 { return .orange }
        return .red
    }
}

struct ElectricityWidget: Widget {
    var body: some WidgetConfiguration {
        StaticConfiguration(kind: "ElectricityWidget", provider: ElectricityProvider()) { entry in
            ElectricityWidgetView(entry: entry)
                .containerBackground(.fill.tertiary, for: .widget)
        }
        .configurationDisplayName("Electricity")
        .description("Current electricity price and today's range.")
        .supportedFamilies([.systemSmall, .systemMedium])
    }
}
