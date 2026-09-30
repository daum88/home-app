import SwiftUI

@main
struct HomeApp: App {
    var body: some Scene {
        WindowGroup {
            ContentView()
                .tint(Palette.accent)
                .task { DownloadManager.shared.cleanTemporaryFiles() }
        }
    }
}
