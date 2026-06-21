import SwiftUI

struct GhostbustersChatView: View {
    let onOpenChat: (ChatSummary) -> Void

    @State private var priorities: [PriorityItem] = []
    @State private var chats: [ChatSummary] = []
    @State private var isLoading = true
    @State private var errorMessage: String?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                header

                if isLoading {
                    ProgressView()
                        .frame(maxWidth: .infinity)
                        .padding(.top, 40)
                } else if let errorMessage {
                    Text(errorMessage)
                        .foregroundStyle(.orange)
                        .padding()
                } else if priorities.isEmpty {
                    Text("You're all caught up — no urgent replies.")
                        .foregroundStyle(.secondary)
                        .padding()
                } else {
                    ForEach(priorities) { priority in
                        PriorityCard(priority: priority) {
                            if let chat = chats.first(where: { $0.chat_id == priority.chat_id }) {
                                onOpenChat(chat)
                            }
                        }
                    }
                }
            }
            .padding()
        }
        .background(Color(.systemGroupedBackground))
        .navigationTitle("Ghostbusters")
        .navigationBarTitleDisplayMode(.inline)
        .task { await load() }
        .refreshable { await load() }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 8) {
                Text("👻")
                    .font(.largeTitle)
                Text("Your top 3")
                    .font(.title2.bold())
            }
            Text("These are the conversations that need a reply most urgently.")
                .font(.subheadline)
                .foregroundStyle(.secondary)
        }
    }

    private func load() async {
        isLoading = priorities.isEmpty
        errorMessage = nil
        do {
            async let p = ConnectorClient.fetchPriorities(limit: 3)
            async let c = ConnectorClient.fetchChats(limit: 30)
            priorities = try await p
            chats = try await c
        } catch {
            errorMessage = "Could not reach connector at 127.0.0.1:8787"
        }
        isLoading = false
    }
}

struct PriorityCard: View {
    let priority: PriorityItem
    let onOpen: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text("#\(priority.rank)")
                    .font(.caption.weight(.bold))
                    .foregroundStyle(.blue)
                Text(priority.contact_name)
                    .font(.headline)
                Spacer()
                SeverityBadge(severity: priority.severity)
            }

            Text("\"\(priority.last_message_preview)\"")
                .font(.subheadline)
                .foregroundStyle(.secondary)

            VStack(alignment: .leading, spacing: 4) {
                Text("Suggested reply")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.blue)
                Text(priority.suggested_response)
                    .font(.body)
            }
            .padding(12)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Color.blue.opacity(0.08))
            .clipShape(RoundedRectangle(cornerRadius: 12))

            Button("Open conversation", action: onOpen)
                .font(.subheadline.weight(.semibold))
        }
        .padding(16)
        .background(Color(.systemBackground))
        .clipShape(RoundedRectangle(cornerRadius: 16))
        .shadow(color: .black.opacity(0.06), radius: 4, y: 2)
    }
}

struct SeverityBadge: View {
    let severity: String

    var body: some View {
        Text(severity.uppercased())
            .font(.caption2.weight(.bold))
            .padding(.horizontal, 8)
            .padding(.vertical, 3)
            .background(color.opacity(0.15))
            .foregroundStyle(color)
            .clipShape(Capsule())
    }

    private var color: Color {
        switch severity {
        case "high", "critical": return .red
        case "medium": return .orange
        default: return .green
        }
    }
}
