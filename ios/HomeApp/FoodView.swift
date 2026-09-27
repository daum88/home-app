import SwiftUI

/// Food dashboard: what's in the fridge, what's expiring, and what's needed.
/// Full inventory / shopping / recipes / spending open from here.
struct FoodView: View {
    @State private var items: [FridgeItem] = []
    @State private var suggested: [RecipeSuggestion] = []
    @State private var quickAdd = ""
    @State private var showFridge = false
    @State private var showShopping = false
    @State private var showRecipes = false
    @State private var showSpending = false
    @State private var showScanner = false

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 22) {
                    header
                    if !expiringSoon.isEmpty {
                        expiringSection.entrance(0)
                    }
                    fridgeOverview.entrance(1)
                    shoppingQuickAdd.entrance(2)
                    shortcuts.entrance(3)
                    if !suggested.isEmpty {
                        suggestionsSection.entrance(4)
                    }
                }
                .padding(16)
                .padding(.bottom, 24)
            }
            .matteBackground()
            .navigationTitle("Food")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button { showScanner = true } label: {
                        Image(systemName: "barcode.viewfinder")
                    }
                }
            }
        }
        .task { await load() }
        .refreshable { await load() }
        .sheet(isPresented: $showFridge) { FridgeView() }
        .sheet(isPresented: $showShopping) { ShoppingView() }
        .sheet(isPresented: $showRecipes) { RecipesView() }
        .sheet(isPresented: $showSpending) { SpendingView() }
        .sheet(isPresented: $showScanner) { BarcodeScanSheet { await load() } }
    }

    // ── Header ──────────────────────────────────────────────────────────────
    private var header: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("Food")
                .font(.display(30))
                .foregroundStyle(Theme.ink)
            Text("What's in the fridge and what you need.")
                .font(.subheadline)
                .foregroundStyle(.secondary)
        }
    }

    // ── Expiring soon ───────────────────────────────────────────────────────
    private var expiringSoon: [FridgeItem] {
        items.filter {
            guard let exp = $0.expiresOn, let d = daysLeft(exp) else { return false }
            return d <= 3
        }
        .sorted { ($0.expiresOn ?? "9999") < ($1.expiresOn ?? "9999") }
    }

    private var expiringSection: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Expiring soon").font(.headline).foregroundStyle(Theme.ink)
            ForEach(expiringSoon.prefix(5)) { item in
                HStack(spacing: 12) {
                    RowIcon(systemName: icon(for: item.position), tint: tint(for: item.position))
                    VStack(alignment: .leading, spacing: 2) {
                        Text(item.name).font(.subheadline.weight(.medium)).lineLimit(1)
                        Text(expiryLabel(item.expiresOn)).font(.caption).foregroundStyle(.secondary)
                    }
                    Spacer()
                    expiryBadge(item.expiresOn)
                }
                .padding(12)
                .background(Theme.surface, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
            }
        }
    }

    // ── Fridge overview ─────────────────────────────────────────────────────
    private var fridgeOverview: some View {
        HStack(spacing: 12) {
            overviewTile("Fridge", count: count(in: "fridge"), symbol: "refrigerator.fill", tint: Theme.teal)
            overviewTile("Freezer", count: count(in: "freezer"), symbol: "snowflake", tint: Theme.copper)
            overviewTile("Pantry", count: count(in: "pantry"), symbol: "cabinet.fill", tint: Theme.ink)
        }
    }

    private func overviewTile(_ label: String, count: Int, symbol: String, tint: Color) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Image(systemName: symbol).font(.subheadline.weight(.semibold)).foregroundStyle(tint)
            Text("\(count)").font(.system(size: 26, weight: .bold, design: .rounded)).monospacedDigit()
                .foregroundStyle(Theme.ink)
            Text(label).font(.caption).foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(14)
        .background(Theme.surface, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
    }

    // ── Shopping quick-add ──────────────────────────────────────────────────
    private var shoppingQuickAdd: some View {
        HStack(spacing: 10) {
            TextField("Add to shopping list…", text: $quickAdd)
                .padding(.horizontal, 14).padding(.vertical, 11)
                .background(Theme.canvas, in: RoundedRectangle(cornerRadius: 13, style: .continuous))
                .onSubmit { addToShopping() }
            Button { addToShopping() } label: {
                Image(systemName: "plus")
                    .font(.system(size: 16, weight: .semibold))
                    .foregroundStyle(.white)
                    .frame(width: 44, height: 44)
                    .background(Theme.teal, in: Circle())
            }
            .disabled(quickAdd.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
        }
    }

    // ── Shortcuts grid ──────────────────────────────────────────────────────
    private var shortcuts: some View {
        HStack(spacing: 12) {
            shortcutTile("Fridge", "refrigerator.fill", Theme.teal) { showFridge = true }
            shortcutTile("Shopping", "cart.fill", Theme.copper) { showShopping = true }
            shortcutTile("Recipes", "fork.knife", Theme.ink) { showRecipes = true }
            shortcutTile("Spending", "chart.bar.fill", Theme.teal) { showSpending = true }
        }
    }

    private func shortcutTile(_ label: String, _ symbol: String, _ tint: Color, action: @escaping () -> Void) -> some View {
        Button { Haptics.impact(); action() } label: {
            VStack(spacing: 8) {
                Image(systemName: symbol).font(.title3).foregroundStyle(tint)
                Text(label).font(.caption.weight(.medium)).foregroundStyle(Theme.ink)
            }
            .frame(maxWidth: .infinity)
            .padding(.vertical, 16)
            .background(Theme.surface, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
        }
        .buttonStyle(PressableButtonStyle())
    }

    // ── Recipe suggestions ──────────────────────────────────────────────────
    private var suggestionsSection: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Recipe ideas").font(.headline).foregroundStyle(Theme.ink)
            ForEach(suggested.prefix(3)) { rec in
                HStack(spacing: 12) {
                    VStack(alignment: .leading, spacing: 2) {
                        Text(rec.name).font(.subheadline.weight(.medium)).lineLimit(1)
                        Text([rec.category, rec.area].compactMap { $0 }.joined(separator: " · "))
                            .font(.caption).foregroundStyle(.secondary)
                    }
                    Spacer()
                    Button("Save") {
                        Task {
                            _ = try? await API.run("save_recipe", args: ["meal_id": rec.id]) as AddResult
                            Haptics.success()
                        }
                    }
                    .buttonStyle(.bordered).buttonBorderShape(.capsule).tint(Theme.teal)
                    .controlSize(.small)
                }
                .padding(12)
                .background(Theme.surface, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
            }
        }
    }

    // ── Helpers ─────────────────────────────────────────────────────────────
    private func load() async {
        if let inv: FridgeInventory = try? await API.run("fridge_inventory_list") {
            items = inv.items
        }
        if let r: RecipeSuggestions = try? await API.run("suggest_recipes") {
            suggested = r.recipes
        }
    }

    private func addToShopping() {
        let name = quickAdd.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !name.isEmpty else { return }
        Haptics.impact(.light)
        quickAdd = ""
        Task { _ = try? await API.run("shopping_add", args: ["name": name]) as EmptyResult }
    }

    private func count(in position: String) -> Int {
        items.filter { ($0.position ?? "fridge") == position }.count
    }

    private func icon(for position: String?) -> String {
        switch position {
        case "freezer": return "snowflake"
        case "pantry": return "cabinet.fill"
        default: return "refrigerator.fill"
        }
    }

    private func tint(for position: String?) -> Color {
        switch position {
        case "freezer": return Theme.copper
        case "pantry": return Theme.ink
        default: return Theme.teal
        }
    }

    private func daysLeft(_ iso: String) -> Int? {
        let f = DateFormatter(); f.dateFormat = "yyyy-MM-dd"
        guard let d = f.date(from: String(iso.prefix(10))) else { return nil }
        return Calendar.current.dateComponents([.day], from: Calendar.current.startOfDay(for: .now), to: d).day
    }

    private func expiryLabel(_ iso: String?) -> String {
        guard let iso, let d = daysLeft(iso) else { return "" }
        if d < 0 { return "expired" }
        if d == 0 { return "today" }
        return "in \(d) days"
    }

    @ViewBuilder private func expiryBadge(_ iso: String?) -> some View {
        if let iso, let d = daysLeft(iso) {
            let color: Color = d < 0 ? Theme.danger : d <= 1 ? Theme.danger : d <= 3 ? Theme.warning : Theme.success
            Text(d < 0 ? "expired" : d == 0 ? "today" : "\(d)d")
                .font(.caption.weight(.semibold))
                .foregroundStyle(color)
                .padding(.horizontal, 9).padding(.vertical, 4)
                .background(color.opacity(0.12), in: Capsule())
        }
    }
}
