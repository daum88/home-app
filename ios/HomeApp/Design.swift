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

// ── Design tokens — paper, ink, light ─────────────────────────────────────
enum Palette {
    /// Brand accent (Media tab, tab-bar selection, progress) — deep teal.
    static let accent = Color(hex: "276B67")
    static let screenGradient = LinearGradient(
        colors: [Color(.systemBackground), Color(.systemGroupedBackground)],
        startPoint: .top, endPoint: .bottom)
}

/// The paper/ink/light language: warm paper canvas, charcoal-green ink,
/// deep teal accent, copper highlights, fixed semantic state colours.
enum Theme {
    static let canvas  = Color(hex: "F5F2EB")   // warm paper background
    static let surface = Color(hex: "FCFAF5")   // raised surface
    static let ink     = Color(hex: "182522")   // charcoal-green primary text
    static let teal    = Color(hex: "276B67")   // deep teal accent (selection/actions)
    static let copper  = Color(hex: "BA8550")   // warm amber/copper (time/energy)
    static let night   = Color(hex: "101A1A")   // media night surface
    static let success = Color(hex: "2E7D5B")   // semantic positive
    static let warning = Color(hex: "B7791F")   // semantic warning
    static let danger  = Color(hex: "B3402E")   // semantic danger
    static let bg      = canvas
    static let card    = surface
}

// ── Typography ─────────────────────────────────────────────────────────────
extension Font {
    /// Editorial display face (system serif) for greetings and section leads.
    static func display(_ size: CGFloat) -> Font {
        .system(size: size, weight: .semibold, design: .serif)
    }
}

// ── Reusable components ────────────────────────────────────────────────────

/// Matte paper card: raised surface, hairline ink border, soft shadow.
struct Card<Content: View>: View {
    let content: Content
    init(@ViewBuilder content: () -> Content) { self.content = content() }

    var body: some View {
        content
            .padding(16)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(
                RoundedRectangle(cornerRadius: 20, style: .continuous)
                    .fill(Theme.surface)
            )
            .overlay(
                RoundedRectangle(cornerRadius: 20, style: .continuous)
                    .strokeBorder(Theme.ink.opacity(0.07), lineWidth: 0.5)
            )
            .shadow(color: Theme.ink.opacity(0.05), radius: 10, y: 5)
    }
}

/// Flat glyph tinted with a feature colour — no square tile behind every icon.
struct IconTile: View {
    let systemName: String
    let colors: [Color]

    var body: some View {
        Image(systemName: systemName)
            .font(.system(size: 22, weight: .semibold))
            .foregroundStyle(colors.first ?? Theme.teal)
    }
}

/// Small tinted glyph used in list rows.
struct RowIcon: View {
    let systemName: String
    let tint: Color

    var body: some View {
        Image(systemName: systemName)
            .font(.system(size: 17, weight: .semibold))
            .foregroundStyle(tint)
            .frame(width: 26)
    }
}

/// Compact stat: tinted glyph, large monospaced value, quiet label.
struct StatTile: View {
    let label: String
    let value: String
    let symbol: String
    let tint: Color

    var body: some View {
        VStack(alignment: .leading, spacing: 7) {
            Image(systemName: symbol)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(tint)
            Text(value)
                .font(.system(size: 24, weight: .semibold, design: .rounded))
                .monospacedDigit()
                .minimumScaleFactor(0.6)
                .lineLimit(1)
                .contentTransition(.numericText())
                .foregroundStyle(Theme.ink)
            Text(label)
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(14)
        .background(
            RoundedRectangle(cornerRadius: 16, style: .continuous)
                .fill(Theme.surface)
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
            .background(color.opacity(0.12), in: Capsule())
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
                    .foregroundStyle(Theme.ink)
            }
            .frame(maxWidth: .infinity)
            .padding(.vertical, 10)
            .background(tint.opacity(0.10), in: RoundedRectangle(cornerRadius: 13, style: .continuous))
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

/// Quiet rounded bar with an animated shimmer sweep — skeleton loading placeholder.
struct SkeletonTile: View {
    var height: CGFloat = 14

    @State private var phase: CGFloat = -1

    var body: some View {
        GeometryReader { geo in
            ZStack(alignment: .leading) {
                RoundedRectangle(cornerRadius: height / 2, style: .continuous)
                    .fill(Theme.ink.opacity(0.06))
                RoundedRectangle(cornerRadius: height / 2, style: .continuous)
                    .fill(
                        LinearGradient(colors: [.clear, .white.opacity(0.5), .clear],
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

/// 8px progress pill in the warm copper tone.
struct ProgressPill: View {
    let progress: Double  // 0...1

    var body: some View {
        GeometryReader { geo in
            ZStack(alignment: .leading) {
                Capsule()
                    .fill(Theme.ink.opacity(0.08))
                    .overlay(Capsule().stroke(Theme.ink.opacity(0.06), lineWidth: 0.5))
                Capsule()
                    .fill(Theme.copper)
                    .frame(width: max(geo.size.height, geo.size.width * progress))
            }
        }
        .frame(height: 8)
    }
}

// ── Motion helpers ─────────────────────────────────────────────────────────

/// Restrained fade-and-rise entrance (kept subtle; motion should be purposeful).
struct Entrance: ViewModifier {
    let index: Int
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var shown = false

    func body(content: Content) -> some View {
        content
            .opacity(shown ? 1 : 0)
            .offset(y: (shown || reduceMotion) ? 0 : 10)
            .animation(reduceMotion ? nil : .easeOut(duration: 0.25).delay(Double(index) * 0.04), value: shown)
            .onAppear { shown = true }
    }
}

extension View {
    func entrance(_ index: Int = 0) -> some View { modifier(Entrance(index: index)) }

    /// Apply the warm paper background used by every non-Media tab.
    func matteBackground() -> some View {
        background(Theme.bg.ignoresSafeArea())
    }
}
