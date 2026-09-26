import WidgetKit
import SwiftUI

struct WasherLiveActivity: Widget {
    var body: some WidgetConfiguration {
        ActivityConfiguration(for: WasherAttributes.self) { context in
            // Lock screen / banner
            VStack(alignment: .leading, spacing: 8) {
                HStack {
                    Image(systemName: "washer").foregroundStyle(.white)
                    Text("Washer").font(.headline).foregroundStyle(.white)
                    Spacer()
                    Text(context.state.machineState.capitalized)
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(.white.opacity(0.8))
                }
                ProgressView(value: context.state.progress / 100).tint(.white)
                if let m = context.state.remainingMinutes {
                    Text("~\(m) min left").font(.caption).foregroundStyle(.white.opacity(0.8))
                }
            }
            .padding()
            .activityBackgroundTint(Color.black.opacity(0.45))
            .activitySystemActionForegroundColor(.white)
        } dynamicIsland: { context in
            DynamicIsland {
                DynamicIslandExpandedRegion(.leading) {
                    Image(systemName: "washer")
                        .font(.title2)
                        .foregroundStyle(.blue)
                }
                DynamicIslandExpandedRegion(.trailing) {
                    Text("\(Int(context.state.progress))%")
                        .font(.title2.bold())
                }
                DynamicIslandExpandedRegion(.center) {
                    Text(context.state.machineState.capitalized)
                        .font(.caption)
                }
                DynamicIslandExpandedRegion(.bottom) {
                    ProgressView(value: context.state.progress / 100)
                }
            } compactLeading: {
                Image(systemName: "washer")
            } compactTrailing: {
                Text("\(Int(context.state.progress))%")
            } minimal: {
                Image(systemName: "washer")
            }
            .keylineTint(.blue)
        }
    }
}
