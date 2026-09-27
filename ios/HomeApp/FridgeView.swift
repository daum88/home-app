import SwiftUI
import AVFoundation
import UniformTypeIdentifiers

struct FridgeView: View {
    @State private var items: [FridgeItem] = []
    @State private var loading = true
    @State private var showAdd = false
    @State private var showScanner = false
    @State private var showImport = false
    @State private var showHonImport = false
    @State private var undoItem: FridgeItem?
    @State private var errorMessage: String?
    @State private var loadError: String?
    @State private var showSpending = false
    @State private var searchText = ""
    @State private var selectedItem: FridgeItem?

    var body: some View {
        NavigationStack {
            Group {
                if loading && items.isEmpty {
                    ProgressView("Loading fridge…").frame(maxWidth: .infinity, maxHeight: .infinity)
                } else if let loadError, items.isEmpty {
                    VStack(spacing: 12) {
                        ContentUnavailableView("Couldn't load fridge", systemImage: "wifi.exclamationmark", description: Text(loadError))
                        Button("Retry") { Task { await load() } }.buttonStyle(.borderedProminent)
                    }
                } else if items.isEmpty {
                    ContentUnavailableView("Fridge is empty", systemImage: "refrigerator",
                                           description: Text("Add an item, scan a barcode, or import a Coop receipt."))
                } else {
                    List {
                        Section {
                            HStack(spacing: 0) {
                                summaryStat(count(in: "fridge"), "Fridge", "refrigerator.fill", Theme.copper)
                                summaryStat(count(in: "freezer"), "Freezer", "snowflake", Theme.teal)
                                summaryStat(count(in: "pantry"), "Pantry", "cabinet.fill", Theme.teal)
                            }
                            if expiringSoonCount > 0 {
                                Divider()
                                Label("\(expiringSoonCount) expiring soon", systemImage: "clock.badge.exclamationmark.fill")
                                    .font(.caption.weight(.semibold))
                                    .foregroundStyle(Theme.danger)
                            }
                        }
                        if !searchText.isEmpty && filteredItems.isEmpty {
                            ContentUnavailableView.search(text: searchText)
                        }
                        ForEach(groupedItems, id: \.position) { group in
                            Section {
                                ForEach(group.items) { item in
                                    row(item)
                                        .contentShape(Rectangle())
                                        .onTapGesture { selectedItem = item }
                                        .swipeActions(edge: .trailing, allowsFullSwipe: true) {
                                            Button("Delete", role: .destructive) { remove(item) }
                                        }
                                }
                            } header: {
                                HStack(spacing: 8) {
                                    Image(systemName: icon(for: group.position))
                                        .foregroundStyle(tint(for: group.position))
                                    Text(positionTitle(group.position))
                                    Spacer()
                                    Text("\(group.items.count)")
                                        .foregroundStyle(.secondary)
                                }
                                .font(.subheadline.weight(.semibold))
                                .textCase(nil)
                            }
                        }
                    }
                    .listStyle(.insetGrouped)
                }
            }
            .navigationTitle("Fridge")
            .toolbar {
                ToolbarItemGroup(placement: .topBarTrailing) {
                    Button { showSpending = true } label: { Image(systemName: "chart.bar.xaxis").frame(minWidth: 44, minHeight: 44).contentShape(Rectangle()) }
                    Button { showScanner = true } label: { Image(systemName: "barcode.viewfinder").frame(minWidth: 44, minHeight: 44).contentShape(Rectangle()) }
                    Menu {
                        Button("Import Coop PDF", systemImage: "doc.badge.plus") { showImport = true }
                        Button("Import hOn items", systemImage: "arrow.down.to.line") { showHonImport = true }
                    } label: {
                        Image(systemName: "square.and.arrow.down").frame(minWidth: 44, minHeight: 44)
                    }
                    Button { showAdd = true } label: { Image(systemName: "plus").frame(minWidth: 44, minHeight: 44).contentShape(Rectangle()) }
                }
            }
            .searchable(text: $searchText, prompt: "Search fridge")
            .safeAreaInset(edge: .bottom) { undoBanner }
            .sheet(item: $selectedItem) { FridgeItemDetailSheet(item: $0) }
            .task { await load() }
            .refreshable { await load() }
            .sheet(isPresented: $showAdd) { AddItemSheet { await load() } }
            .sheet(isPresented: $showScanner) { BarcodeScanSheet { await load() } }
            .sheet(isPresented: $showSpending) { SpendingView() }
            .fileImporter(isPresented: $showImport, allowedContentTypes: [.pdf]) { result in
                if case .success(let url) = result { Task { await importReceipt(url) } }
            }
            .confirmationDialog("Import hOn items?", isPresented: $showHonImport, titleVisibility: .visible) {
                Button("Import from hOn") { Task { await importHon() } }
            } message: {
                Text("Copies cloud items to this app without changing hOn. Items already in both lists may appear twice.")
            }
            .alert("Fridge", isPresented: Binding(
                get: { errorMessage != nil }, set: { if !$0 { errorMessage = nil } }
            )) {
                Button("OK", role: .cancel) { errorMessage = nil }
            } message: {
                Text(errorMessage ?? "")
            }
        }
    }

    private var filteredItems: [FridgeItem] {
        let q = searchText.trimmingCharacters(in: .whitespaces)
        guard !q.isEmpty else { return items }
        return items.filter { $0.name.localizedCaseInsensitiveContains(q) }
    }

    private var groupedItems: [(position: String, items: [FridgeItem])] {
        let order = ["fridge", "freezer", "pantry"]
        var groups: [(String, [FridgeItem])] = []
        for p in order {
            let matches = filteredItems
                .filter { ($0.position ?? "fridge") == p }
                .sorted { ($0.expiresOn ?? "9999-12-31") < ($1.expiresOn ?? "9999-12-31") }
            if !matches.isEmpty { groups.append((p, matches)) }
        }
        let rest = filteredItems
            .filter { !order.contains($0.position ?? "") }
            .sorted { ($0.expiresOn ?? "9999-12-31") < ($1.expiresOn ?? "9999-12-31") }
        if !rest.isEmpty { groups.append(("other", rest)) }
        return groups
    }

    private func positionTitle(_ p: String) -> String {
        switch p {
        case "freezer": return "Freezer"
        case "pantry": return "Pantry"
        case "other": return "Other"
        default: return "Fridge"
        }
    }

    private func row(_ item: FridgeItem) -> some View {
        HStack(spacing: 12) {
            RowIcon(systemName: icon(for: item.position), tint: tint(for: item.position))
            VStack(alignment: .leading, spacing: 3) {
                Text(item.name).font(.subheadline.weight(.medium)).lineLimit(1)
                Text(subtitle(item)).font(.caption).foregroundStyle(.secondary)
            }
            Spacer()
            expiryBadge(item)
        }
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
        case "freezer": return Theme.teal
        case "pantry": return Theme.teal
        default: return Theme.copper
        }
    }

    private func subtitle(_ i: FridgeItem) -> String {
        var parts: [String] = []
        if let q = i.quantity, let u = i.unit { parts.append("\(q) \(u)") }
        if let exp = i.expiresOn { parts.append("expires \(expiryDateLabel(exp))") }
        return parts.joined(separator: " · ")
    }

    private func daysLeft(_ iso: String) -> Int? {
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyy-MM-dd"
        guard let date = formatter.date(from: String(iso.prefix(10))) else { return nil }
        return Calendar.current.dateComponents([.day], from: Calendar.current.startOfDay(for: .now), to: date).day
    }

    private func count(in position: String) -> Int {
        items.filter { ($0.position ?? "fridge") == position }.count
    }

    private var expiringSoonCount: Int {
        items.filter {
            guard let exp = $0.expiresOn, let d = daysLeft(exp) else { return false }
            return d <= 3
        }.count
    }

    private func summaryStat(_ count: Int, _ label: String, _ symbol: String, _ tint: Color) -> some View {
        VStack(spacing: 8) {
            Image(systemName: symbol)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(.white)
                .frame(width: 36, height: 36)
                .background(tint, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
            Text("\(count)")
                .font(.system(size: 26, weight: .bold, design: .rounded))
                .contentTransition(.numericText())
            Text(label).font(.caption).foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity)
    }

    private func expiryBadge(_ item: FridgeItem) -> some View {
        Group {
            if let exp = item.expiresOn, let days = daysLeft(exp) {
                Label(expiryBadgeText(days), systemImage: days <= 1 ? "exclamationmark.triangle.fill" : "clock")
                    .font(.caption.weight(.semibold))
                    .padding(.horizontal, 9).padding(.vertical, 5)
                    .background(expiryColor(days).opacity(0.15), in: Capsule())
                    .foregroundStyle(expiryColor(days))
            }
        }
    }

    private func expiryBadgeText(_ days: Int) -> String {
        days < 0 ? "expired" : days == 0 ? "today" : "\(days)d"
    }

    private func expiryColor(_ days: Int) -> Color {
        days < 0 ? Theme.danger : days <= 1 ? Theme.danger : days <= 3 ? Theme.warning : Theme.success
    }

    private func expiryDateLabel(_ iso: String) -> String {
        let f = DateFormatter()
        f.dateFormat = "yyyy-MM-dd"
        guard let d = f.date(from: String(iso.prefix(10))) else { return iso }
        f.dateFormat = "d MMM"
        return f.string(from: d)
    }

    private func load() async {
        loading = true
        defer { loading = false }
        do {
            let inv: FridgeInventory = try await API.run("fridge_inventory_list")
            items = inv.items
            loadError = nil
        } catch {
            loadError = error.localizedDescription
        }
    }

    private func remove(_ item: FridgeItem) {
        undoItem = nil
        // Optimistic: remove instantly, restore only if the server call fails.
        withAnimation(.spring(response: 0.3, dampingFraction: 0.85)) {
            items.removeAll { $0.id == item.id }
        }
        Task {
            do {
                _ = try await API.run("fridge_inventory_remove", args: ["item_id": item.id]) as RemoveResult
                Haptics.success()
                undoItem = item
                Task { try? await Task.sleep(nanoseconds: 5_000_000_000); undoItem = nil }
            } catch {
                withAnimation { items.append(item) }
                errorMessage = error.localizedDescription
                Haptics.error()
            }
        }
    }

    private func undo(_ item: FridgeItem) {
        undoItem = nil
        withAnimation(.spring(response: 0.3, dampingFraction: 0.85)) { items.append(item) }
        Task {
            do {
                _ = try await API.run("fridge_inventory_add",
                                      args: ["name": item.name, "qty": item.quantity ?? 1,
                                             "unit": item.unit ?? "pz", "barcode": item.barcode ?? "",
                                             "brands": item.brands ?? "", "category": item.category ?? "",
                                             "expires_on": item.expiresOn ?? "",
                                             "position": item.position ?? "fridge"]) as AddResult
                await load()
            } catch {
                withAnimation { items.removeAll { $0.id == item.id } }
                errorMessage = error.localizedDescription
                Haptics.error()
            }
        }
    }

    @ViewBuilder private var undoBanner: some View {
        if let undoItem {
            HStack {
                Text("Removed \(undoItem.name)").font(.footnote)
                Spacer()
                Button("Undo") { undo(undoItem) }.font(.footnote).fontWeight(.semibold)
            }
            .padding(.horizontal, 16).padding(.vertical, 10)
            .background(.ultraThinMaterial, in: Capsule())
            .padding(.horizontal).padding(.bottom, 4)
        }
    }



    private func importHon() async {
        do {
            let result: HonImportResult = try await API.run("fridge_inventory_import_hon")
            await load()
            errorMessage = "Imported \(result.imported) items. Skipped \(result.skipped)."
            Haptics.success()
        } catch {
            errorMessage = error.localizedDescription
            Haptics.error()
        }
    }

    private func importReceipt(_ url: URL) async {
        do {
            let data = try Data(contentsOf: url)
            let r = try await API.importReceipt(data, filename: url.lastPathComponent)
            if r.alreadyImported == true {
                errorMessage = "Already imported"
            } else {
                errorMessage = "Added \(r.items?.count ?? 0) items"
            }
            Haptics.success()
            await load()
        } catch {
            errorMessage = error.localizedDescription
            Haptics.error()
        }
    }
}

struct HonImportResult: Decodable {
    let imported: Int
    let skipped: Int
}

struct AddItemSheet: View {
    @Environment(\.dismiss) private var dismiss
    var onAdded: () async -> Void

    @State private var name = ""
    @State private var expiry = Date().addingTimeInterval(7 * 86400)
    @State private var position = "fridge"
    @State private var busy = false
    @State private var errorMessage: String?

    var body: some View {
        NavigationStack {
            Form {
                Section("Item") {
                    TextField("Name (e.g. Milk 2.5%)", text: $name)
                    DatePicker("Expires", selection: $expiry, displayedComponents: .date)
                    Picker("Where", selection: $position) {
                        Text("Fridge").tag("fridge")
                        Text("Freezer").tag("freezer")
                        Text("Pantry").tag("pantry")
                    }
                    .pickerStyle(.segmented)
                }
                if let errorMessage {
                    Section { Text(errorMessage).foregroundStyle(.red).font(.footnote) }
                }
            }
            .navigationTitle("Add item")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Add") { Task { await add() } }.disabled(name.isEmpty || busy)
                }
            }
        }
    }

    private func add() async {
        busy = true
        let df = DateFormatter(); df.dateFormat = "yyyy-MM-dd"
        do {
            _ = try await API.run("fridge_inventory_add",
                                  args: ["name": name, "qty": 1,
                                         "expires_on": df.string(from: expiry),
                                         "position": position]) as AddResult
            Haptics.success()
            await onAdded()
            dismiss()
        } catch {
            errorMessage = error.localizedDescription
            Haptics.error()
        }
        busy = false
    }
}

struct BarcodeScannerView: UIViewControllerRepresentable {
    var onScan: (String) -> Void

    func makeUIViewController(context: Context) -> ScannerVC {
        let vc = ScannerVC()
        vc.onScan = { code in onScan(code) }
        return vc
    }

    func updateUIViewController(_ vc: ScannerVC, context: Context) {}
}

final class ScannerVC: UIViewController, AVCaptureMetadataOutputObjectsDelegate {
    var onScan: ((String) -> Void)?
    private let session = AVCaptureSession()

    override func viewDidLoad() {
        super.viewDidLoad()
        guard let device = AVCaptureDevice.default(for: .video),
              let input = try? AVCaptureDeviceInput(device: device) else { return }
        if session.canAddInput(input) { session.addInput(input) }
        let output = AVCaptureMetadataOutput()
        if session.canAddOutput(output) {
            session.addOutput(output)
            output.setMetadataObjectsDelegate(self, queue: .main)
            output.metadataObjectTypes = [.ean13, .ean8, .upce, .code128]
        }
        let preview = AVCaptureVideoPreviewLayer(session: session)
        preview.videoGravity = .resizeAspectFill
        preview.frame = view.bounds
        view.layer.addSublayer(preview)
        DispatchQueue.global(qos: .userInitiated).async { self.session.startRunning() }
    }

    func metadataOutput(_ output: AVCaptureMetadataOutput,
                        didOutput metadataObjects: [AVMetadataObject],
                        from connection: AVCaptureConnection) {
        if let obj = metadataObjects.first as? AVMetadataMachineReadableCodeObject, let code = obj.stringValue {
            session.stopRunning()
            onScan?(code)
        }
    }
}

struct BarcodeScanSheet: View {
    @Environment(\.dismiss) private var dismiss
    var onAdded: () async -> Void

    @State private var product: BarcodeProduct?
    @State private var errorMessage: String?
    @State private var adding = false

    var body: some View {
        NavigationStack {
            VStack(spacing: 16) {
                if let found = product {
                    VStack(spacing: 10) {
                        Image(systemName: "checkmark.seal.fill").font(.system(size: 40)).foregroundStyle(.green)
                        Text(found.name).font(.headline).multilineTextAlignment(.center)
                        Text([found.brands ?? "", found.category ?? ""].filter { !$0.isEmpty }.joined(separator: " · "))
                            .font(.caption).foregroundStyle(.secondary)
                        if let d = found.shelfLifeDays {
                            Text("Expires in ~\(d) days").font(.caption).foregroundStyle(.secondary)
                        }
                    }
                    Button {
                        Task { await add() }
                    } label: {
                        if adding { ProgressView() } else { Text("Add to fridge") }
                    }
                    .buttonStyle(.borderedProminent).buttonBorderShape(.capsule).disabled(adding)
                    Button("Scan another") { product = nil; errorMessage = nil }
                } else {
                    ZStack(alignment: .bottom) {
                        BarcodeScannerView { code in Task { await lookup(code) } }
                        Text("Point at a barcode")
                            .font(.footnote)
                            .padding(.horizontal, 14).padding(.vertical, 8)
                            .background(.ultraThinMaterial, in: Capsule())
                            .padding(.bottom, 40)
                    }
                    if let errorMessage {
                        Text(errorMessage).font(.footnote).foregroundStyle(.red)
                    }
                }
            }
            .padding()
            .navigationTitle("Scan barcode")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
            }
        }
    }

    private func lookup(_ code: String) async {
        do {
            product = try await API.run("lookup_barcode", args: ["barcode": code])
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    private func add() async {
        guard let code = product?.barcode else { return }
        adding = true
        do {
            _ = try await API.run("add_barcode_item", args: ["barcode": code]) as AddResult
            Haptics.success()
            await onAdded()
            dismiss()
        } catch {
            errorMessage = error.localizedDescription
            Haptics.error()
        }
        adding = false
    }
}

struct FridgeItemDetailSheet: View {
    let item: FridgeItem
    @Environment(\.dismiss) private var dismiss
    @State private var price: PriceTrend?

    var body: some View {
        NavigationStack {
            List {
                Section("Item") {
                    LabeledContent("Name", value: item.name)
                    LabeledContent("Where", value: item.position ?? "fridge")
                    if let q = item.quantity, let u = item.unit {
                        LabeledContent("Quantity", value: "\(q) \(u)")
                    }
                    if let exp = item.expiresOn {
                        LabeledContent("Expires", value: String(exp.prefix(10)))
                    }
                }
                Section("Price history") {
                    if let p = price, let h = p.history, !h.isEmpty {
                        LabeledContent("Latest", value: String(format: "%.2f €", p.latest ?? 0))
                        LabeledContent("Min", value: String(format: "%.2f €", p.min ?? 0))
                        LabeledContent("Max", value: String(format: "%.2f €", p.max ?? 0))
                        LabeledContent("Avg", value: String(format: "%.2f €", p.avg ?? 0))
                        ForEach(h) { row in
                            HStack {
                                Text(row.boughtOn ?? "").foregroundStyle(.secondary)
                                Spacer()
                                Text(String(format: "%.2f €", row.price)).fontWeight(.semibold)
                            }
                        }
                    } else {
                        Text("No price history yet — import receipts to start tracking.")
                            .font(.footnote).foregroundStyle(.secondary)
                    }
                }
            }
            .navigationTitle(item.name)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .topBarTrailing) { Button("Done") { dismiss() } } }
            .task {
                price = try? await API.run("price_trend", args: ["name": item.name])
            }
        }
    }
}
