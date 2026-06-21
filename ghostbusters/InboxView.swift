import SwiftUI

struct InboxView: View {
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
                        Section {
                            NavigationLink(value: InboxDestination.ghostbusters) {
                                PinnedGhostbustersRow()
                            }
                        } header: {
                            Label("Pinned", systemImage: "pin.fill")
                        }

                        Section("Messages") {
                            ForEach(chats) { chat in
                                NavigationLink(value: InboxDestination.chat(chat)) {
                                    ChatRow(chat: chat)
                                }
                            }
                        }
                    }
                    .listStyle(.plain)
                }
            }
            .navigationTitle("Messages")
            .navigationDestination(for: InboxDestination.self) { dest in
                switch dest {
                case .ghostbusters:
                    GhostbustersChatView(onOpenChat: { chat in
                        path.append(InboxDestination.chat(chat))
                    })
                case .chat(let chat):
                    ChatThreadView(chat: chat)
                }
            }
            .refreshable { await load() }
        }
        .task { await load() }
    }

    private func load() async {
        isLoading = chats.isEmpty
        errorMessage = nil
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
                        .font(.body.weight(chat.is_from_me ? .regular : .semibold))
                        .lineLimit(1)
                    Spacer()
                    Text(Formatters.time(chat.last_message_at))
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                }

                Text(chat.is_from_me ? "You: \(chat.last_message)" : chat.last_message)
                    .font(.subheadline)
                    .foregroundStyle(chat.is_from_me ? .secondary : .primary)
                    .lineLimit(1)
            }
        }
        .padding(.vertical, 2)
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
