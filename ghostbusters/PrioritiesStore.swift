import Foundation
import Observation

@MainActor
@Observable
final class PrioritiesStore {
    static let shared = PrioritiesStore()

    var priorities: [PriorityItem] = []
    var chats: [ChatSummary] = []
    var isRefreshing = false
    var lastError: String?

    private var lastFetched: Date?
    private var prefetchTask: Task<Void, Never>?
    private let cacheTTL: TimeInterval = 300

    func prefetchIfNeeded() {
        guard prefetchTask == nil else { return }
        if let lastFetched, Date().timeIntervalSince(lastFetched) < cacheTTL, !priorities.isEmpty {
            return
        }

        prefetchTask = Task {
            await refresh(showLoading: false)
            Task { try? await ConnectorClient.triggerPrefetch(limit: 3) }
            prefetchTask = nil
        }
    }

    func refresh(showLoading: Bool = true) async {
        if showLoading {
            isRefreshing = true
        }
        lastError = nil
        defer { isRefreshing = false }

        do {
            async let chatData = ConnectorClient.fetchChats(limit: 30)
            async let priorityData = ConnectorClient.fetchPriorities(limit: 3)
            chats = try await chatData
            priorities = try await priorityData
            lastFetched = Date()
        } catch {
            if priorities.isEmpty {
                lastError = "Could not reach connector at 127.0.0.1:8787"
            }
        }
    }
}
