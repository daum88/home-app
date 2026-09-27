import SwiftUI
import AVFoundation
import Speech

struct Message: Identifiable {
    let id = UUID()
    let role: String   // "user" | "assistant"
    let content: String
    var thinking = false
}

@MainActor
final class AssistantModel: ObservableObject {
    @Published var messages: [Message] = []
    @Published var input = ""
    @Published var busy = false
    @Published var listening = false
    @Published var speakReplies = true

    private let synth = AVSpeechSynthesizer()
    private let recognizer = SFSpeechRecognizer(locale: Locale(identifier: "en-US"))
    private let audioEngine = AVAudioEngine()
    private var request: SFSpeechAudioBufferRecognitionRequest?

    func send(_ text: String? = nil, fromVoice: Bool = false) {
        let t = (text ?? input).trimmingCharacters(in: .whitespacesAndNewlines)
        guard !t.isEmpty, !busy else { return }
        Haptics.impact(.light)
        input = ""
        messages.append(Message(role: "user", content: t))
        let thinking = Message(role: "assistant", content: "", thinking: true)
        messages.append(thinking)
        busy = true
        Task {
            do {
                let reply = try await API.chat(t)
                messages.removeAll { $0.id == thinking.id }
                messages.append(Message(role: "assistant", content: reply))
                if fromVoice && speakReplies { speak(reply) }
            } catch {
                messages.removeAll { $0.id == thinking.id }
                messages.append(Message(role: "assistant", content: "⚠️ \(error.localizedDescription)"))
            }
            busy = false
        }
    }

    private func speak(_ text: String) {
        let u = AVSpeechUtterance(string: text)
        u.voice = AVSpeechSynthesisVoice(language: "en-US")
        synth.speak(u)
    }

    func toggleMic() { Haptics.impact(.medium); listening ? stopListening() : startListening() }

    func startListening() {
        guard let recognizer, recognizer.isAvailable else { return }
        SFSpeechRecognizer.requestAuthorization { [weak self] status in
            guard status == .authorized else { return }
            DispatchQueue.main.async { self?.beginListening() }
        }
    }

    private func beginListening() {
        guard let recognizer else { return }
        let request = SFSpeechAudioBufferRecognitionRequest()
        self.request = request
        request.shouldReportPartialResults = false
        let inputNode = audioEngine.inputNode
        let format = inputNode.outputFormat(forBus: 0)
        inputNode.installTap(onBus: 0, bufferSize: 1024, format: format) { buffer, _ in
            request.append(buffer)
        }
        audioEngine.prepare()
        do {
            try audioEngine.start()
            listening = true
        } catch {
            request.endAudio()
            self.request = nil
            return
        }
        recognizer.recognitionTask(with: request) { [weak self] result, error in
            if let result, result.isFinal {
                let text = result.bestTranscription.formattedString
                DispatchQueue.main.async {
                    self?.stopListening()
                    self?.send(text, fromVoice: true)
                }
            } else if error != nil {
                DispatchQueue.main.async { self?.stopListening() }
            }
        }
    }

    func stopListening() {
        audioEngine.stop()
        audioEngine.inputNode.removeTap(onBus: 0)
        request?.endAudio()
        request = nil
        listening = false
    }
}

// A calm, flat "ink" orb (Siri-style presence) shown while idle.
struct GlowingOrb: View {
    @State private var pulse = false

    var body: some View {
        ZStack {
            Circle()
                .fill(Theme.ink)
                .frame(width: 132, height: 132)
                .overlay(Circle().stroke(Theme.pearl.opacity(0.7), lineWidth: 1.5))
                .shadow(color: Theme.ink.opacity(0.25), radius: 18, y: 8)
            Image(systemName: "sparkles")
                .font(.system(size: 42, weight: .medium))
                .foregroundStyle(Theme.frozen)
        }
        .frame(width: 200, height: 200)
        .scaleEffect(pulse ? 1.05 : 0.95)
        .animation(.easeInOut(duration: 2.4).repeatForever(autoreverses: true), value: pulse)
        .onAppear { pulse = true }
    }
}

struct AssistantView: View {
    @ObservedObject var model: AssistantModel

    private let suggestions: [(String, String, String)] = [
        ("Morning briefing", "sun.and.horizon.fill", "Give me a morning briefing"),
        ("Washer status", "washer.fill", "Is the washer done?"),
        ("What's in my fridge?", "refrigerator.fill", "What is in my fridge?"),
        ("Recipe ideas", "book.fill", "Suggest 3 recipes using what is in my fridge"),
        ("Expiring soon", "clock.badge.exclamationmark.fill", "What expires this week?"),
    ]

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                if model.messages.isEmpty {
                    idleState
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                } else {
                    chatList
                }
                inputBar
            }
            .navigationTitle("Assistant")
            .navigationBarTitleDisplayMode(.large)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button { model.speakReplies.toggle() } label: {
                        Image(systemName: model.speakReplies ? "speaker.wave.2.fill" : "speaker.slash.fill")
                    }
                }
            }
        }
    }

    // ── Idle placeholder ─────────────────────────────────────────────────────
    private var idleState: some View {
        VStack(spacing: 20) {
            Spacer()
            GlowingOrb()
            Text("How can I help?")
                .font(.title2.weight(.semibold))
                .tracking(-0.02)
            Text("Ask about your washer, fridge, recipes, downloads, or files.")
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 32)
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 8) {
                    ForEach(suggestions, id: \.0) { s in
                        Button { model.send(s.2) } label: {
                            Label(s.0, systemImage: s.1)
                                .font(.subheadline.weight(.medium))
                        }
                        .buttonStyle(.bordered)
                        .buttonBorderShape(.capsule)
                        .tint(Theme.slate)
                    }
                }
                .padding(.horizontal, 20)
            }
            Spacer()
            Spacer()
        }
    }

    // ── Chat ────────────────────────────────────────────────────────────────
    private var chatList: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 10) {
                    ForEach(model.messages) { m in Bubble(m: m) }
                }
                .padding()
            }
            .onChange(of: model.messages.count) {
                if let last = model.messages.last { proxy.scrollTo(last.id, anchor: .bottom) }
            }
        }
    }

    // ── Input bar (Liquid Glass) ─────────────────────────────────────────────
    private var inputBar: some View {
        HStack(spacing: 10) {
            Button { model.toggleMic() } label: {
                Image(systemName: model.listening ? "mic.fill" : "mic")
                    .font(.system(size: 20))
                    .foregroundStyle(model.listening ? .white : Theme.slate)
                    .frame(width: 44, height: 44)
                    .background(model.listening ? Theme.danger : Theme.slate.opacity(0.12), in: Circle())
            }
            TextField("Ask anything…", text: $model.input)
                .padding(.horizontal, 14).padding(.vertical, 10)
                .background(Color(.secondarySystemBackground), in: Capsule())
                .onSubmit { model.send() }
            Button { model.send() } label: {
                Image(systemName: "arrow.up")
                    .font(.system(size: 17, weight: .semibold))
                    .frame(width: 44, height: 44)
            }
            .buttonStyle(.borderedProminent)
            .buttonBorderShape(.circle)
            .tint(Theme.ink)
            .disabled(model.busy)
        }
        .padding(.horizontal, 16).padding(.vertical, 8)
        .background(Color(.secondarySystemGroupedBackground))
        .overlay(alignment: .top) { Divider() }
    }
}

struct Bubble: View {
    let m: Message
    var body: some View {
        HStack {
            if m.role == "user" { Spacer(minLength: 48) }
            Text(m.thinking ? "…" : m.content)
                .padding(.horizontal, 15).padding(.vertical, 11)
                .foregroundStyle(m.role == "user" ? .white : .primary)
                .background {
                    if m.role == "user" {
                        RoundedRectangle(cornerRadius: 18, style: .continuous)
                            .fill(Theme.ink)
                    } else {
                        RoundedRectangle(cornerRadius: 18, style: .continuous)
                            .fill(Color(.secondarySystemGroupedBackground))
                    }
                }
            if m.role != "user" { Spacer(minLength: 48) }
        }
    }
}
