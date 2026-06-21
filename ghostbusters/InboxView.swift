import SwiftUI

struct InboxView: View {
    @Environment(PrioritiesStore.self) private var prioritiesStore
    @State private var chats: [ChatSummary] = []
    @State private var isLoading = true
    @State private var errorMessage: String?
    @State private var searchText = ""
    @State private var path = NavigationPath()

    private var filteredChats: [ChatSummary] {
        let query = searchText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !query.isEmpty else { return chats }
        return chats.filter {
            $0.display_name.localizedCaseInsensitiveContains(query)
                || $0.last_message.localizedCaseInsensitiveContains(query)
        }
    }

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
                            .listRowBackground(
                                GhostbustersGroupedBackground(
                                    corners: ghostbustersSectionCorners(row: 0, total: ghostbustersSectionRowCount)
                                )
                            )

                            if prioritiesStore.isRefreshing, prioritiesStore.priorities.isEmpty {
                                HStack(spacing: 10) {
                                    ProgressView()
                                        .controlSize(.small)
                                    Text("Finding who needs a reply…")
                                        .font(.subheadline)
                                        .foregroundStyle(.secondary)
                                }
                                .frame(maxWidth: .infinity, alignment: .leading)
                                .padding(.vertical, 8)
                                .listRowBackground(
                                    GhostbustersGroupedBackground(
                                        corners: ghostbustersSectionCorners(row: 1, total: ghostbustersSectionRowCount)
                                    )
                                )
                            } else if prioritiesStore.priorities.isEmpty {
                                Text("You're all caught up.")
                                    .font(.subheadline)
                                    .foregroundStyle(.secondary)
                                    .frame(maxWidth: .infinity, alignment: .leading)
                                    .padding(.vertical, 8)
                                    .listRowBackground(
                                        GhostbustersGroupedBackground(
                                            corners: ghostbustersSectionCorners(row: 1, total: ghostbustersSectionRowCount)
                                        )
                                    )
                            } else {
                                ForEach(Array(prioritiesStore.priorities.enumerated()), id: \.element.id) { index, priority in
                                    NavigationLink(
                                        value: InboxDestination.chat(
                                            chat: chat(for: priority),
                                            prefilledDraft: priority.suggested_response
                                        )
                                    ) {
                                        RespondToNameRow(priority: priority)
                                    }
                                    .listRowBackground(
                                        GhostbustersGroupedBackground(
                                            corners: ghostbustersSectionCorners(
                                                row: index + 1,
                                                total: ghostbustersSectionRowCount
                                            )
                                        )
                                    )
                                }
                            }
                        }
                        .listRowInsets(EdgeInsets(top: 0, leading: 12, bottom: 0, trailing: 12))
                        .listRowSeparator(.hidden)

                        Section {
                            if searchText.isEmpty {
                                Text("Messages")
                                    .font(.subheadline.weight(.semibold))
                                    .foregroundStyle(.secondary)
                                    .frame(maxWidth: .infinity, alignment: .leading)
                                    .padding(.top, 2)
                                    .padding(.bottom, 4)
                                    .listRowInsets(EdgeInsets(top: 0, leading: 16, bottom: 0, trailing: 16))
                                    .listRowSeparator(.hidden)
                                    .listRowBackground(Color(.systemBackground))
                            }

                            ForEach(filteredChats) { chat in
                                NavigationLink(value: InboxDestination.chat(chat: chat, prefilledDraft: "")) {
                                    ChatRow(chat: chat)
                                }
                                .listRowBackground(Color(.systemBackground))
                            }
                        }
                    }
                    .listStyle(.plain)
                    .listSectionSpacing(0)
                    .scrollContentBackground(.hidden)
                    .background(Color(.systemBackground))
                    .safeAreaInset(edge: .bottom, spacing: 0) {
                        FloatingInboxSearchBar(
                            searchText: $searchText,
                            onCompose: { path.append(InboxDestination.ghostbusters) }
                        )
                    }
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
            .refreshable {
                await load()
                await prioritiesStore.refresh(showLoading: false)
            }
        }
        .background(Color(.systemBackground))
        .task { await load() }
        .onReceive(NotificationCenter.default.publisher(for: .inboxShouldRefresh)) { _ in
            Task {
                await load()
                await prioritiesStore.refresh(showLoading: false)
            }
        }
        .onAppear {
            prioritiesStore.prefetchIfNeeded()
        }
    }

    private func load() async {
        isLoading = chats.isEmpty
        errorMessage = nil
        prioritiesStore.prefetchIfNeeded()

        do {
            async let chatData = ConnectorClient.fetchChats(limit: 30)
            async let priorityRefresh: Void = prioritiesStore.refresh(showLoading: false)
            chats = try await chatData
            await priorityRefresh
        } catch {
            errorMessage = "Start the connector: cd connector && .venv/bin/python main.py"
        }
        isLoading = false
    }

    private var ghostbustersSectionRowCount: Int {
        if prioritiesStore.isRefreshing, prioritiesStore.priorities.isEmpty {
            return 2
        }
        if prioritiesStore.priorities.isEmpty {
            return 2
        }
        return 1 + prioritiesStore.priorities.count
    }

    private func ghostbustersSectionCorners(row: Int, total: Int) -> GhostbustersGroupedCorners {
        if total <= 1 {
            return .all
        }
        if row == 0 {
            return .top
        }
        if row == total - 1 {
            return .bottom
        }
        return .middle
    }

    private func chat(for priority: PriorityItem) -> ChatSummary {
        if let match = prioritiesStore.chats.first(where: { $0.chat_id == priority.chat_id }) {
            return match
        }
        if let match = chats.first(where: { $0.chat_id == priority.chat_id }) {
            return match
        }
        return ChatSummary(
            chat_id: priority.chat_id,
            chat_guid: priority.chat_guid,
            display_name: priority.contact_name,
            contact_handle: priority.contact_handle,
            last_message: priority.last_message_preview,
            last_message_at: priority.last_message_at,
            is_from_me: false,
            is_group: priority.chat_guid.contains(";+;"),
            needs_reply: true,
            reply_waiting_at: priority.reply_waiting_at,
            unread_count: 1
        )
    }
}

struct UnreadDot: View {
    var body: some View {
        Circle()
            .fill(Color.blue)
            .frame(width: 11, height: 11)
            .accessibilityLabel("Unread")
    }
}

enum GhostbustersGroupedCorners {
    case all
    case top
    case middle
    case bottom
}

struct GhostbustersGroupedBackground: View {
    let corners: GhostbustersGroupedCorners

    var body: some View {
        UnevenRoundedRectangle(
            topLeadingRadius: topRadius,
            bottomLeadingRadius: bottomRadius,
            bottomTrailingRadius: bottomRadius,
            topTrailingRadius: topRadius,
            style: .continuous
        )
        .fill(Color(.secondarySystemGroupedBackground))
        .padding(.top, corners == .top || corners == .all ? 6 : 0)
    }

    private var topRadius: CGFloat {
        corners == .top || corners == .all ? 14 : 0
    }

    private var bottomRadius: CGFloat {
        corners == .bottom || corners == .all ? 14 : 0
    }
}

struct FloatingInboxSearchBar: View {
    @Binding var searchText: String
    let onCompose: () -> Void

    var body: some View {
        HStack(spacing: 10) {
            HStack(spacing: 8) {
                Image(systemName: "magnifyingglass")
                    .foregroundStyle(.secondary)
                TextField("Search", text: $searchText)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 10)
            .frame(maxWidth: .infinity)
            .background(.regularMaterial, in: Capsule())
            .shadow(color: .black.opacity(0.12), radius: 10, y: 4)

            Button(action: onCompose) {
                Image(systemName: "square.and.pencil")
                    .font(.body.weight(.semibold))
                    .foregroundStyle(.primary)
                    .frame(width: 44, height: 44)
                    .background(.regularMaterial, in: Circle())
                    .shadow(color: .black.opacity(0.12), radius: 10, y: 4)
            }
            .buttonStyle(.plain)
            .accessibilityLabel("Compose")
        }
        .padding(.horizontal, 16)
        .padding(.top, 10)
        .padding(.bottom, 8)
        .background {
            LinearGradient(
                colors: [Color(.systemBackground).opacity(0), Color(.systemBackground)],
                startPoint: .top,
                endPoint: .bottom
            )
            .ignoresSafeArea(edges: .bottom)
        }
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
                    .lineLimit(2)
                    .fixedSize(horizontal: false, vertical: true)
            }

            Spacer(minLength: 8)

            Text("Now")
                .font(.subheadline)
                .foregroundStyle(.secondary)
        }
        .padding(.vertical, 4)
    }
}

struct RespondToNameRow: View {
    let priority: PriorityItem

    var body: some View {
        HStack(spacing: 10) {
            Image(systemName: "sparkles")
                .font(.caption)
                .foregroundStyle(.blue)
                .frame(width: 18)

            Text(priority.contact_name)
                .font(.body)
                .foregroundStyle(.primary)

            Spacer(minLength: 8)

            Text("waiting \(priority.replyWaitLabel)")
                .font(.subheadline)
                .foregroundStyle(.orange)
        }
        .padding(.vertical, 4)
    }
}

struct ChatRow: View {
    let chat: ChatSummary

    var body: some View {
        HStack(spacing: 8) {
            Group {
                if chat.hasUnread {
                    UnreadDot()
                } else {
                    Color.clear
                        .frame(width: 11, height: 11)
                }
            }
            .frame(width: 11, height: 11)

            AvatarView(label: Formatters.initials(chat.display_name))

            VStack(alignment: .leading, spacing: 3) {
                HStack {
                    Text(chat.display_name)
                        .font(.body.weight(chat.hasUnread ? .semibold : .regular))
                        .lineLimit(1)
                    Spacer()
                    Text(chat.inboxTimestamp)
                        .font(.subheadline)
                        .foregroundStyle(chat.hasUnread ? .primary : .secondary)
                }

                Text(previewText)
                    .font(.subheadline)
                    .foregroundStyle(chat.hasUnread ? .primary : .secondary)
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
