import SwiftUI

// ── Models (bundled study.json) ────────────────────────────────────────────
struct StudyData: Codable {
    let semester: String
    let generated: String
    let courses: [StudyCourse]
}

struct StudyCourse: Codable, Identifiable, Hashable {
    let id: String
    let code: String
    let name: String
    let english: String
    let source: String
    let grading: [StudyGrade]
    let schedule: [StudySlot]
    let exams: [StudyEvent]
    let deadlines: [StudyDeadline]
}

struct StudyGrade: Codable, Hashable { let label: String; let value: String }
struct StudySlot: Codable, Hashable { let day: String; let time: String; let room: String; let type: String }
struct StudyEvent: Codable, Hashable { let what: String; let date: String; let time: String; let room: String }
struct StudyDeadline: Codable, Hashable { let what: String; let date: String; let time: String }

// ── Date helpers ───────────────────────────────────────────────────────────
private let isoDay: DateFormatter = {
    let f = DateFormatter(); f.dateFormat = "yyyy-MM-dd"; f.locale = Locale(identifier: "en_US_POSIX")
    return f
}()

private func studyDate(_ iso: String) -> Date? { isoDay.date(from: String(iso.prefix(10))) }

private func daysLeft(_ iso: String) -> Int? {
    guard let d = studyDate(iso) else { return nil }
    let today = Calendar.current.startOfDay(for: .now)
    return Calendar.current.dateComponents([.day], from: today, to: d).day
}

// ── Study tab ──────────────────────────────────────────────────────────────
struct StudyView: View {
    @State private var data: StudyData?

    private var courses: [StudyCourse] { data?.courses ?? [] }

    /// Next upcoming deadline across all courses (soonest first).
    private var upcoming: [(course: StudyCourse, deadline: StudyDeadline)] {
        courses
            .flatMap { c in c.deadlines.map { (c, $0) } }
            .filter { (studyDate($0.1.date) ?? .distantPast) >= Calendar.current.startOfDay(for: .now) }
            .sorted { $0.1.date < $1.1.date }
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 22) {
                    header
                    if let next = upcoming.first {
                        upNextCard(next).entrance(0)
                        comingUpSection(Array(upcoming.dropFirst())).entrance(1)
                    } else {
                        noDeadlines.entrance(0)
                    }
                    thisWeekSection.entrance(2)
                    coursesSection.entrance(3)
                }
                .padding(16)
                .padding(.bottom, 24)
            }
            .matteBackground()
            .navigationTitle("Study")
            .navigationBarTitleDisplayMode(.inline)
            .navigationDestination(for: StudyCourse.self) { CourseDetailView(course: $0) }
        }
        .task { load() }
    }

    private func load() {
        guard data == nil else { return }
        if let url = Bundle.main.url(forResource: "study", withExtension: "json"),
           let d = try? Data(contentsOf: url),
           let decoded = try? JSONDecoder().decode(StudyData.self, from: d) {
            data = decoded
        }
    }

    // ── Header ────────────────────────────────────────────────────────────
    private var header: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("Study")
                .font(.display(30))
                .foregroundStyle(Theme.ink)
            if let s = data?.semester {
                Text("\(s) · \(courses.count) courses")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            }
        }
    }

    // ── Hero: single next deadline ─────────────────────────────────────────
    private func upNextCard(_ item: (course: StudyCourse, deadline: StudyDeadline)) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text("UP NEXT")
                    .font(.caption.weight(.bold))
                    .tracking(1.2)
                    .foregroundStyle(Theme.teal)
                Spacer()
                if let d = daysLeft(item.deadline.date) {
                    Text(d < 0 ? "overdue" : d == 0 ? "today" : d == 1 ? "tomorrow" : "\(d) days")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(d <= 2 ? Theme.danger : Theme.teal)
                        .padding(.horizontal, 10).padding(.vertical, 4)
                        .background((d <= 2 ? Theme.danger : Theme.teal).opacity(0.12), in: Capsule())
                }
            }
            Text(item.deadline.what)
                .font(.system(size: 19, weight: .semibold, design: .rounded))
                .foregroundStyle(Theme.ink)
                .fixedSize(horizontal: false, vertical: true)
            HStack(spacing: 8) {
                Text(item.course.name)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(Theme.teal)
                Text("·").foregroundStyle(.secondary)
                Text("\(prettyDate(item.deadline.date)) at \(item.deadline.time)")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            }
        }
        .padding(18)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(
            RoundedRectangle(cornerRadius: 22, style: .continuous)
                .fill(Theme.surface)
        )
        .overlay(
            RoundedRectangle(cornerRadius: 22, style: .continuous)
                .strokeBorder(Theme.teal.opacity(0.18), lineWidth: 1)
        )
        .shadow(color: Theme.ink.opacity(0.06), radius: 12, y: 6)
    }

    // ── Coming up list ─────────────────────────────────────────────────────
    private func comingUpSection(_ items: [(course: StudyCourse, deadline: StudyDeadline)]) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Coming up").font(.headline).foregroundStyle(Theme.ink)
            ForEach(Array(items.prefix(5)), id: \.deadline) { item in
                deadlineRow(item)
            }
        }
    }

    private func deadlineRow(_ item: (course: StudyCourse, deadline: StudyDeadline)) -> some View {
        HStack(spacing: 12) {
            VStack(alignment: .leading, spacing: 2) {
                Text(item.deadline.what)
                    .font(.subheadline.weight(.medium))
                    .foregroundStyle(Theme.ink)
                    .lineLimit(1)
                Text("\(item.course.name) · \(prettyDate(item.deadline.date))")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            Spacer()
            if let d = daysLeft(item.deadline.date) {
                deadlineBadge(d)
            }
        }
        .padding(12)
        .background(Theme.surface, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
    }

    private func deadlineBadge(_ d: Int) -> some View {
        let color: Color = d < 0 ? Theme.danger : d == 0 ? Theme.danger : d <= 2 ? Theme.warning : d <= 7 ? Theme.copper : Theme.teal
        let label = d < 0 ? "overdue" : d == 0 ? "today" : d == 1 ? "tomorrow" : "\(d)d"
        return Text(label)
            .font(.caption.weight(.semibold))
            .foregroundStyle(color)
            .padding(.horizontal, 9).padding(.vertical, 4)
            .background(color.opacity(0.12), in: Capsule())
    }

    // ── This week ──────────────────────────────────────────────────────────
    private var weekly: [(day: String, sessions: [(course: StudyCourse, slot: StudySlot)])] {
        let order = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        var out: [(String, [(StudyCourse, StudySlot)])] = []
        for day in order {
            let s = courses.flatMap { c in c.schedule.filter { $0.day == day }.map { (c, $0) } }
                .sorted { $0.1.time < $1.1.time }
            if !s.isEmpty { out.append((day, s)) }
        }
        return out
    }

    private var thisWeekSection: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("This week").font(.headline).foregroundStyle(Theme.ink)
            if weekly.isEmpty {
                Text("No scheduled sessions.").font(.subheadline).foregroundStyle(.secondary)
            }
            ForEach(weekly, id: \.day) { group in
                HStack(alignment: .top, spacing: 12) {
                    Text(group.day)
                        .font(.caption.weight(.bold))
                        .foregroundStyle(Theme.copper)
                        .frame(width: 34, alignment: .leading)
                        .padding(.top, 3)
                    VStack(spacing: 8) {
                        ForEach(group.sessions, id: \.course.id) { s in
                            HStack(spacing: 12) {
                                VStack(alignment: .leading, spacing: 1) {
                                    Text(s.course.name).font(.subheadline.weight(.medium))
                                        .foregroundStyle(Theme.ink).lineLimit(1)
                                    Text("\(s.slot.type) · room \(s.slot.room)").font(.caption)
                                        .foregroundStyle(.secondary).lineLimit(1)
                                }
                                Spacer()
                                Text(s.slot.time)
                                    .font(.caption.weight(.semibold))
                                    .monospacedDigit()
                                    .foregroundStyle(Theme.ink)
                            }
                            .padding(12)
                            .background(Theme.surface, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
                        }
                    }
                }
            }
        }
    }

    // ── Courses ────────────────────────────────────────────────────────────
    private var coursesSection: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Courses").font(.headline).foregroundStyle(Theme.ink)
            ForEach(courses) { course in
                NavigationLink(value: course) {
                    courseCard(course)
                }
                .buttonStyle(.plain)
            }
        }
    }

    private func courseCard(_ course: StudyCourse) -> some View {
        HStack(spacing: 14) {
            Image(systemName: courseIcon(course.id))
                .font(.system(size: 20, weight: .semibold))
                .foregroundStyle(Theme.teal)
                .frame(width: 44, height: 44)
                .background(Theme.teal.opacity(0.10), in: RoundedRectangle(cornerRadius: 13, style: .continuous))
            VStack(alignment: .leading, spacing: 3) {
                Text(course.name)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(Theme.ink)
                    .lineLimit(1)
                Text("\(course.code) · \(course.english)")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }
            Spacer()
            Image(systemName: "chevron.right")
                .font(.caption.weight(.semibold))
                .foregroundStyle(.tertiary)
        }
        .padding(14)
        .background(Theme.surface, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 16, style: .continuous)
                .strokeBorder(Theme.ink.opacity(0.05), lineWidth: 0.5)
        )
    }

    private var noDeadlines: some View {
        HStack(spacing: 12) {
            Image(systemName: "checkmark.seal.fill")
                .font(.title2).foregroundStyle(Theme.success)
            Text("All caught up — no pending deadlines.")
                .font(.subheadline).foregroundStyle(.secondary)
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Theme.surface, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
    }

    // ── Helpers ────────────────────────────────────────────────────────────
    private func prettyDate(_ iso: String) -> String {
        guard let d = studyDate(iso) else { return iso }
        let f = DateFormatter(); f.dateFormat = "EEE dd.MM"
        return f.string(from: d)
    }

    private func courseIcon(_ id: String) -> String {
        switch id {
        case "ml": return "brain.head.profile"
        case "atm": return "function"
        case "dataviz": return "chart.xyaxis.line"
        case "ba": return "briefcase.fill"
        case "crm": return "person.2.fill"
        default: return "book.closed.fill"
        }
    }
}

// ── Course detail ──────────────────────────────────────────────────────────
struct CourseDetailView: View {
    let course: StudyCourse

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 22) {
                VStack(alignment: .leading, spacing: 4) {
                    Text(course.name)
                        .font(.display(28))
                        .foregroundStyle(Theme.ink)
                    Text("\(course.code) · \(course.english)")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                    Text(course.source)
                        .font(.caption)
                        .foregroundStyle(Theme.copper)
                }
                .entrance(0)

                if !course.grading.isEmpty { gradingSection.entrance(1) }
                if !course.schedule.isEmpty { scheduleSection.entrance(2) }
                if !course.deadlines.isEmpty { deadlinesSection.entrance(3) }
                if !course.exams.isEmpty { examsSection.entrance(4) }
            }
            .padding(16)
            .padding(.bottom, 24)
        }
        .matteBackground()
        .navigationTitle(course.code)
        .navigationBarTitleDisplayMode(.inline)
    }

    private var gradingSection: some View {
        section("Grading", symbol: "list.number", tint: Theme.teal) {
            VStack(spacing: 0) {
                ForEach(Array(course.grading.enumerated()), id: \.offset) { i, g in
                    HStack {
                        Text(g.label)
                            .font(.subheadline)
                            .foregroundStyle(Theme.ink)
                        Spacer()
                        Text(g.value)
                            .font(.subheadline.weight(.semibold))
                            .monospacedDigit()
                            .foregroundStyle(Theme.teal)
                    }
                    .padding(.vertical, 9)
                    if i < course.grading.count - 1 { Divider().opacity(0.5) }
                }
            }
        }
    }

    private var scheduleSection: some View {
        section("Schedule", symbol: "calendar", tint: Theme.copper) {
            ForEach(course.schedule, id: \.self) { slot in
                HStack(spacing: 12) {
                    Text(slot.day)
                        .font(.caption.weight(.bold))
                        .foregroundStyle(Theme.copper)
                        .frame(width: 40, alignment: .leading)
                    VStack(alignment: .leading, spacing: 1) {
                        Text(slot.type).font(.subheadline.weight(.medium)).foregroundStyle(Theme.ink)
                        Text("room \(slot.room)").font(.caption).foregroundStyle(.secondary)
                    }
                    Spacer()
                    Text(slot.time)
                        .font(.caption.weight(.semibold)).monospacedDigit().foregroundStyle(Theme.ink)
                }
                .padding(.vertical, 6)
            }
        }
    }

    private var deadlinesSection: some View {
        section("Deadlines", symbol: "flag.fill", tint: Theme.danger) {
            ForEach(course.deadlines, id: \.self) { dl in
                HStack(spacing: 12) {
                    VStack(alignment: .leading, spacing: 1) {
                        Text(dl.what)
                            .font(.subheadline.weight(.medium))
                            .foregroundStyle(Theme.ink)
                            .lineLimit(2)
                        Text("\(pretty(dl.date)) · \(dl.time)")
                            .font(.caption).foregroundStyle(.secondary)
                    }
                    Spacer()
                    if let d = daysLeft(dl.date) {
                        badge(d)
                    }
                }
                .padding(.vertical, 7)
            }
        }
    }

    private var examsSection: some View {
        section("Exams & tests", symbol: "pencil.and.list.clipboard", tint: Theme.warning) {
            ForEach(course.exams, id: \.self) { ex in
                HStack(spacing: 12) {
                    VStack(alignment: .leading, spacing: 1) {
                        Text(ex.what).font(.subheadline.weight(.medium)).foregroundStyle(Theme.ink)
                        Text("\(pretty(ex.date)) · \(ex.time)\(ex.room.isEmpty ? "" : " · \(ex.room)")")
                            .font(.caption).foregroundStyle(.secondary)
                    }
                    Spacer()
                }
                .padding(.vertical, 7)
            }
        }
    }

    @ViewBuilder
    private func section(_ title: String, symbol: String, tint: Color,
                         @ViewBuilder content: () -> some View) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 8) {
                Image(systemName: symbol).font(.subheadline.weight(.semibold)).foregroundStyle(tint)
                Text(title).font(.headline).foregroundStyle(Theme.ink)
            }
            VStack(alignment: .leading, spacing: 0) { content() }
                .padding(14)
                .background(Theme.surface, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
                .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous)
                    .strokeBorder(Theme.ink.opacity(0.05), lineWidth: 0.5))
        }
    }

    private func badge(_ d: Int) -> some View {
        let color: Color = d < 0 ? Theme.danger : d == 0 ? Theme.danger : d <= 2 ? Theme.warning : d <= 7 ? Theme.copper : Theme.teal
        let label = d < 0 ? "overdue" : d == 0 ? "today" : d == 1 ? "tomorrow" : "\(d)d"
        return Text(label)
            .font(.caption.weight(.semibold))
            .foregroundStyle(color)
            .padding(.horizontal, 9).padding(.vertical, 4)
            .background(color.opacity(0.12), in: Capsule())
    }

    private func pretty(_ iso: String) -> String {
        guard let d = studyDate(iso) else { return iso }
        let f = DateFormatter(); f.dateFormat = "EEE dd.MM"
        return f.string(from: d)
    }
}
