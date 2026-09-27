import SwiftUI

// ── Continue watching row ──────────────────────────────────────────────────

struct ContinueWatchingRow: View {
    let items: [PlaybackRecord]
    let onPlay: (PlaybackRecord) -> Void
    let onChanged: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Continue watching").font(.subheadline.weight(.semibold)).padding(.horizontal, 16)
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 10) {
                    ForEach(items) { rec in
                        Button { Haptics.impact(); onPlay(rec) } label: {
                            ContinueCard(rec: rec)
                        }
                        .buttonStyle(PressableButtonStyle())
                        .contextMenu {
                            Button { Task { await markWatched(rec) } } label: {
                                Label("Mark watched", systemImage: "checkmark")
                            }
                            Button { Task { await clearProgress(rec) } } label: {
                                Label("Start over", systemImage: "gobackward")
                            }
                        }
                    }
                }
                .padding(.horizontal, 16)
            }
        }
    }

    private func markWatched(_ rec: PlaybackRecord) async {
        try? await API.playbackMarkWatched(rec.path, watched: true)
        onChanged()
    }

    private func clearProgress(_ rec: PlaybackRecord) async {
        try? await API.playbackMarkWatched(rec.path, watched: false)
        try? await API.playbackSave(path: rec.path, position: 0, duration: rec.duration,
                                    title: rec.title ?? "", kind: rec.kind ?? "movie", image: rec.image,
                                    seriesId: rec.seriesId, season: rec.season, episode: rec.episode)
        onChanged()
    }
}

struct ContinueCard: View {
    let rec: PlaybackRecord

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            PosterImage(imagePath: rec.image)
                .frame(width: 84)
                .overlay(alignment: .bottom) {
                    GeometryReader { geo in
                        ZStack(alignment: .leading) {
                            Rectangle().fill(.black.opacity(0.5))
                            Rectangle().fill(Palette.accent)
                                .frame(width: max(0, geo.size.width * progress))
                        }
                    }
                    .frame(height: 3)
                }
                .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
            Text(rec.title ?? rec.path)
                .font(.caption2.weight(.semibold))
                .lineLimit(1)
                .frame(width: 84, alignment: .leading)
            Text(remainingLabel)
                .font(.caption2)
                .foregroundStyle(.secondary)
        }
    }

    private var progress: Double {
        rec.duration > 0 ? min(rec.position / rec.duration, 1) : 0
    }

    private var remainingLabel: String {
        let left = max(0, Int(rec.duration - rec.position))
        if left < 3600 { return "\(left / 60) min left" }
        return "\(left / 3600) h \(left % 3600 / 60) min left"
    }
}
