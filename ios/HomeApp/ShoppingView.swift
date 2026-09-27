import SwiftUI

struct ShoppingView: View {
    @State private var items: [ShoppingItem] = []
    @State private var newItem = ""

    var body: some View {
        NavigationStack {
            Group {
                if items.isEmpty {
                    ContentUnavailableView("Shopping list is empty", systemImage: "cart",
                                           description: Text("Add items below or ask the assistant."))
                } else {
                    List {
                        ForEach(items) { item in
                            HStack(spacing: 12) {
                                Circle().fill(Theme.pearl).frame(width: 7, height: 7)
                                Text(item.name)
                            }
                        }
                        .onDelete(perform: delete)
                    }
                    .listStyle(.insetGrouped)
                }
            }
            .navigationTitle("Shopping")
            .navigationBarTitleDisplayMode(.large)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Clear") { Task { await clear() } }
                        .disabled(items.isEmpty)
                }
            }
            .safeAreaInset(edge: .bottom, spacing: 12) {
                HStack(spacing: 10) {
                    TextField("Add item…", text: $newItem)
                        .padding(.horizontal, 14).padding(.vertical, 10)
                        .background(Color(.secondarySystemBackground), in: Capsule())
                        .onSubmit { add() }
                    Button { add() } label: {
                        Image(systemName: "plus")
                            .font(.system(size: 16, weight: .semibold))
                            .foregroundStyle(.white)
                            .frame(width: 44, height: 44)
                            .background(Theme.ink, in: Circle())
                    }
                    .disabled(newItem.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                }
                .padding(.horizontal, 16).padding(.vertical, 8)
                .background(Color(.secondarySystemGroupedBackground))
                .overlay(alignment: .top) { Divider() }
            }
            .task { await load() }
            .refreshable { await load() }
        }
    }

    private func load() async {
        if let list: ShoppingList = try? await API.run("shopping_list") { items = list.items }
    }

    private func add() {
        let name = newItem.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !name.isEmpty else { return }
        Haptics.impact(.light)
        newItem = ""
        Task {
            _ = try? await API.run("shopping_add", args: ["name": name]) as EmptyResult
            await load()
        }
    }

    private func delete(at offsets: IndexSet) {
        Haptics.impact(.light)
        for i in offsets {
            let item = items[i]
            Task { _ = try? await API.run("shopping_remove", args: ["item_id": item.id]) as RemoveResult }
        }
        items.remove(atOffsets: offsets)
    }

    private func clear() async {
        Haptics.success()
        _ = try? await API.run("shopping_clear") as EmptyResult
        await load()
    }
}
import SwiftUI

struct RecipesView: View {
    @State private var saved: [SavedRecipe] = []
    @State private var suggested: [RecipeSuggestion] = []
    @State private var showImport = false
    @State private var showDetail: SavedRecipe?
    @State private var showSuggestion: RecipeSuggestion?
    @State private var importURL = ""
    @State private var showTextImport = false
    @State private var importText = ""
    @State private var loading = false
    @State private var statusMessage: String?

    var body: some View {
        NavigationStack {
            List {
                if !suggested.isEmpty {
                    Section("Suggestions from your fridge") {
                        ForEach(suggested) { rec in
                            Button { showSuggestion = rec } label: {
                                HStack {
                                    Text(rec.name).lineLimit(1)
                                    Spacer()
                                    Button("Save") {
                                        Task {
                                            _ = try? await API.run("save_recipe", args: ["meal_id": rec.id]) as AddResult
                                            Haptics.success()
                                            await load()
                                        }
                                    }
                                    .buttonStyle(.bordered).buttonBorderShape(.capsule)
                                }
                            }
                            .foregroundStyle(.primary)
                        }
                    }
                }

                Section("Saved") {
                    if saved.isEmpty && !loading {
                        Text("No saved recipes yet.").foregroundStyle(.secondary)
                    }
                    ForEach(saved) { rec in
                        Button { showDetail = rec } label: {
                            HStack {
                                VStack(alignment: .leading, spacing: 2) {
                                    Text(rec.name).lineLimit(1)
                                    Text("\(rec.ingredients?.count ?? 0) ingredients · \(rec.source ?? "")")
                                        .font(.caption).foregroundStyle(.secondary)
                                }
                                Spacer()
                            }
                        }
                        .foregroundStyle(.primary)
                        .swipeActions {
                            Button("Delete", role: .destructive) {
                                Task {
                                    _ = try? await API.run("remove_saved_recipe", args: ["recipe_id": rec.id]) as RemoveResult
                                    Haptics.impact(.light)
                                    await load()
                                }
                            }
                        }
                    }
                }
            }
            .navigationTitle("Recipes")
            .navigationBarTitleDisplayMode(.large)
            .toolbar {
                ToolbarItemGroup(placement: .topBarTrailing) {
                    Button { Task { await suggest() } } label: { Image(systemName: "sparkles") }
                    Button { showTextImport = true } label: { Image(systemName: "text.badge.plus") }
                    Button { showImport = true } label: { Image(systemName: "square.and.arrow.down") }
                }
            }
            .task { await load() }
            .refreshable { await load() }
            .sheet(isPresented: $showImport) { importSheet }
            .sheet(isPresented: $showTextImport) { textImportSheet }
            .sheet(item: $showDetail) { rec in
                RecipeDetailSheet(name: rec.name, ingredients: rec.ingredients ?? [], instructions: rec.instructions ?? "",
                                  thumb: rec.thumb, source: rec.source, recipeId: rec.id, onChanged: { Task { await load() } })
            }
            .sheet(item: $showSuggestion) { rec in
                RecipeDetailSheet(name: rec.name, ingredients: rec.ingredients ?? [], instructions: rec.instructions ?? "",
                                  thumb: rec.thumb, category: rec.category, area: rec.area)
            }
            .alert("Recipes", isPresented: Binding(get: { statusMessage != nil }, set: { if !$0 { statusMessage = nil } })) {
                Button("OK", role: .cancel) { statusMessage = nil }
            } message: { Text(statusMessage ?? "") }
        }
    }

    private var importSheet: some View {
        NavigationStack {
            Form {
                Section("Recipe link") {
                    TextField("https://…", text: $importURL)
                        .keyboardType(.URL)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                }
            }
            .navigationTitle("Import recipe")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { showImport = false } }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Import") { Task { await importFromURL() } }.disabled(importURL.isEmpty)
                }
            }
        }
    }

    private func load() async {
        loading = true
        do {
            let list: SavedRecipeList = try await API.run("saved_recipes")
            saved = list.recipes
        } catch {
            statusMessage = error.localizedDescription
        }
        loading = false
    }

    private func suggest() async {
        do {
            let r: RecipeSuggestions = try await API.run("suggest_recipes")
            suggested = r.recipes
            if r.recipes.isEmpty { statusMessage = "No recipes found." }
        } catch {
            statusMessage = error.localizedDescription
        }
    }

    private func importFromURL() async {
        do {
            _ = try await API.run("import_recipe", args: ["url": importURL]) as AddResult
            Haptics.success()
            statusMessage = "Recipe saved."
            importURL = ""
            showImport = false
            await load()
        } catch {
            statusMessage = error.localizedDescription
            Haptics.error()
        }
    }

    private var textImportSheet: some View {
        NavigationStack {
            Form {
                Section("Paste the recipe") {
                    TextEditor(text: $importText)
                        .frame(minHeight: 240)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                }
            }
            .navigationTitle("Add from text")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { showTextImport = false } }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Parse") { Task { await importFromText() } }
                        .disabled(importText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                }
            }
        }
    }

    private func importFromText() async {
        let text = importText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }
        do {
            let r: TextImportResult = try await API.run("import_recipe_text", args: ["text": text])
            Haptics.success()
            statusMessage = "Saved \"\(r.saved ?? "recipe")\""
            importText = ""
            showTextImport = false
            await load()
        } catch {
            statusMessage = error.localizedDescription
            Haptics.error()
        }
    }
}

struct TextImportResult: Decodable { var saved: String?; var id: String? }

struct RecipeDetailSheet: View {
    let name: String
    let ingredients: [String]
    let instructions: String
    var thumb: String? = nil
    var category: String? = nil
    var area: String? = nil
    var source: String? = nil
    var recipeId: String? = nil
    var onChanged: () -> Void = {}

    @Environment(\.dismiss) private var dismiss
    @State private var showCook = false
    @State private var showEdit = false

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    hero
                    if !badgeItems.isEmpty { badges }
                    if !ingredients.isEmpty {
                        sectionCard("Ingredients", icon: "carrot.fill") { ingredientList }
                    }
                    if !parsedSteps.isEmpty {
                        sectionCard("Steps", icon: "list.number") { stepsList }
                    }
                }
                .padding(16)
                .padding(.bottom, 24)
            }
            .matteBackground()
            .navigationTitle(name)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItemGroup(placement: .topBarTrailing) {
                    if recipeId != nil {
                        Button { showEdit = true } label: { Image(systemName: "pencil") }
                    }
                    if !parsedSteps.isEmpty {
                        Button { showCook = true } label: { Label("Cook", systemImage: "flame.fill") }
                    }
                    Button("Done") { dismiss() }
                }
            }
            .fullScreenCover(isPresented: $showCook) { CookModeView(name: name, steps: parsedSteps) }
            .sheet(isPresented: $showEdit) {
                if let recipeId {
                    RecipeEditSheet(recipeId: recipeId, name: name, ingredients: ingredients, instructions: instructions, onSaved: onChanged)
                }
            }
        }
    }

    // ── Hero ────────────────────────────────────────────────────────────────
    private var hero: some View {
        Group {
            if let t = thumb, !t.isEmpty, let url = URL(string: t) {
                AsyncImage(url: url) { phase in
                    switch phase {
                    case .success(let image):
                        image.resizable().scaledToFill()
                    case .failure:
                        heroPlaceholder
                    default:
                        ZStack { Color(.systemGray5); ProgressView() }
                    }
                }
            } else {
                heroPlaceholder
            }
        }
        .frame(height: 190)
        .frame(maxWidth: .infinity)
        .clipShape(RoundedRectangle(cornerRadius: 22, style: .continuous))
    }

    private var heroPlaceholder: some View {
        ZStack {
            Theme.pearl
            Image(systemName: "fork.knife").font(.system(size: 46)).foregroundStyle(.white.opacity(0.9))
        }
    }

    // ── Badges ──────────────────────────────────────────────────────────────
    private var badgeItems: [(String, String, Color)] {
        var items: [(String, String, Color)] = []
        if let category, !category.isEmpty { items.append((category, "tag.fill", Theme.pearl)) }
        if let area, !area.isEmpty { items.append((area, "globe", Theme.slate)) }
        if let source, !source.isEmpty {
            let label = source == "mealdb" ? "TheMealDB" : (source == "url" ? "Imported" : source)
            items.append((label, "link", Theme.slate))
        }
        return items
    }

    private var badges: some View {
        HStack(spacing: 8) {
            ForEach(badgeItems, id: \.0) { item in
                Label(item.0, systemImage: item.1)
                    .font(.caption.weight(.medium))
                    .padding(.horizontal, 10).padding(.vertical, 6)
                    .background(item.2.opacity(0.14), in: Capsule())
                    .foregroundStyle(item.2)
            }
        }
    }

    // ── Sections ────────────────────────────────────────────────────────────
    private func sectionCard<Content: View>(_ title: String, icon: String,
                                            @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            Label(title, systemImage: icon).font(.headline)
            content()
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color(.secondarySystemGroupedBackground), in: RoundedRectangle(cornerRadius: 18, style: .continuous))
    }

    private var ingredientList: some View {
        VStack(spacing: 0) {
            ForEach(Array(ingredients.enumerated()), id: \.offset) { idx, ing in
                HStack(alignment: .top, spacing: 12) {
                    Circle().fill(Theme.pearl).frame(width: 7, height: 7).padding(.top, 7)
                    Text(ing).font(.subheadline).lineSpacing(2)
                    Spacer(minLength: 0)
                }
                .padding(.vertical, 7)
                if idx < ingredients.count - 1 { Divider() }
            }
        }
    }

    private var stepsList: some View {
        VStack(alignment: .leading, spacing: 14) {
            ForEach(Array(parsedSteps.enumerated()), id: \.offset) { idx, step in
                HStack(alignment: .top, spacing: 12) {
                    Text("\(idx + 1)")
                        .font(.subheadline.weight(.bold))
                        .foregroundStyle(.white)
                        .frame(width: 28, height: 28)
                        .background(Theme.slate, in: Circle())
                    Text(step).font(.subheadline).lineSpacing(3)
                    Spacer(minLength: 0)
                }
            }
        }
    }

    // ── Step parsing ────────────────────────────────────────────────────────
    private var parsedSteps: [String] {
        let text = instructions.replacingOccurrences(of: "\r\n", with: "\n")
        let lines = text.components(separatedBy: "\n")
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
        if lines.count > 1 { return lines }

        // Single blob: split on numbered step markers ("1.", "1)", "Step 1:").
        let patterns = [
            #"(?<!\d)(\d{1,2})[\.\):]\s*"#,
            #"(?i)step\s+\d{1,2}\s*[:.]?\s*"#,
        ]
        for pattern in patterns {
            guard let regex = try? NSRegularExpression(pattern: pattern) else { continue }
            let ns = text as NSString
            let matches = regex.matches(in: text, range: NSRange(location: 0, length: ns.length))
            guard matches.count > 1 else { continue }
            var steps: [String] = []
            for (i, m) in matches.enumerated() {
                let start = m.range.location
                let end = (i + 1 < matches.count) ? matches[i + 1].range.location : ns.length
                let s = ns.substring(with: NSRange(location: start, length: end - start))
                    .trimmingCharacters(in: .whitespacesAndNewlines)
                if !s.isEmpty { steps.append(s) }
            }
            if !steps.isEmpty { return steps }
        }
        return [text]
    }
}

struct RecipeEditSheet: View {
    let recipeId: String
    let onSaved: () -> Void
    @Environment(\.dismiss) private var dismiss
    @State private var name: String
    @State private var ingredientsText: String
    @State private var instructions: String
    @State private var saving = false
    @State private var errorMessage: String?

    init(recipeId: String, name: String, ingredients: [String], instructions: String, onSaved: @escaping () -> Void) {
        self.recipeId = recipeId
        self.onSaved = onSaved
        _name = State(initialValue: name)
        _ingredientsText = State(initialValue: ingredients.joined(separator: "\n"))
        _instructions = State(initialValue: instructions)
    }

    var body: some View {
        NavigationStack {
            Form {
                Section("Title") {
                    TextField("Recipe name", text: $name)
                }
                Section("Ingredients — one per line") {
                    TextEditor(text: $ingredientsText).frame(minHeight: 150)
                }
                Section("Instructions") {
                    TextEditor(text: $instructions).frame(minHeight: 180)
                }
                if let errorMessage {
                    Section { Text(errorMessage).font(.footnote).foregroundStyle(.red) }
                }
            }
            .navigationTitle("Edit recipe")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") { Task { await save() } }
                        .disabled(saving || name.trimmingCharacters(in: .whitespaces).isEmpty)
                }
            }
        }
    }

    private func save() async {
        saving = true
        defer { saving = false }
        let ings = ingredientsText.components(separatedBy: "\n")
            .map { $0.trimmingCharacters(in: .whitespaces) }
            .filter { !$0.isEmpty }
        do {
            _ = try await API.run("update_recipe", args: [
                "recipe_id": recipeId,
                "name": name.trimmingCharacters(in: .whitespaces),
                "ingredients": ings,
                "instructions": instructions,
            ]) as EmptyResult
            Haptics.success()
            onSaved()
            dismiss()
        } catch {
            Haptics.error()
            errorMessage = error.localizedDescription
        }
    }
}
