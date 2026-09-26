import WidgetKit
import SwiftUI

struct ExpiringEntry: TimelineEntry {
    let date: Date
    let items: [Server.ExpiringItem]
}

struct ExpiringProvider: TimelineProvider {
    func placeholder(in context: Context) -> ExpiringEntry {
        ExpiringEntry(date: Date(), items: [
            .init(name: "Milk", expiresOn: "2026-09-13", daysLeft: 1),
            .init(name: "Eggs", expiresOn: "2026-09-20", daysLeft: 8),
        ])
    }

    func getSnapshot(in context: Context, completion: @escaping (ExpiringEntry) -> Void) {
        completion(placeholder(in: context))
    }

    func getTimeline(in context: Context, completion: @escaping (Timeline<ExpiringEntry>) -> Void) {
        Task {
            let items = await Server.expiringItems()
            let entry = ExpiringEntry(date: Date(), items: items)
            let next = Calendar.current.date(byAdding: .hour, value: 1, to: Date()) ?? Date()
            completion(Timeline(entries: [entry], policy: .after(next)))
        }
    }
}

struct ExpiringWidgetView: View {
    @Environment(\.widgetFamily) private var family
    let entry: ExpiringEntry

    var body: some View {
        switch family {
        case .systemSmall: small
        default: medium
        }
    }

    private var small: some View {
        VStack(alignment: .leading, spacing: 4) {
            Image(systemName: "refrigerator.fill").foregroundStyle(.blue)
            Spacer()
            Text("\(entry.items.count)")
                .font(.system(size: 40, weight: .bold, design: .rounded))
            Text(entry.items.count == 1 ? "expiring soon" : "expiring soon")
                .font(.caption).foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private var medium: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Label("Expiring soon", systemImage: "refrigerator.fill")
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(.blue)
                Spacer()
                Text("\(entry.items.count)").font(.caption).foregroundStyle(.secondary)
            }
            if entry.items.isEmpty {
                Text("Nothing expiring in the next 7 days.")
                    .font(.caption).foregroundStyle(.secondary)
            } else {
                ForEach(entry.items.prefix(4)) { item in
                    HStack {
                        Text(item.name).lineLimit(1)
                        Spacer()
                        if let d = item.daysLeft {
                            Text(d <= 0 ? "today" : "\(d)d")
                                .font(.caption.weight(.semibold))
                                .foregroundStyle(d <= 1 ? .red : d <= 3 ? .orange : .green)
                        }
                    }
                    .font(.caption)
                }
            }
        }
    }
}

struct ExpiringWidget: Widget {
    var body: some WidgetConfiguration {
        StaticConfiguration(kind: "ExpiringWidget", provider: ExpiringProvider()) { entry in
            ExpiringWidgetView(entry: entry)
                .containerBackground(.fill.tertiary, for: .widget)
        }
        .configurationDisplayName("Expiring soon")
        .description("Fridge items expiring in the next week.")
        .supportedFamilies([.systemSmall, .systemMedium])
    }
}
