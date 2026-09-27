import SwiftUI

struct ContentView: View {
    @AppStorage("appearance") private var appearance = "light"
    @State private var selection: Tab = .home
    @State private var visited: Set<Tab> = [.home]
    @State private var keyboardOpen = false
    @StateObject private var deviceState = DeviceState()
    @StateObject private var assistantModel = AssistantModel()
    @StateObject private var notifications = NotificationMonitor()

    enum Tab: String, CaseIterable {
        case home, media, food, assistant
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
            .animation(.easeInOut(duration: 0.18), value: selection)
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
        case .home: DevicesView(state: deviceState)
        case .media: MediaView()
        case .food: FoodView()
        case .assistant: AssistantView(model: assistantModel)
        }
    }

    // Anchored matte bottom bar — not a floating capsule.
    private var tabBar: some View {
        HStack(spacing: 6) {
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
                    }
                    .foregroundStyle(isSelected ? Theme.teal : Color.secondary)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 6)
                    .contentShape(Rectangle())
                }
                .buttonStyle(PressableButtonStyle())
            }
        }
        .padding(.horizontal, 8)
        .padding(.top, 6)
        .background(Theme.surface.ignoresSafeArea(edges: .bottom))
        .overlay(alignment: .top) { Divider().opacity(0.6) }
    }

    private func icon(for tab: Tab) -> String {
        switch tab {
        case .home: return "house"
        case .media: return "play.rectangle"
        case .food: return "fork.knife"
        case .assistant: return "bubble.left.and.bubble.right"
        }
    }
}
