import SwiftUI

// ── Design tokens ──────────────────────────────────────────────────────────
enum Palette {
    static let accent = Color(red: 0.0, green: 0.45, blue: 0.85)
    static let accentGradient = [
        Color(red: 0.0, green: 0.45, blue: 0.85),
        Color(red: 0.0, green: 0.68, blue: 0.78),
    ]
    static let screenGradient = LinearGradient(
        colors: [Color(.systemBackground), Color(.systemGroupedBackground)],
        startPoint: .top, endPoint: .bottom)
}

// Reusable design components — Apple Liquid Glass + standard materials.

/// Content card with a continuous curve (squircle) and standard material.
struct Card<Content: View>: View {
    let content: Content
    init(@ViewBuilder content: () -> Content) { self.content = content() }

    var body: some View {
        content
            .padding(16)
            .frame(maxWidth: .infinity, alignment: .leading)
            .glassEffect(.regular, in: RoundedRectangle(cornerRadius: 24, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: 24, style: .continuous)
                    .fill(LinearGradient(colors: [.white.opacity(0.4), .white.opacity(0.0)],
                                         startPoint: .top, endPoint: .center))
                    .blendMode(.plusLighter)
            )
            .overlay(
                RoundedRectangle(cornerRadius: 24, style: .continuous)
                    .strokeBorder(Color.primary.opacity(0.06), lineWidth: 0.5)
            )
            .shadow(color: .black.opacity(0.06), radius: 20, y: 10)
    }
}

struct IconTile: View {
    let systemName: String
    let colors: [Color]  // unified: always rendered with the accent tint

    var body: some View {
        Image(systemName: systemName)
            .font(.system(size: 19, weight: .semibold))
            .foregroundStyle(Palette.accent)
            .frame(width: 44, height: 44)
            .background(Palette.accent.opacity(0.12), in: RoundedRectangle(cornerRadius: 13, style: .continuous))
    }
}

struct RowIcon: View {
    let systemName: String
    let tint: Color  // unified: always rendered with the accent tint

    var body: some View {
        Image(systemName: systemName)
            .font(.system(size: 15, weight: .semibold))
            .foregroundStyle(Palette.accent)
            .frame(width: 34, height: 34)
            .background(Palette.accent.opacity(0.12), in: RoundedRectangle(cornerRadius: 10, style: .continuous))
    }
}

struct StatTile: View {
    let label: String
    let value: String
    let symbol: String
    let tint: Color

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Image(systemName: symbol)
                .font(.caption)
                .foregroundStyle(Palette.accent)
            Text(value)
                .font(.system(size: 26, weight: .semibold, design: .rounded))
                .minimumScaleFactor(0.6)
                .lineLimit(1)
            Text(label)
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(14)
        .glassEffect(.regular, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
    }
}

struct PillStatus: View {
    let text: String
    let color: Color

    var body: some View {
        Text(text)
            .font(.caption.weight(.semibold))
            .foregroundStyle(color)
            .padding(.horizontal, 10).padding(.vertical, 5)
            .background(color.opacity(0.15), in: Capsule())
    }
}

/// Tactile action button using Liquid Glass (interactive = scales on press).
struct GlassActionButton: View {
    let label: String
    let systemName: String
    let tint: Color
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            VStack(spacing: 4) {
                Image(systemName: systemName)
                    .font(.system(size: 17, weight: .semibold))
                    .foregroundStyle(tint)
                Text(label)
                    .font(.caption2.weight(.semibold))
                    .foregroundStyle(.primary)
            }
            .frame(maxWidth: .infinity)
            .padding(.vertical, 10)
        }
        .buttonStyle(PressableButtonStyle())
        .glassEffect(.regular.interactive())
    }
}

/// Spring press state: compress to 96% and rebound, per Liquid Glass physics.
struct PressableButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .scaleEffect(configuration.isPressed ? 0.96 : 1)
            .animation(.spring(response: 0.3, dampingFraction: 0.6), value: configuration.isPressed)
    }
}

/// Central haptics helper — light impacts for taps, ticks for toggles,
/// and success/error pulses for actions.
enum Haptics {
    static func impact(_ style: UIImpactFeedbackGenerator.FeedbackStyle = .light) {
        UIImpactFeedbackGenerator(style: style).impactOccurred()
    }
    static func success() { UINotificationFeedbackGenerator().notificationOccurred(.success) }
    static func error() { UINotificationFeedbackGenerator().notificationOccurred(.error) }
    static func warning() { UINotificationFeedbackGenerator().notificationOccurred(.warning) }
    static func selection() { UISelectionFeedbackGenerator().selectionChanged() }
}

/// Gray rounded bar with an animated shimmer sweep — skeleton loading placeholder.
struct SkeletonTile: View {
    var height: CGFloat = 14

    @State private var phase: CGFloat = -1

    var body: some View {
        GeometryReader { geo in
            ZStack(alignment: .leading) {
                RoundedRectangle(cornerRadius: height / 2, style: .continuous)
                    .fill(Color.primary.opacity(0.08))
                RoundedRectangle(cornerRadius: height / 2, style: .continuous)
                    .fill(
                        LinearGradient(colors: [.clear, .white.opacity(0.6), .clear],
                                       startPoint: .leading, endPoint: .trailing)
                    )
                    .frame(width: geo.size.width * 0.5)
                    .offset(x: phase * geo.size.width * 1.2)
                    .blendMode(.plusLighter)
            }
        }
        .frame(height: height)
        .onAppear {
            withAnimation(.linear(duration: 1.1).repeatForever(autoreverses: false)) { phase = 1 }
        }
    }
}

/// 8px frosted pill progress bar for the washer.
struct ProgressPill: View {
    let progress: Double  // 0...1

    var body: some View {
        GeometryReader { geo in
            ZStack(alignment: .leading) {
                Capsule()
                    .fill(Color.primary.opacity(0.08))
                    .overlay(Capsule().stroke(Color.primary.opacity(0.06), lineWidth: 0.5))
                Capsule()
                    .fill(Palette.accent)
                    .frame(width: max(geo.size.height, geo.size.width * progress))
            }
        }
        .frame(height: 8)
    }
}
