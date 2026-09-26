import SwiftUI

struct SettingsView: View {
    @AppStorage("serverURL") private var serverURL = ""
    @AppStorage("appearance") private var appearance = "light"
    @State private var showLogs = false

    var body: some View {
        NavigationStack {
            Form {
                Section("Appearance") {
                    Picker("Theme", selection: $appearance) {
                        Text("Light").tag("light")
                        Text("Dark").tag("dark")
                        Text("System").tag("system")
                    }
                    .pickerStyle(.segmented)
                }
                Section("Server") {
                    TextField("Auto (Tailscale + home LAN)", text: $serverURL)
                        .keyboardType(.URL)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                    Text("Leave empty to auto-connect via Tailscale, falling back to your home network. Set a URL only if you want to override it.")
                        .font(.footnote).foregroundStyle(.secondary)
                }
                Section("Diagnostics") {
                    Button { showLogs = true } label: {
                        Label("View app logs", systemImage: "doc.text.magnifyingglass")
                    }
                    Button(role: .destructive) {
                        AppLog.clear()
                        Haptics.success()
                    } label: {
                        Label("Clear logs", systemImage: "trash")
                    }
                }
            }
            .navigationTitle("Settings")
            .sheet(isPresented: $showLogs) { LogViewer() }
        }
    }
}

/// Shows the persistent app log with copy + share options.
struct LogViewer: View {
    @Environment(\.dismiss) private var dismiss
    @State private var text = AppLog.contents()

    var body: some View {
        NavigationStack {
            ScrollView {
                Text(text)
                    .font(.system(.caption, design: .monospaced))
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding()
                    .textSelection(.enabled)
            }
            .navigationTitle("App logs")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Done") { dismiss() }
                }
                ToolbarItem(placement: .topBarLeading) {
                    Button { UIPasteboard.general.string = text; Haptics.success() } label: {
                        Image(systemName: "doc.on.doc")
                    }
                }
            }
            .onAppear { text = AppLog.contents() }
        }
    }
}
