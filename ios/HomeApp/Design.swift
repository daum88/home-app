import SwiftUI

// ── Hex colour helper ──────────────────────────────────────────────────────
extension Color {
    init(hex: String) {
        let s = hex.trimmingCharacters(in: CharacterSet(charactersIn: "#"))
        var v: UInt64 = 0
        for c in s { v = (v << 4) | UInt64(c.hexDigitValue ?? 0) }
        let r = Double((v >> 16) & 0xFF) / 255
        let g = Double((v >> 8) & 0xFF) / 255
        let b = Double(v & 0xFF) / 255
        self.init(red: r, green: g, blue: b)
    }
}

// ── Design tokens ──────────────────────────────────────────────────────────
enum Palette {
    /// Brand accent (Media tab, tab-bar selection, progress) — Blue Slate.
    static let accent = Color(hex: "57737a")
    /// Background gradient for the media tab.
    static let screenGradient = LinearGradient(
        colors: [Color(.systemBackground), Color(.systemGroupedBackground)],
        startPoint: .top, endPoint: .bottom)
}

/// The icy aqua → ink palette. Flat, calm, one cohesive temperature.
enum Theme {
    static let frozen = Color(hex: "c9fbff")   // lightest — chips, light tiles
    static let icy    = Color(hex: "c2fcf7")   // light aqua — secondary surfaces
    static let pearl  = Color(hex: "85bdbf")   // accent — progress, positive
    static let slate  = Color(hex: "57737a")   // main accent — icons, buttons
    static let ink    = Color(hex: "040f0f")   // dark — text, hero surfaces
    static let bg     = Color(red: 0.925, green: 0.985, blue: 0.99)  // icy white

    /// Functional danger tint (kept red so errors/doors read clearly).
    static let danger = Color(red: 0.79, green: 0.28, blue: 0.28)
}

// Reusable design components — matte surfaces, soft shadows, flat colour.

/// Matte content card: white surface, hairline ink border, soft shadow.
struct Card<Content: View>: View {
    let content: Content
    init(@ViewBuilder content: () -> Content) { self.content = content() }

    var body: some View {
        content
            .padding(16)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(
                RoundedRectangle(cornerRadius: 20, style: .continuous)
                    .fill(Color(.secondarySystemGroupedBackground))
            )
            .overlay(
                RoundedRectangle(cornerRadius: 20, style: .continuous)
                    .strokeBorder(Theme.ink.opacity(0.06), lineWidth: 0.5)
            )
            .shadow(color: Theme.ink.opacity(0.06), radius: 12, y: 6)
    }
}

/// Apple-Home-style feature tile: white glyph on a flat coloured square.
struct IconTile: View {
    let systemName: String
    let colors: [Color]

    var body: some View {
        let tint = colors.first ?? Theme.slate
        Image(systemName: systemName)
            .font(.system(size: 18, weight: .semibold))
            .foregroundStyle(.white)
            .frame(width: 46, height: 46)
            .background(tint, in: RoundedRectangle(cornerRadius: 13, style: .continuous))
            .shadow(color: tint.opacity(0.28), radius: 6, y: 3)
    }
}

/// Small coloured icon used in list rows — white glyph on a flat tinted tile.
struct RowIcon: View {
    let systemName: String
    let tint: Color

    var body: some View {
        Image(systemName: systemName)
            .font(.system(size: 14, weight: .semibold))
            .foregroundStyle(.white)
            .frame(width: 34, height: 34)
            .background(tint, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
            .shadow(color: tint.opacity(0.25), radius: 4, y: 2)
    }
}

/// Compact stat tile: matte surface, coloured icon, large rounded value.
struct StatTile: View {
    let label: String
    let value: String
    let symbol: String
    let tint: Color

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Image(systemName: symbol)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(.white)
                .frame(width: 30, height: 30)
                .background(tint, in: RoundedRectangle(cornerRadius: 9, style: .continuous))
            Text(value)
                .font(.system(size: 24, weight: .semibold, design: .rounded))
                .minimumScaleFactor(0.6)
                .lineLimit(1)
                .contentTransition(.numericText())
            Text(label)
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(14)
        .background(
            RoundedRectangle(cornerRadius: 16, style: .continuous)
                .fill(Color(.secondarySystemGroupedBackground))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 16, style: .continuous)
                .strokeBorder(Theme.ink.opacity(0.05), lineWidth: 0.5)
        )
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
            .background(color.opacity(0.14), in: Capsule())
    }
}

/// Tactile matte action button (flat tint, scale on press).
struct GlassActionButton: View {
    let label: String
    let systemName: String
    let tint: Color
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            VStack(spacing: 4) {
                Image(systemName: systemName)
                    .font(.system(size: 16, weight: .semibold))
                    .foregroundStyle(tint)
                Text(label)
                    .font(.caption2.weight(.semibold))
                    .foregroundStyle(.primary)
            }
            .frame(maxWidth: .infinity)
            .padding(.vertical, 10)
            .background(tint.opacity(0.12), in: RoundedRectangle(cornerRadius: 13, style: .continuous))
        }
        .buttonStyle(PressableButtonStyle())
    }
}

/// Spring press state: compress to 96% and rebound.
struct PressableButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .scaleEffect(configuration.isPressed ? 0.96 : 1)
            .animation(.spring(response: 0.3, dampingFraction: 0.6), value: configuration.isPressed)
    }
}

/// Central haptics helper.
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
                    .fill(Color.primary.opacity(0.07))
                RoundedRectangle(cornerRadius: height / 2, style: .continuous)
                    .fill(
                        LinearGradient(colors: [.clear, .white.opacity(0.55), .clear],
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

/// 8px progress pill in the accent tone.
struct ProgressPill: View {
    let progress: Double  // 0...1

    var body: some View {
        GeometryReader { geo in
            ZStack(alignment: .leading) {
                Capsule()
                    .fill(Color.primary.opacity(0.08))
                    .overlay(Capsule().stroke(Color.primary.opacity(0.06), lineWidth: 0.5))
                Capsule()
                    .fill(Theme.pearl)
                    .frame(width: max(geo.size.height, geo.size.width * progress))
            }
        }
        .frame(height: 8)
    }
}

// ── Motion helpers ─────────────────────────────────────────────────────────

/// Fade-and-rise entrance with a small per-index stagger, for "alive" lists.
struct StaggeredEntrance: ViewModifier {
    let index: Int
    @State private var shown = false

    func body(content: Content) -> some View {
        content
            .opacity(shown ? 1 : 0)
            .offset(y: shown ? 0 : 16)
            .animation(.spring(response: 0.55, dampingFraction: 0.86)
                        .delay(Double(index) * 0.055), value: shown)
            .onAppear { shown = true }
    }
}

extension View {
    func entrance(_ index: Int = 0) -> some View { modifier(StaggeredEntrance(index: index)) }

    /// Apply the calm icy matte background used by every non-Media tab.
    func matteBackground() -> some View {
        background(Theme.bg.ignoresSafeArea())
    }
}
