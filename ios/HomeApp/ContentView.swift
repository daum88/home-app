import SwiftUI

struct ContentView: View {
    @AppStorage("appearance") private var appearance = "light"
    @State private var selection: Tab = .assistant
    @State private var visited: Set<Tab> = [.assistant]
    @State private var keyboardOpen = false
    @StateObject private var deviceState = DeviceState()
    @StateObject private var assistantModel = AssistantModel()
    @StateObject private var notifications = NotificationMonitor()

    enum Tab: String, CaseIterable {
        case assistant, devices, media, fridge, recipes, shopping, settings
    }

    var body: some View {
        VStack(spacing: 0) {
            ZStack {
                ForEach(Tab.allCases, id: \.self) { tab in
                    if visited.contains(tab) {
                        content(for: tab)
                            .opacity(selection == tab ? 1 : 0)
                            .allowsHitTesting(selection == tab)
                            .accessibilityHidden(selection != tab)
                            .zIndex(selection == tab ? 1 : 0)
                    }
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .animation(.easeInOut(duration: 0.22), value: selection)
            if !keyboardOpen { tabBar }
        }
        .sensoryFeedback(.selection, trigger: selection)
        .onReceive(NotificationCenter.default.publisher(for: UIResponder.keyboardWillShowNotification)) { _ in
            withAnimation(.easeInOut(duration: 0.2)) { keyboardOpen = true }
        }
        .onReceive(NotificationCenter.default.publisher(for: UIResponder.keyboardWillHideNotification)) { _ in
            withAnimation(.easeInOut(duration: 0.2)) { keyboardOpen = false }
        }
        .preferredColorScheme(scheme)
        .task { notifications.start() }
    }

    private var scheme: ColorScheme? {
        switch appearance {
        case "dark": return .dark
        case "system": return nil
        default: return .light
        }
    }

    @ViewBuilder private func content(for tab: Tab) -> some View {
        switch tab {
        case .assistant: AssistantView(model: assistantModel)
        case .devices: DevicesView(state: deviceState)
        case .media: MediaView()
        case .fridge: FridgeView()
        case .recipes: RecipesView()
        case .shopping: ShoppingView()
        case .settings: SettingsView()
        }
    }

    // Floating capsule tab bar with a springing selected pill.
    private var tabBar: some View {
        HStack(spacing: 4) {
            ForEach(Tab.allCases, id: \.self) { tab in
                let isSelected = selection == tab
                Button {
                    withAnimation(.spring(response: 0.35, dampingFraction: 0.8)) {
                        visited.insert(tab)
                        selection = tab
                    }
                } label: {
                    VStack(spacing: 3) {
                        Image(systemName: icon(for: tab))
                            .symbolVariant(isSelected ? .fill : .none)
                            .font(.system(size: 18, weight: .semibold))
                            .contentTransition(.symbolEffect(.replace))
                        Text(tab.rawValue.capitalized)
                            .font(.system(size: 10, weight: isSelected ? .semibold : .medium))
                            .tracking(-0.01)
                            .lineLimit(1)
                            .minimumScaleFactor(0.7)
                    }
                    .foregroundStyle(isSelected ? Palette.accent : Color.secondary)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 8)
                    .background(
                        isSelected ? Palette.accent.opacity(0.13) : Color.clear,
                        in: RoundedRectangle(cornerRadius: 16, style: .continuous)
                    )
                }
                .buttonStyle(PressableButtonStyle())
            }
        }
        .padding(6)
        .background(Color(.secondarySystemGroupedBackground), in: RoundedRectangle(cornerRadius: 26, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 26, style: .continuous)
                .strokeBorder(Color.primary.opacity(0.08), lineWidth: 0.5)
        )
        .shadow(color: .black.opacity(0.08), radius: 18, y: 8)
        .padding(.horizontal, 16)
        .padding(.bottom, 6)
    }

    private func icon(for tab: Tab) -> String {
        switch tab {
        case .assistant: return "bubble.left.and.bubble.right"
        case .devices: return "house"
        case .media: return "film.stack"
        case .fridge: return "refrigerator"
        case .recipes: return "fork.knife"
        case .shopping: return "cart"
        case .settings: return "gearshape"
        }
    }
}
