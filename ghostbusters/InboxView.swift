import SwiftUI

struct InboxView: View {
    @Environment(PrioritiesStore.self) private var prioritiesStore
    @State private var chats: [ChatSummary] = []
    @State private var isLoading = true
    @State private var errorMessage: String?
    @State private var path = NavigationPath()

    var body: some View {
        NavigationStack(path: $path) {
            Group {
                if isLoading {
                    ProgressView("Loading messages…")
                } else if let errorMessage {
                    ContentUnavailableView {
                        Label("Connector offline", systemImage: "wifi.exclamationmark")
                    } description: {
                        Text(errorMessage)
                    } actions: {
                        Button("Retry") { Task { await load() } }
                    }
                } else {
                    List {
                        NavigationLink(value: InboxDestination.ghostbusters) {
                            PinnedGhostbustersRow()
                        }
                        .listRowBackground(Color(.systemBackground))

                        ForEach(chats) { chat in
                            NavigationLink(value: InboxDestination.chat(chat: chat, prefilledDraft: "")) {
                                ChatRow(chat: chat)
                            }
                            .listRowBackground(Color(.systemBackground))
                        }
                    }
                    .listStyle(.plain)
                    .scrollContentBackground(.hidden)
                    .background(Color(.systemBackground))
                }
            }
            .navigationTitle("Messages")
            .navigationBarTitleDisplayMode(.inline)
            .toolbarBackground(.visible, for: .navigationBar)
            .toolbarBackground(Color(.systemBackground), for: .navigationBar)
            .navigationDestination(for: InboxDestination.self) { dest in
                switch dest {
                case .ghostbusters:
                    GhostbustersChatView(onOpenChat: { chat, draft in
                        path.append(InboxDestination.chat(chat: chat, prefilledDraft: draft))
                    })
                case .chat(let chat, let prefilledDraft):
                    ChatThreadView(chat: chat, initialDraft: prefilledDraft)
                }
            }
            .refreshable { await load() }
        }
        .background(Color(.systemBackground))
        .task { await load() }
        .onAppear {
            prioritiesStore.prefetchIfNeeded()
        }
    }

    private func load() async {
        isLoading = chats.isEmpty
        errorMessage = nil
        prioritiesStore.prefetchIfNeeded()
        do {
            chats = try await ConnectorClient.fetchChats(limit: 30)
        } catch {
            errorMessage = "Start the connector: cd connector && .venv/bin/python main.py"
        }
        isLoading = false
    }
}

struct PinnedGhostbustersRow: View {
    var body: some View {
        HStack(spacing: 12) {
            ZStack {
                Circle()
                    .fill(
                        LinearGradient(
                            colors: [Color.blue, Color.purple.opacity(0.8)],
                            startPoint: .topLeading,
                            endPoint: .bottomTrailing
                        )
                    )
                    .frame(width: 48, height: 48)
                Text("👻")
                    .font(.title3)
            }

            VStack(alignment: .leading, spacing: 3) {
                HStack {
                    Text("Ghostbusters")
                        .font(.body.weight(.semibold))
                    Image(systemName: "pin.fill")
                        .font(.caption2)
                        .foregroundStyle(.orange)
                }
                Text("Top 3 conversations you should respond to")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }

            Spacer()

            Text("Now")
                .font(.subheadline)
                .foregroundStyle(.secondary)
        }
        .padding(.vertical, 2)
    }
}

struct ChatRow: View {
    let chat: ChatSummary

    var body: some View {
        HStack(spacing: 12) {
            AvatarView(label: Formatters.initials(chat.display_name))

            VStack(alignment: .leading, spacing: 3) {
                HStack {
                    Text(chat.display_name)
                        .font(.body.weight(chat.needs_reply ? .semibold : .regular))
                        .lineLimit(1)
                    Spacer()
                    Text(chat.inboxTimestamp)
                        .font(.subheadline)
                        .foregroundStyle(chat.needs_reply ? .primary : .secondary)
                }

                Text(previewText)
                    .font(.subheadline)
                    .foregroundStyle(chat.needs_reply ? .primary : .secondary)
                    .lineLimit(1)
            }
        }
        .padding(.vertical, 2)
    }

    private var previewText: String {
        if chat.is_from_me {
            return "You: \(chat.last_message)"
        }
        return chat.last_message
    }
}

struct AvatarView: View {
    let label: String

    var body: some View {
        Circle()
            .fill(Color(.systemGray4))
            .frame(width: 48, height: 48)
            .overlay {
                Text(label)
                    .font(.body.weight(.semibold))
                    .foregroundStyle(.white)
            }
    }
}

#Preview {
    InboxView()
}
