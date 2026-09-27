import SwiftUI

struct SpendingView: View {
    @Environment(\.dismiss) private var dismiss
    @State private var stats: SpendingStats?

    var body: some View {
        NavigationStack {
            List {
                if let stats {
                    if !stats.monthly.isEmpty {
                        Section("Monthly") {
                            monthlyChart(stats.monthly)
                                .frame(maxWidth: .infinity)
                            if let m = stats.monthly.last {
                                HStack {
                                    Text("This month")
                                    Spacer()
                                    Text(String(format: "%.2f €", m.total)).font(.headline).contentTransition(.numericText())
                                }
                            }
                        }
                    }
                    if let stores = stats.stores, !stores.isEmpty {
                        Section("By store") {
                            ForEach(stores) { s in
                                HStack {
                                    Text(s.store)
                                    Spacer()
                                    Text(String(format: "%.2f €", s.total)).fontWeight(.semibold)
                                    Text("(\(s.count))").font(.caption).foregroundStyle(.secondary)
                                }
                            }
                        }
                    }
                    if let recent = stats.recent, !recent.isEmpty {
                        Section("Recent") {
                            ForEach(recent) { r in
                                HStack {
                                    VStack(alignment: .leading, spacing: 2) {
                                        Text(r.store ?? "Receipt").font(.subheadline)
                                        if let d = r.receiptDate { Text(d).font(.caption).foregroundStyle(.secondary) }
                                    }
                                    Spacer()
                                    Text(String(format: "%.2f €", r.total ?? 0)).font(.subheadline.weight(.semibold))
                                }
                            }
                        }
                    }
                } else {
                    ContentUnavailableView("No receipts yet", systemImage: "chart.bar",
                                           description: Text("Import a Coop receipt to start tracking spending."))
                }
            }
            .navigationTitle("Spending")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .topBarTrailing) { Button("Done") { dismiss() } } }
            .task { stats = try? await API.run("spending_stats") }
        }
    }

    private func monthlyChart(_ monthly: [SpendingMonth]) -> some View {
        let maxTotal = max(monthly.map(\.total).max() ?? 1, 1)
        return HStack(alignment: .bottom, spacing: 12) {
            ForEach(monthly) { m in
                VStack(spacing: 4) {
                    Text(String(format: "%.0f€", m.total)).font(.caption2).foregroundStyle(.secondary)
                    RoundedRectangle(cornerRadius: 4)
                        .fill(Theme.copper)
                        .frame(width: 34, height: max(6, CGFloat(m.total / maxTotal) * 100))
                    Text(monthLabel(m.month)).font(.caption2).foregroundStyle(.secondary)
                }
            }
        }
        .frame(height: 160, alignment: .bottom)
    }

    private func monthLabel(_ iso: String) -> String {
        let names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        let parts = iso.split(separator: "-")
        guard parts.count == 2, let idx = Int(parts[1]), (1...12).contains(idx) else { return iso }
        return names[idx - 1]
    }
}
