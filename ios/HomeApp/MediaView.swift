import SwiftUI

// ── Media tab: poster-grid library + downloads (Transmission). ───────────────

struct MediaView: View {
    enum LibrarySection: String, CaseIterable {
        case movies, series
    }
    @State private var section: LibrarySection = .movies
    @State private var continueItems: [PlaybackRecord] = []
    @State private var playerPresentation: PlayerPresentation?
    @State private var showDownloads = false
    @State private var showOnDevice = false

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                if !continueItems.isEmpty {
                    ContinueWatchingRow(items: continueItems, onPlay: { play($0) },
                                        onChanged: { Task { await loadContinue() } })
                        .padding(.top, 8)
                }

                Picker("Section", selection: $section) {
                    Text("Movies").tag(LibrarySection.movies)
                    Text("Series").tag(LibrarySection.series)
                }
                .pickerStyle(.segmented)
                .padding(.horizontal, 16)
                .padding(.vertical, 8)

                switch section {
                case .movies: MediaLibraryView(mediaType: "movie")
                case .series: MediaLibraryView(mediaType: "series")
                }
            }
            .matteBackground()
            .navigationTitle("Media")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItemGroup(placement: .topBarTrailing) {
                    Button { showOnDevice = true } label: { Image(systemName: "iphone") }
                    Button { showDownloads = true } label: { Image(systemName: "arrow.down.circle") }
                }
            }
            .sheet(isPresented: $showDownloads) { NavigationStack { DownloadsView() } }
            .sheet(isPresented: $showOnDevice) { NavigationStack { DownloadedView() } }
        }
        .task { await loadContinue() }
        .fullScreenCover(item: $playerPresentation) { p in
            PlayerView(url: p.url, subtitleURL: p.subtitleURL, title: p.title,
                       path: p.path, kind: p.kind, image: p.image,
                       seriesId: p.seriesId, season: p.season, episode: p.episode)
        }
    }

    private func loadContinue() async {
        if let r = try? await API.playbackContinue() {
            continueItems = r.items
        }
    }

    private func play(_ rec: PlaybackRecord) {
        guard let url = API.streamURL(path: rec.path) else { return }
        Haptics.impact(.medium)
        playerPresentation = PlayerPresentation(url: url, subtitleURL: API.subtitlesURL(path: rec.path),
                                                title: rec.title ?? "", path: rec.path,
                                                kind: rec.kind ?? "movie", image: rec.image,
                                                seriesId: rec.seriesId, season: rec.season, episode: rec.episode)
    }
}

// ── Codec badge (flags files the TV can't play) ──────────────────────────────

func codecBadge(_ item: JellyfinItem) -> (label: String, color: Color) {
    let codec = (item.videoCodec ?? "").lowercased()
    let depth = item.bitDepth ?? 0
    if item.hdr == true { return ("HDR", .red) }
    if depth >= 10 { return ("10-bit", .red) }
    if codec == "av1" { return ("AV1", .red) }
    if codec == "hevc" || codec == "h265" || codec == "x265" {
        return (item.resolution.map { "HEVC \($0)" } ?? "HEVC", .orange)
    }
    if codec == "h264" || codec == "avc" || codec == "x264" {
        return (item.resolution.map { "H.264 \($0)" } ?? "H.264", .green)
    }
    if codec.isEmpty { return (item.resolution ?? "—", .secondary) }
    return (codec.uppercased(), .secondary)
}

// ── Poster image with shimmer placeholder ────────────────────────────────────

struct PosterImage: View {
    let imagePath: String?
    var cornerRadius: CGFloat = 12

    var body: some View {
        Color.clear
            .aspectRatio(2/3, contentMode: .fit)
            .overlay { posterContent }
            .clipShape(RoundedRectangle(cornerRadius: cornerRadius, style: .continuous))
            .clipped()
    }

    @ViewBuilder private var posterContent: some View {
        if let p = imagePath, let url = API.imageURL(p) {
            AsyncImage(url: url) { phase in
                switch phase {
                case .success(let img): img.resizable().scaledToFill()
                case .failure: placeholder
                case .empty: placeholder
                @unknown default: placeholder
                }
            }
        } else {
            placeholder
        }
    }

    private var placeholder: some View {
        ZStack {
            Rectangle().fill(
                LinearGradient(colors: [Palette.accent.opacity(0.16), Palette.accent.opacity(0.04)],
                               startPoint: .top, endPoint: .bottom))
            Image(systemName: "film")
                .font(.largeTitle)
                .foregroundStyle(Palette.accent.opacity(0.45))
        }
    }
}

// ── Poster grid cell ─────────────────────────────────────────────────────────

struct PosterCell: View {
    let item: JellyfinItem
    var watched: Bool = false
    var progress: Double = 0

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            PosterImage(imagePath: item.image)
                .frame(maxWidth: .infinity)
                .overlay(alignment: .topLeading) { codecOverlay }
                .overlay(alignment: .topTrailing) {
                    if watched {
                        Image(systemName: "checkmark.circle.fill")
                            .font(.title3)
                            .foregroundStyle(.white, Palette.accent)
                            .shadow(color: .black.opacity(0.4), radius: 2)
                            .padding(6)
                    }
                }
                .overlay(alignment: .bottom) {
                    if progress > 0.01 && progress < 0.99 {
                        GeometryReader { geo in
                            ZStack(alignment: .leading) {
                                Rectangle().fill(.black.opacity(0.5))
                                Rectangle().fill(Palette.accent)
                                    .frame(width: max(0, geo.size.width * progress))
                            }
                        }
                        .frame(height: 3)
                    }
                }

            Text(item.name)
                .font(.caption.weight(.semibold))
                .lineLimit(2, reservesSpace: true)
                .multilineTextAlignment(.leading)

            HStack(spacing: 5) {
                if let r = item.rating, r > 0 {
                    Label(String(format: "%.1f", r), systemImage: "star.fill")
                        .font(.caption2.weight(.medium))
                        .foregroundStyle(.yellow)
                }
                if let y = item.year {
                    Text(String(y)).font(.caption2).foregroundStyle(.secondary)
                }
                Spacer(minLength: 0)
            }
        }
    }

    @ViewBuilder private var codecOverlay: some View {
        let badge = codecBadge(item)
        if badge.color == .red || badge.color == .orange {
            PillStatus(text: badge.label, color: badge.color)
                .padding(6)
        }
    }
}

// ── Movie / series poster grid ───────────────────────────────────────────────

struct MediaLibraryView: View {
    let mediaType: String
    @State private var items: [JellyfinItem] = []
    @State private var loading = true
    @State private var errorMessage: String?
    @State private var selected: JellyfinItem?
    @State private var selectedSeries: JellyfinItem?
    @State private var searchText = ""
    @State private var playbackByPath: [String: PlaybackRecord] = [:]
    @State private var didLoad = false
    @State private var itemToDelete: JellyfinItem?
    @Namespace private var ns

    private let columns = [
        GridItem(.flexible(), spacing: 12),
        GridItem(.flexible(), spacing: 12),
        GridItem(.flexible(), spacing: 12),
    ]

    var body: some View {
        Group {
            if loading {
                VStack(spacing: 16) {
                    HStack(spacing: 12) { ForEach(0..<3, id: \.self) { _ in SkeletonTile(height: 150).clipShape(RoundedRectangle(cornerRadius: 12)) } }
                    HStack(spacing: 12) { ForEach(0..<3, id: \.self) { _ in SkeletonTile(height: 150).clipShape(RoundedRectangle(cornerRadius: 12)) } }
                    Spacer()
                }
                .padding(16)
            } else if let errorMessage {
                VStack(spacing: 12) {
                    ContentUnavailableView("Couldn't load", systemImage: "wifi.exclamationmark", description: Text(errorMessage))
                    Button("Retry") { Task { await load() } }
                        .buttonStyle(.borderedProminent)
                }
            } else if items.isEmpty {
                ContentUnavailableView("Empty library", systemImage: "film", description: Text("No \(mediaType == "series" ? "series" : "movies") yet."))
            } else {
                ScrollView {
                    if filteredItems.isEmpty {
                        ContentUnavailableView("No matches", systemImage: "magnifyingglass", description: Text("Try a different search."))
                            .padding(.top, 60)
                    } else {
                        LazyVGrid(columns: columns, spacing: 18) {
                            ForEach(Array(filteredItems.enumerated()), id: \.element.id) { idx, item in
                            Button {
                                Haptics.impact()
                                if item.type == "Series" {
                                    selectedSeries = item
                                } else {
                                    selected = item
                                }
                            } label: {
                                let rec = playbackByPath[item.path ?? ""]
                                PosterCell(item: item,
                                           watched: rec?.watched ?? false,
                                           progress: rec.map { $0.duration > 0 ? min($0.position / $0.duration, 1) : 0 } ?? 0)
                            }
                            .buttonStyle(PressableButtonStyle())
                            .matchedTransitionSource(id: item.id, in: ns)
                            .opacity(items.count > 0 ? 1 : 0)
                            .animation(.easeOut(duration: 0.35).delay(Double(idx) * 0.03), value: items.count)
                            .contextMenu {
                                Button(role: .destructive) {
                                    itemToDelete = item
                                } label: {
                                    Label("Delete", systemImage: "trash")
                                }
                            }
                        }
                    }
                    .padding(.horizontal, 16)
                    .padding(.bottom, 24)
                    }
                }
                .refreshable { await load() }
                .searchable(text: $searchText, placement: .navigationBarDrawer(displayMode: .always), prompt: "Search \(mediaType == "series" ? "series" : "movies")")
            }
        }
        .task {
            guard !didLoad else { return }
            didLoad = true
            await load()
        }
        .navigationDestination(item: $selected) { item in
            MediaItemDetailSheet(item: item) {
                items.removeAll { $0.id == item.id }
            }
            .navigationTransition(.zoom(sourceID: item.id, in: ns))
        }
        .sheet(item: $selectedSeries) { series in
            SeriesEpisodesView(series: series)
        }
        .confirmationDialog("Delete \"\(itemToDelete?.name ?? "")\"?",
                            isPresented: Binding(get: { itemToDelete != nil }, set: { if !$0 { itemToDelete = nil } }),
                            titleVisibility: .visible) {
            Button("Delete from drive", role: .destructive) {
                if let item = itemToDelete { Task { await deleteItem(item) } }
                itemToDelete = nil
            }
            Button("Cancel", role: .cancel) { itemToDelete = nil }
        } message: {
            Text("This removes the files from the drive. It can't be undone.")
        }
    }

    private func deleteItem(_ item: JellyfinItem) async {
        do {
            let _: JellyfinDeleteResult = try await API.run("jellyfin_delete", args: ["item_id": item.id])
            withAnimation { items.removeAll { $0.id == item.id } }
            Haptics.success()
        } catch {
            errorMessage = error.localizedDescription
            Haptics.error()
        }
    }

    private func load() async {
        loading = true
        defer { loading = false }
        do {
            let r: JellyfinItemList = try await API.run("jellyfin_library", args: ["media_type": mediaType])
            items = r.items
            errorMessage = nil
        } catch {
            // Fallback: scan the drive directly (works even when the Mac/Jellyfin is off)
            let tool = mediaType == "series" ? "local_series" : "local_movies"
            if let r: JellyfinItemList = try? await API.run(tool) {
                items = r.items
                errorMessage = nil
            } else {
                errorMessage = error.localizedDescription
            }
        }
        await refreshStatus()
    }

    private func refreshStatus() async {
        if let s = try? await API.playbackStatus() {
            playbackByPath = Dictionary(uniqueKeysWithValues: s.items.map { ($0.path, $0) })
        }
    }

    private var filteredItems: [JellyfinItem] {
        let q = searchText.trimmingCharacters(in: .whitespaces)
        guard !q.isEmpty else { return items }
        return items.filter { $0.name.localizedCaseInsensitiveContains(q) }
    }
}

// ── Detail sheet ─────────────────────────────────────────────────────────────

struct MediaItemDetailSheet: View {
    @Environment(\.dismiss) private var dismiss
    let item: JellyfinItem
    let onDeleted: () -> Void

    @State private var detail: JellyfinItemDetail?
    @State private var errorMessage: String?
    @State private var showDeleteConfirm = false
    @State private var deleting = false
    @State private var playerPresentation: PlayerPresentation?
    @State private var downloading = false
    @State private var downloadStatus: String?
    @State private var downloadFilename = ""
    @ObservedObject private var downloads = DownloadManager.shared

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                    // Poster hero
                    PosterImage(imagePath: item.image, cornerRadius: 18)
                        .frame(maxWidth: 230)
                        .frame(maxWidth: .infinity)
                        .overlay(alignment: .bottom) {
                            LinearGradient(colors: [.clear, .black.opacity(0.8)], startPoint: .center, endPoint: .bottom)
                                .overlay(alignment: .bottomLeading) {
                                    VStack(alignment: .leading, spacing: 2) {
                                        Text(item.name)
                                            .font(.headline.weight(.bold))
                                            .foregroundStyle(.white)
                                            .multilineTextAlignment(.leading)
                                            .lineLimit(2)
                                        if let y = item.year {
                                            Text(String(y)).font(.caption.weight(.semibold)).foregroundStyle(.white.opacity(0.85))
                                        }
                                    }
                                    .padding(12)
                                }
                                .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
                        }
                        .shadow(color: .black.opacity(0.3), radius: 18, y: 10)

                    // Meta
                    VStack(spacing: 4) {
                        metaLine
                    }
                    .frame(maxWidth: .infinity)

                    // Play + Download
                    HStack(spacing: 12) {
                        Button { play() } label: {
                            Label("Play", systemImage: "play.fill")
                                .frame(maxWidth: .infinity)
                                .padding(.vertical, 6)
                        }
                        .buttonStyle(.borderedProminent)
                        .tint(Palette.accent)

                        Button { Task { await download() } } label: {
                            Label(downloadStatus ?? "Download", systemImage: downloading ? "arrow.down.circle.dotted" : "arrow.down.circle")
                                .frame(maxWidth: .infinity)
                                .padding(.vertical, 6)
                        }
                        .buttonStyle(.bordered)
                        .disabled(downloading)
                    }

                    // Download progress
                    if downloading, let p = downloads.progress[downloadFilename] {
                        VStack(alignment: .leading, spacing: 6) {
                            ProgressView(value: p)
                                .progressViewStyle(.linear)
                                .tint(Theme.teal)
                            Text("Downloading… \(Int(p * 100))%")
                                .font(.caption).foregroundStyle(.secondary)
                        }
                    }

                    // Delete
                    Button(role: .destructive) {
                        showDeleteConfirm = true
                    } label: {
                        Label(deleting ? "Deleting…" : "Delete from drive", systemImage: "trash")
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, 6)
                    }
                    .buttonStyle(.borderedProminent)
                    .tint(.red)
                    .disabled(deleting)

                    // Genres
                    if let genres = detail?.genres, !genres.isEmpty {
                        FlowChips(items: genres)
                    }

                    // Overview
                    if let overview = detail?.overview, !overview.isEmpty {
                        VStack(alignment: .leading, spacing: 6) {
                            Text("Storyline").font(.headline)
                            Text(overview).font(.subheadline).foregroundStyle(.secondary)
                        }
                    }

                    // Cast + director
                    if let cast = detail?.cast, !cast.isEmpty {
                        VStack(alignment: .leading, spacing: 8) {
                            Text("Cast").font(.headline)
                            FlowChips(items: cast)
                        }
                    }
                    if let director = detail?.director {
                        LabeledContent("Director", value: director).font(.subheadline)
                    }

                    // File info
                    VStack(alignment: .leading, spacing: 8) {
                        Text("File").font(.headline)
                        let badge = codecBadge(item)
                        HStack(spacing: 8) {
                            PillStatus(text: badge.label, color: badge.color)
                            if let s = item.sizeMB, s > 0 { Text("\(Int(s)) MB").font(.caption).foregroundStyle(.secondary) }
                        }
                        if let p = item.path {
                            Text(p).font(.caption2).foregroundStyle(.secondary).lineLimit(2)
                        }
                    }
                }
                .padding(20)
            }
            .navigationTitle(item.name)
            .navigationBarTitleDisplayMode(.inline)
        .task { await load() }
        .confirmationDialog("Delete \"\(item.name)\"?", isPresented: $showDeleteConfirm, titleVisibility: .visible) {
            Button("Delete from drive", role: .destructive) { Task { await delete() } }
            Button("Cancel", role: .cancel) {}
        } message: {
            Text("This removes the files from the drive. It can't be undone.")
        }
        .alert("Media", isPresented: Binding(
            get: { errorMessage != nil }, set: { if !$0 { errorMessage = nil } }
        )) {
            Button("OK", role: .cancel) { errorMessage = nil }
        } message: {
            Text(errorMessage ?? "")
        }
        .fullScreenCover(item: $playerPresentation) { p in
            PlayerView(url: p.url, subtitleURL: p.subtitleURL, title: p.title,
                       path: p.path, kind: p.kind, image: p.image,
                       seriesId: p.seriesId, season: p.season, episode: p.episode)
        }
    }

    private var metaLine: some View {
        HStack(spacing: 10) {
            if let y = item.year { Text(String(y)) }
            if let r = item.rating, r > 0 { Label(String(format: "%.1f", r), systemImage: "star.fill").foregroundStyle(.yellow) }
            if let m = item.runtimeMin, m > 0 { Text("\(m) min") }
            if let o = item.officialRating { Text(o) }
        }
        .font(.subheadline)
        .foregroundStyle(.secondary)
    }

    private func load() async {
        detail = try? await API.run("jellyfin_item_detail", args: ["item_id": item.id])
    }

    private func play() {
        guard let path = item.path, let url = API.streamURL(path: path) else {
            errorMessage = "No playable file path is available."
            return
        }
        Haptics.impact(.medium)
        playerPresentation = PlayerPresentation(url: url, subtitleURL: API.subtitlesURL(path: path), title: item.name,
                                                path: item.path, kind: "movie", image: item.image)
    }

    private func download() async {
        downloading = true
        downloadStatus = "Downloading…"
        defer { downloading = false }
        guard let path = item.path, let url = API.streamURL(path: path, download: true) else {
            downloadStatus = "Download unavailable"
            errorMessage = "No downloadable file path is available."
            return
        }
        let base = (path as NSString).lastPathComponent
        let filename = (base as NSString).deletingPathExtension + ".mp4"
        downloadFilename = filename
        do {
            try await DownloadManager.shared.download(name: item.name, filename: filename, remoteURL: url)
            Haptics.success()
            downloadStatus = "Downloaded ✓"
        } catch {
            Haptics.error()
            downloadStatus = "Download failed"
            errorMessage = error.localizedDescription
        }
    }

    private func delete() async {
        deleting = true
        defer { deleting = false }
        do {
            let _: JellyfinDeleteResult = try await API.run("jellyfin_delete", args: ["item_id": item.id])
            Haptics.success()
            onDeleted()
            dismiss()
        } catch {
            Haptics.error()
            errorMessage = error.localizedDescription
        }
    }
}

/// Simple wrapping chip layout for genres / cast names.
struct FlowChips: View {
    let items: [String]

    var body: some View {
        FlowLayout(spacing: 6) {
            ForEach(items, id: \.self) { text in
                Text(text)
                    .font(.caption.weight(.medium))
                    .padding(.horizontal, 10).padding(.vertical, 5)
                    .background(Palette.accent.opacity(0.1), in: Capsule())
                    .foregroundStyle(Palette.accent)
            }
        }
    }
}

/// Minimal flow layout (left-to-right wrapping) for chips.
struct FlowLayout: Layout {
    var spacing: CGFloat = 6

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let maxWidth = proposal.width ?? .infinity
        var x: CGFloat = 0, y: CGFloat = 0, rowHeight: CGFloat = 0
        for sub in subviews {
            let size = sub.sizeThatFits(.unspecified)
            if x + size.width > maxWidth, x > 0 {
                x = 0; y += rowHeight + spacing; rowHeight = 0
            }
            x += size.width + spacing
            rowHeight = max(rowHeight, size.height)
        }
        return CGSize(width: maxWidth, height: y + rowHeight)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        var x = bounds.minX, y = bounds.minY, rowHeight: CGFloat = 0
        for sub in subviews {
            let size = sub.sizeThatFits(.unspecified)
            if x + size.width > bounds.maxX, x > bounds.minX {
                x = bounds.minX; y += rowHeight + spacing; rowHeight = 0
            }
            sub.place(at: CGPoint(x: x, y: y), proposal: ProposedViewSize(size))
            x += size.width + spacing
            rowHeight = max(rowHeight, size.height)
        }
    }
}

// ── Downloads (Transmission) ─────────────────────────────────────────────────

struct DownloadsView: View {
    @State private var torrents: [Torrent] = []
    @State private var disk: DiskUsage?
    @State private var loading = true
    @State private var errorMessage: String?
    @State private var showAdd = false

    var body: some View {
        Group {
            if loading && torrents.isEmpty {
                VStack(spacing: 12) {
                    ForEach(0..<5, id: \.self) { _ in SkeletonTile(height: 20) }
                    Spacer()
                }
                .padding(20)
            } else if let errorMessage, torrents.isEmpty {
                ContentUnavailableView("Couldn't load", systemImage: "wifi.exclamationmark", description: Text(errorMessage))
            } else {
                List {
                    if let disk {
                        Section("Drive") {
                            VStack(alignment: .leading, spacing: 8) {
                                HStack {
                                    Text("Free \(fmt(disk.freeGB ?? 0)) GB")
                                        .font(.subheadline.weight(.semibold))
                                    Spacer()
                                    Text("of \(fmt(disk.totalGB ?? 0)) GB")
                                        .font(.caption).foregroundStyle(.secondary)
                                }
                                let used = (disk.usedGB ?? 0) / max(disk.totalGB ?? 1, 1)
                                ProgressPill(progress: used)
                            }
                            .padding(.vertical, 4)
                        }
                    }
                    if !torrents.isEmpty {
                        Section("Downloads") {
                            ForEach(torrents) { torrentRow($0) }
                        }
                    } else {
                        Section {
                            ContentUnavailableView("No downloads", systemImage: "arrow.down.circle", description: Text("Tap + to add a magnet link."))
                        }
                    }
                }
                .listStyle(.insetGrouped)
                .scrollContentBackground(.hidden)
            }
        }
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button { Haptics.impact(); showAdd = true } label: { Image(systemName: "plus") }
            }
        }
        .sheet(isPresented: $showAdd) { AddTorrentSheet { Task { await load() } } }
        .task { await load() }
        .refreshable { await load() }
    }

    private func fmt(_ gb: Double) -> String { String(format: "%.0f", gb) }

    private func torrentRow(_ t: Torrent) -> some View {
        let paused = t.status == "paused"
        return VStack(alignment: .leading, spacing: 6) {
            Text(t.name).font(.subheadline.weight(.medium)).lineLimit(2)
            ProgressPill(progress: t.progress / 100.0)
            HStack {
                PillStatus(text: t.status, color: statusColor(t.status))
                Spacer()
                Text([t.size, t.eta].compactMap { $0 }.joined(separator: " · "))
                    .font(.caption).foregroundStyle(.secondary)
            }
        }
        .padding(.vertical, 4)
        .contentShape(Rectangle())
        .onTapGesture { Task { await togglePause(t) } }
        .swipeActions(edge: .leading) {
            Button { Task { await togglePause(t) } } label: {
                Label(paused ? "Resume" : "Pause", systemImage: paused ? "play.fill" : "pause.fill")
            }
            .tint(paused ? .green : .orange)
        }
        .swipeActions(edge: .trailing, allowsFullSwipe: false) {
            Button(role: .destructive) { Task { await remove(t, deleteData: false) } } label: {
                Label("Remove", systemImage: "xmark")
            }
            Button(role: .destructive) { Task { await remove(t, deleteData: true) } } label: {
                Label("Remove + data", systemImage: "trash")
            }
        }
    }

    private func statusColor(_ s: String) -> Color {
        switch s {
        case "downloading": return .blue
        case "seeding": return .green
        case "paused": return .orange
        case "checking", "queued": return .purple
        default: return .secondary
        }
    }

    private func load() async {
        loading = true
        defer { loading = false }
        do {
            let r: TorrentList = try await API.run("list_torrents")
            torrents = r.torrents
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
        if let d: DiskUsage = try? await API.run("disk_usage") { disk = d }
    }

    private func togglePause(_ t: Torrent) async {
        Haptics.impact()
        do {
            if t.status == "paused" {
                struct R: Decodable { var resumed: Bool }
                let _: R = try await API.run("torrent_resume", args: ["torrent_id": t.id])
            } else {
                struct R: Decodable { var paused: Bool }
                let _: R = try await API.run("torrent_pause", args: ["torrent_id": t.id])
            }
            await load()
        } catch {
            Haptics.error()
            errorMessage = error.localizedDescription
        }
    }

    private func remove(_ t: Torrent, deleteData: Bool) async {
        Haptics.impact()
        do {
            struct R: Decodable { var removed: Bool }
            let _: R = try await API.run("torrent_delete", args: ["torrent_id": t.id, "delete_data": deleteData])
            Haptics.success()
            torrents.removeAll { $0.id == t.id }
            if let d: DiskUsage = try? await API.run("disk_usage") { disk = d }
        } catch {
            Haptics.error()
            errorMessage = error.localizedDescription
        }
    }
}

// ── Add magnet link sheet ────────────────────────────────────────────────────

struct AddTorrentSheet: View {
    @Environment(\.dismiss) private var dismiss
    @State private var magnet = ""
    @State private var adding = false
    @State private var errorMessage: String?
    let onAdded: () -> Void

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    TextField("magnet:… or https://…", text: $magnet, axis: .vertical)
                        .lineLimit(3...6)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                } footer: {
                    Text("Paste a magnet link or a .torrent URL.")
                }
                if let errorMessage {
                    Section {
                        Text(errorMessage).font(.footnote).foregroundStyle(.red)
                    }
                }
            }
            .navigationTitle("Add download")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Add") { Task { await add() } }
                        .disabled(magnet.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || adding)
                }
            }
        }
    }

    private func add() async {
        adding = true
        defer { adding = false }
        let link = magnet.trimmingCharacters(in: .whitespacesAndNewlines)
        do {
            struct R: Decodable { var added: Bool }
            let _: R = try await API.run("add_torrent", args: ["magnet_uri": link])
            Haptics.success()
            onAdded()
            dismiss()
        } catch {
            Haptics.error()
            errorMessage = error.localizedDescription
        }
    }
}

// ── Movies downloaded to the phone ───────────────────────────────────────────

struct DownloadedView: View {
    @ObservedObject private var downloads = DownloadManager.shared
    @State private var playingURL: URL?

    var body: some View {
        Group {
            if downloads.items.isEmpty {
                ContentUnavailableView("Nothing here yet", systemImage: "arrow.down.circle",
                                       description: Text("Open a movie and tap Download to save it for offline watching."))
            } else {
                List {
                    Section("On this iPhone") {
                        ForEach(downloads.items) { item in
                            HStack {
                                VStack(alignment: .leading, spacing: 2) {
                                    Text(item.name).font(.subheadline.weight(.medium)).lineLimit(1)
                                    Text("\(fmt(item.size)) · \(item.date.formatted(date: .abbreviated, time: .omitted))")
                                        .font(.caption).foregroundStyle(.secondary)
                                }
                                Spacer()
                            }
                            .contentShape(Rectangle())
                            .onTapGesture { playingURL = item.url; Haptics.impact() }
                            .swipeActions {
                                Button("Delete", role: .destructive) { downloads.delete(item); Haptics.impact(.light) }
                            }
                        }
                    }
                }
                .listStyle(.insetGrouped)
                .scrollContentBackground(.hidden)
            }
        }
        .task { downloads.refresh() }
        .fullScreenCover(isPresented: Binding(get: { playingURL != nil }, set: { if !$0 { playingURL = nil } })) {
            if let playingURL {
                PlayerView(url: playingURL, subtitleURL: nil, title: playingURL.deletingPathExtension().lastPathComponent)
            }
        }
    }

    private func fmt(_ bytes: Int64) -> String {
        let gb = Double(bytes) / 1e9
        if gb >= 1 { return String(format: "%.1f GB", gb) }
        return String(format: "%.0f MB", Double(bytes) / 1e6)
    }
}

// ── TV series episode list ───────────────────────────────────────────────────

struct SeriesEpisodesView: View {
    let series: JellyfinItem
    @Environment(\.dismiss) private var dismiss
    @State private var episodes: [JellyfinEpisode] = []
    @State private var loading = true
    @State private var errorMessage: String?
    @State private var playerPresentation: PlayerPresentation?
    @State private var playbackByPath: [String: PlaybackRecord] = [:]

    var body: some View {
        NavigationStack {
            Group {
                if loading {
                    VStack(spacing: 12) {
                        ForEach(0..<6, id: \.self) { _ in SkeletonTile(height: 20) }
                        Spacer()
                    }
                    .padding(20)
                } else if let errorMessage {
                    ContentUnavailableView("Couldn't load", systemImage: "wifi.exclamationmark", description: Text(errorMessage))
                } else if episodes.isEmpty {
                    ContentUnavailableView("No episodes", systemImage: "tv", description: Text("This series has no episodes indexed yet."))
                } else {
                    List {
                        ForEach(seasons, id: \.self) { season in
                            Section("Season \(season)") {
                                ForEach(episodes.filter { $0.season == season }) { ep in
                                    let watched = playbackByPath[ep.path ?? ""]?.watched ?? false
                                    Button { play(ep) } label: {
                                        HStack(spacing: 12) {
                                            Text("E\(ep.episode ?? 0)")
                                                .font(.caption.weight(.bold))
                                                .foregroundStyle(.secondary)
                                                .frame(width: 34, alignment: .leading)
                                            Text(ep.name).lineLimit(2)
                                            Spacer()
                                            if watched {
                                                Image(systemName: "checkmark.circle.fill")
                                                    .font(.title3)
                                                    .foregroundStyle(.green)
                                            } else {
                                                Image(systemName: "play.circle.fill")
                                                    .font(.title3)
                                                    .foregroundStyle(Palette.accent)
                                            }
                                        }
                                    }
                                    .foregroundStyle(.primary)
                                    .contextMenu {
                                        Button { Task { await setWatched(ep, watched: !watched) } } label: {
                                            Label(watched ? "Mark unwatched" : "Mark watched",
                                                  systemImage: watched ? "circle" : "checkmark.circle")
                                        }
                                    }
                                }
                            }
                        }
                    }
                    .listStyle(.insetGrouped)
                }
            }
            .navigationTitle(series.name)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItemGroup(placement: .topBarTrailing) {
                    Button { Task { await markAllWatched() } } label: {
                        Image(systemName: "checkmark.rectangle")
                    }
                    Button("Done") { dismiss() }
                }
            }
        }
        .task { await load() }
        .fullScreenCover(item: $playerPresentation) { p in
            PlayerView(url: p.url, subtitleURL: p.subtitleURL, title: p.title,
                       path: p.path, kind: p.kind, image: p.image,
                       seriesId: p.seriesId, season: p.season, episode: p.episode)
        }
    }

    private var seasons: [Int] {
        Array(Set(episodes.compactMap { $0.season })).sorted()
    }

    private func load() async {
        loading = true
        defer { loading = false }
        let localPath = series.path ?? series.id
        do {
            let result: JellyfinEpisodeList
            if series.id.hasPrefix("/") {
                result = try await API.run("local_episodes", args: ["series_path": localPath])
            } else {
                result = try await API.run("jellyfin_episodes", args: ["series_id": series.id])
            }
            episodes = result.episodes
            errorMessage = nil
        } catch {
            if !series.id.hasPrefix("/"),
               let result: JellyfinEpisodeList = try? await API.run("local_episodes", args: ["series_path": localPath]) {
                episodes = result.episodes
                errorMessage = nil
            } else {
                errorMessage = error.localizedDescription
            }
        }
        await refreshStatus()
    }

    private func refreshStatus() async {
        if let s = try? await API.playbackStatus() {
            playbackByPath = Dictionary(uniqueKeysWithValues: s.items.map { ($0.path, $0) })
        }
    }

    private func setWatched(_ ep: JellyfinEpisode, watched: Bool) async {
        guard let path = ep.path else { return }
        try? await API.playbackMarkWatched(path, watched: watched)
        await refreshStatus()
    }

    private func markAllWatched() async {
        Haptics.impact()
        for ep in episodes {
            if let path = ep.path { try? await API.playbackMarkWatched(path, watched: true) }
        }
        await refreshStatus()
    }

    private func play(_ ep: JellyfinEpisode) {
        guard let path = ep.path else { return }
        guard let url = API.streamURL(path: path) else { return }
        Haptics.impact(.medium)
        let label = "\(series.name) S\(ep.season ?? 0)E\(ep.episode ?? 0) · \(ep.name)"
        playerPresentation = PlayerPresentation(url: url, subtitleURL: API.subtitlesURL(path: path), title: label,
                                                path: path, kind: "episode", image: series.image,
                                                seriesId: series.id, season: ep.season, episode: ep.episode)
    }
}
