import SwiftUI
import AVKit
import AVFAudio
import HomeCore

/// Full-screen video player with loading spinner, error handling and a
/// subtitle overlay (parsed from WebVTT served by the backend).
struct PlayerView: View {
    let url: URL
    let subtitleURL: URL?
    let title: String
    let path: String?
    let kind: String
    let image: String?
    let seriesId: String?
    let season: Int?
    let episode: Int?

    init(url: URL, subtitleURL: URL?, title: String,
         path: String? = nil, kind: String = "movie", image: String? = nil,
         seriesId: String? = nil, season: Int? = nil, episode: Int? = nil) {
        self.url = url
        self.subtitleURL = subtitleURL
        self.title = title
        self.path = path
        self.kind = kind
        self.image = image
        self.seriesId = seriesId
        self.season = season
        self.episode = episode
    }

    @Environment(\.dismiss) private var dismiss
    @State private var player: AVPlayer?
    @State private var isLoading = true
    @State private var errorMessage: String?
    @State private var observers: [NSKeyValueObservation] = []
    @State private var subtitleText: String?
    @State private var subtitleTimer: Timer?
    @State private var resumeDecision = ResumeDecision()
    @State private var saveTimer: Timer?

    var body: some View {
        ZStack {
            Color.black.ignoresSafeArea()

            VideoPlayer(player: player)
                .ignoresSafeArea()
                .opacity(isLoading || errorMessage != nil ? 0 : 1)

            if let subtitleText {
                Text(subtitleText)
                    .font(.system(size: 17, weight: .semibold))
                    .foregroundStyle(.white)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, 12)
                    .padding(.vertical, 6)
                    .background(.black.opacity(0.55), in: RoundedRectangle(cornerRadius: 6, style: .continuous))
                    .frame(maxWidth: .infinity, alignment: .center)
                    .padding(.horizontal, 20)
                    .padding(.bottom, 40)
                    .frame(maxHeight: .infinity, alignment: .bottom)
            }

            if let errorMessage {
                VStack(spacing: 16) {
                    Image(systemName: "exclamationmark.triangle.fill")
                        .font(.system(size: 44))
                        .foregroundStyle(.yellow)
                    Text("Couldn't play").font(.headline).foregroundStyle(.white)
                    Text(errorMessage)
                        .font(.subheadline)
                        .foregroundStyle(.white.opacity(0.8))
                        .multilineTextAlignment(.center)
                    HStack(spacing: 12) {
                        Button("Retry") { retry() }
                            .buttonStyle(.borderedProminent)
                        Button("Close") { dismiss() }
                            .buttonStyle(.borderedProminent)
                            .tint(.white.opacity(0.2))
                    }
                }
                .padding(28)
            } else if isLoading {
                VStack(spacing: 14) {
                    ProgressView().controlSize(.large).tint(.white)
                    Text("Loading…").font(.subheadline).foregroundStyle(.white.opacity(0.85))
                }
            }
        }
        .overlay(alignment: .topLeading) {
            Button { dismiss() } label: {
                Image(systemName: "chevron.down")
                    .font(.title3.weight(.bold))
                    .foregroundStyle(.white)
                    .padding(12)
                    .background(.black.opacity(0.45), in: Circle())
            }
            .padding(.top, 8)
            .padding(.leading, 12)
        }
        .onAppear { setup() }
        .onDisappear {
            saveProgress()
            player?.pause()
            subtitleTimer?.invalidate()
            saveTimer?.invalidate()
            observers.forEach { $0.invalidate() }
            observers.removeAll()
        }
    }

    private func retry() {
        player?.pause()
        subtitleTimer?.invalidate()
        saveTimer?.invalidate()
        observers.forEach { $0.invalidate() }
        observers.removeAll()
        player = nil
        subtitleText = nil
        resumeDecision = ResumeDecision()
        errorMessage = nil
        isLoading = true
        setup()
    }

    private func setup() {
        guard player == nil else { return }
        // Ensure audio plays even when the phone's mute switch is on.
        try? AVAudioSession.sharedInstance().setCategory(.playback, mode: .moviePlayback)
        try? AVAudioSession.sharedInstance().setActive(true)

        let p = AVPlayer(url: url)
        player = p
        attachObservers(to: p)
        p.play()
        if subtitleURL != nil { loadSubtitles() }
        if let path {
            startSaveTimer()
            Task {
                if let rec = try? await API.playbackGet(path) {
                    await MainActor.run { resumeIfReady(position: rec.position) }
                }
            }
        }
    }

    private func attachObservers(to p: AVPlayer) {
        let statusObs = p.observe(\.timeControlStatus, options: [.initial, .new]) { player, _ in
            DispatchQueue.main.async {
                if errorMessage != nil { return }
                switch player.timeControlStatus {
                case .playing:
                    isLoading = false
                case .waitingToPlayAtSpecifiedRate:
                    isLoading = true
                case .paused:
                    if player.currentItem?.status == .readyToPlay { isLoading = false }
                @unknown default:
                    break
                }
            }
        }
        observers.append(statusObs)

        if let item = p.currentItem {
            let itemObs = item.observe(\.status, options: [.initial, .new]) { item, _ in
                DispatchQueue.main.async {
                    switch item.status {
                    case .failed:
                        errorMessage = item.error?.localizedDescription ?? "The video couldn't be loaded."
                        AppLog.error("Player failed: \(errorMessage ?? "unknown")")
                        isLoading = false
                    case .readyToPlay:
                        resumeIfReady(duration: item.duration.seconds)
                    default:
                        isLoading = true
                    }
                }
            }
            observers.append(itemObs)
            let durationObs = item.observe(\.duration, options: [.initial, .new]) { item, _ in
                DispatchQueue.main.async { resumeIfReady(duration: item.duration.seconds) }
            }
            observers.append(durationObs)
        }
    }

    private func resumeIfReady(position: Double? = nil, duration: Double? = nil) {
        var target: Double?
        if let position { target = resumeDecision.receivePosition(position) }
        if let duration { target = resumeDecision.receiveDuration(duration) }
        if let target {
            player?.seek(to: CMTime(seconds: target, preferredTimescale: 600),
                         toleranceBefore: .zero, toleranceAfter: .zero)
        }
    }

    // ── Resume / progress persistence ───────────────────────────────────────

    private func startSaveTimer() {
        saveTimer?.invalidate()
        saveTimer = Timer.scheduledTimer(withTimeInterval: 5, repeats: true) { _ in
            saveProgress()
        }
    }

    private func saveProgress() {
        guard let path, let p = player, let item = p.currentItem else { return }
        let dur = item.duration.seconds
        guard dur.isFinite, dur > 0 else { return }
        let pos = p.currentTime().seconds
        guard pos.isFinite, pos >= 0 else { return }
        Task {
            try? await API.playbackSave(path: path, position: pos, duration: dur,
                                        title: title, kind: kind, image: image,
                                        seriesId: seriesId, season: season, episode: episode)
        }
    }

    // ── Subtitles (text overlay synced to playback) ──────────────────────────

    private func loadSubtitles() {
        guard let subtitleURL else { return }
        Task {
            do {
                let (data, _) = try await URLSession.shared.data(from: subtitleURL)
                guard let vtt = String(data: data, encoding: .utf8) else { return }
                let cues = parseWebVTT(vtt)
                guard !cues.isEmpty else { return }
                await MainActor.run {
                    startSubtitleTimer(cues: cues)
                }
            } catch {
                AppLog.error("subtitles: \(error.localizedDescription)")
            }
        }
    }

    private func startSubtitleTimer(cues: [SubtitleCue]) {
        subtitleTimer?.invalidate()
        subtitleTimer = Timer.scheduledTimer(withTimeInterval: 0.25, repeats: true) { _ in
            let t = player?.currentTime().seconds ?? 0
            let cue = cues.first(where: { t >= $0.start && t <= $0.end })
            DispatchQueue.main.async {
                subtitleText = cue?.text
            }
        }
    }

    private func parseWebVTT(_ vtt: String) -> [SubtitleCue] {
        var cues: [SubtitleCue] = []
        let lines = vtt.components(separatedBy: .newlines)
        var i = 0
        while i < lines.count {
            let line = lines[i].trimmingCharacters(in: .whitespaces)
            if line.contains("-->") {
                let parts = line.components(separatedBy: "-->")
                if parts.count == 2 {
                    let start = parseTimestamp(parts[0])
                    let end = parseTimestamp(parts[1])
                    var text: [String] = []
                    i += 1
                    while i < lines.count {
                        let t = lines[i].trimmingCharacters(in: .whitespaces)
                        if t.isEmpty || t.contains("-->") { break }
                        text.append(t)
                        i += 1
                    }
                    cues.append(SubtitleCue(start: start, end: end, text: text.joined(separator: "\n")))
                    continue
                }
            }
            i += 1
        }
        return cues
    }

    private func parseTimestamp(_ s: String) -> TimeInterval {
        let clean = s.trimmingCharacters(in: .whitespaces).replacingOccurrences(of: ",", with: ".")
        let parts = clean.split(separator: ":").map(String.init)
        if parts.count == 3 {
            return (Double(parts[0]) ?? 0) * 3600 + (Double(parts[1]) ?? 0) * 60 + (Double(parts[2]) ?? 0)
        } else if parts.count == 2 {
            return (Double(parts[0]) ?? 0) * 60 + (Double(parts[1]) ?? 0)
        }
        return 0
    }
}

struct SubtitleCue {
    let start: TimeInterval
    let end: TimeInterval
    let text: String
}

/// Identifiable wrapper so `.fullScreenCover(item:)` can present the player.
struct PlayerPresentation: Identifiable {
    let id = UUID()
    let url: URL
    let subtitleURL: URL?
    let title: String
    var path: String?
    var kind: String = "movie"
    var image: String?
    var seriesId: String?
    var season: Int?
    var episode: Int?
}
