import SwiftUI

@main
struct GhostbustersApp: App {
    @State private var prioritiesStore = PrioritiesStore.shared

    var body: some Scene {
        WindowGroup {
            InboxView()
                .environment(prioritiesStore)
                .task {
                    prioritiesStore.prefetchIfNeeded()
                }
        }
    }
}
