import SwiftUI

/// Full-screen, step-at-a-time cooking mode with large legible text.
struct CookModeView: View {
    let name: String
    let steps: [String]

    @Environment(\.dismiss) private var dismiss
    @State private var index = 0

    var body: some View {
        ZStack {
            Color(.systemBackground).ignoresSafeArea()

            VStack(spacing: 0) {
                HStack {
                    Text(name).font(.subheadline.weight(.semibold)).lineLimit(1)
                    Spacer()
                    Button { dismiss() } label: {
                        Image(systemName: "xmark.circle.fill")
                            .font(.system(size: 26))
                            .foregroundStyle(.secondary)
                    }
                }
                .padding(.horizontal, 20).padding(.top, 16)

                ProgressView(value: Double(index + 1), total: Double(steps.count))
                    .tint(Theme.teal)
                    .padding(.horizontal, 20).padding(.top, 12)

                ScrollView {
                    Text(steps[index])
                        .font(.system(size: 30, weight: .semibold, design: .rounded))
                        .tracking(-0.01)
                        .lineSpacing(8)
                        .padding(.horizontal, 28)
                        .padding(.top, 44)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
                .id(index)

                HStack {
                    Button {
                        Haptics.impact(.light)
                        withAnimation(.spring(response: 0.35, dampingFraction: 0.8)) { index = max(0, index - 1) }
                    } label: {
                        Image(systemName: "chevron.left")
                            .font(.title2.weight(.bold))
                            .foregroundStyle(.primary)
                            .frame(width: 60, height: 60)
                            .background(.regularMaterial, in: Circle())
                    }
                    .disabled(index == 0)
                    .opacity(index == 0 ? 0.35 : 1)

                    Spacer()

                    Button {
                        if index < steps.count - 1 {
                            Haptics.impact(.light)
                            withAnimation(.spring(response: 0.35, dampingFraction: 0.8)) { index += 1 }
                        } else {
                            Haptics.success()
                            dismiss()
                        }
                    } label: {
                        Text(index == steps.count - 1 ? "Done" : "Next")
                            .font(.headline)
                            .foregroundStyle(.white)
                            .frame(width: 140, height: 60)
                            .background(Theme.ink, in: Capsule())
                    }
                }
                .padding(.horizontal, 24).padding(.bottom, 20)
            }
        }
    }
}
