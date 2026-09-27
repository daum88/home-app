import Foundation
import UserNotifications

/// Lightweight notification monitor. While the app is running it polls the
/// backend and fires local notifications on events: washer finished, fridge
/// door opened, new movie downloaded. The washer "done" notification is
/// scheduled ahead of time so it also fires if the app is backgrounded.
@MainActor
final class NotificationMonitor: ObservableObject {
    private var timer: Timer?
    private var lastWasherRunning = false
    private var lastDoorOpen = false
    private var lastMovieCount = -1
    private var lastMovieCheck: Date = .distantPast

    func start() {
        guard timer == nil else { return }
        UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound, .badge]) { _, _ in }
        Task { await tick() }  // prime state immediately
        timer = Timer.scheduledTimer(withTimeInterval: 60, repeats: true) { [weak self] _ in
            Task { @MainActor in await self?.tick() }
        }
    }

    private func tick() async {
        await checkWasher()
        await checkFridge()
        await checkMovies()
    }

    private func checkWasher() async {
        guard let w: WasherStatus = try? await API.run("washer_status") else { return }
        let running = ["run", "running", "washing"].contains(w.machineState ?? "")
        if lastWasherRunning && !running {
            notify("Washer done 🧺", "Your laundry is finished.")
        }
        lastWasherRunning = running
        if running, let mins = w.remainingMinutes, mins > 0 {
            schedule(at: Date().addingTimeInterval(TimeInterval(mins) * 60),
                     id: "washer-done", title: "Washer done 🧺", body: "Your laundry is finished.")
        }
    }

    private func checkFridge() async {
        guard let f: FridgeStatus = try? await API.run("fridge_status") else { return }
        let open = (f.fridgeDoorOpen == true) || (f.freezerDoorOpen == true)
        if !lastDoorOpen && open {
            notify("Fridge door open", "The fridge or freezer door is open.")
        }
        lastDoorOpen = open
    }

    private func checkMovies() async {
        guard Date().timeIntervalSince(lastMovieCheck) >= 300 else { return }
        lastMovieCheck = Date()
        guard let list: JellyfinItemList = try? await API.run("jellyfin_library", args: ["media_type": "movie"]) else { return }
        let count = list.items.count
        if lastMovieCount >= 0, count > lastMovieCount {
            notify("New movie 🎬", count - lastMovieCount == 1 ? "A new movie was added to your library." : "\(count - lastMovieCount) new movies were added.")
        }
        lastMovieCount = count
    }

    private func notify(_ title: String, _ body: String) {
        let content = UNMutableNotificationContent()
        content.title = title
        content.body = body
        content.sound = .default
        UNUserNotificationCenter.current().add(UNNotificationRequest(identifier: UUID().uuidString, content: content, trigger: nil))
    }

    private func schedule(at date: Date, id: String, title: String, body: String) {
        let center = UNUserNotificationCenter.current()
        center.removePendingNotificationRequests(withIdentifiers: [id])
        guard date > Date() else { return }
        let content = UNMutableNotificationContent()
        content.title = title
        content.body = body
        content.sound = .default
        let comps = Calendar.current.dateComponents([.year, .month, .day, .hour, .minute], from: date)
        center.add(UNNotificationRequest(identifier: id, content: content, trigger: UNCalendarNotificationTrigger(dateMatching: comps, repeats: false)))
    }
}
