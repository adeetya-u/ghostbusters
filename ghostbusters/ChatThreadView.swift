import SwiftUI

struct ChatThreadView: View {
    @Environment(PrioritiesStore.self) private var prioritiesStore
    @FocusState private var composerFocused: Bool

    let chat: ChatSummary
    let initialDraft: String

    @State private var messages: [MessageItem] = []
    @State private var suggestions: [String] = []
    @State private var contextSnippets: [String] = []
    @State private var needsReply = true
    @State private var suggestionStatus: String?
    @State private var draftText: String
    @State private var isLoadingMessages = false
    @State private var isLoadingSuggestions = false
    @State private var isLoadingHydraContext = false
    @State private var isSending = false
    @State private var sendError: String?

    init(chat: ChatSummary, initialDraft: String = "") {
        self.chat = chat
        self.initialDraft = initialDraft
        _draftText = State(initialValue: initialDraft)
        if Self.isUsableSuggestion(initialDraft) {
            _suggestions = State(initialValue: [initialDraft])
        }
        _needsReply = State(initialValue: chat.needs_reply)
    }

    private static func isUsableSuggestion(_ text: String) -> Bool {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return false }
        return trimmed != "Generating reply…"
    }

    private var threadRows: [ThreadRow] {
        ThreadRow.build(from: messages)
    }

    var body: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(spacing: 10) {
                    if isLoadingMessages, messages.isEmpty {
                        ProgressView("Loading messages…")
                            .frame(maxWidth: .infinity)
                            .padding(.top, 40)
                    }

                    ForEach(threadRows) { row in
                        switch row {
                        case .daySeparator(let label):
                            Text(label)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                                .frame(maxWidth: .infinity)
                                .padding(.vertical, 6)
                                .id(row.id)
                        case .message(let message, let isLastOutgoing):
                            MessageBubble(
                                message: message,
                                isGroup: chat.is_group,
                                isLastOutgoing: isLastOutgoing
                            )
                            .id(row.id)
                        }
                    }
                }
                .frame(maxWidth: .infinity)
                .padding(.horizontal, 16)
                .padding(.vertical, 8)
            }
            .onChange(of: messages.count) { _, _ in
                if let last = messages.last {
                    withAnimation {
                        proxy.scrollTo("msg-\(last.row_id)", anchor: .bottom)
                    }
                }
            }
        }
        .safeAreaInset(edge: .bottom, spacing: 0) {
            composerArea
        }
        .navigationTitle(chat.display_name)
        .navigationBarTitleDisplayMode(.inline)
        .task(id: chat.chat_id) {
            await loadMessages()
            await loadSuggestions()
        }
    }

    private var composerArea: some View {
        VStack(spacing: 0) {
            ReplySuggestionsBar(
                suggestions: suggestions,
                contextSnippets: contextSnippets,
                isLoading: isLoadingSuggestions,
                isLoadingHydraContext: isLoadingHydraContext,
                needsReply: needsReply,
                statusMessage: suggestionStatus,
                selectedText: draftText,
                onSelect: { draftText = $0 },
                onRequestHydraContext: {
                    Task { await loadHydraContextIfNeeded() }
                }
            )

            if let sendError {
                Text(sendError)
                    .font(.caption)
                    .foregroundStyle(.orange)
                    .padding(.horizontal, 12)
            }

            HStack(alignment: .center, spacing: 8) {
                Image(systemName: "plus.circle.fill")
                    .font(.title2)
                    .foregroundStyle(.gray)
                    .fixedSize()

                TextField("iMessage", text: $draftText, axis: .vertical)
                    .font(.body)
                    .lineLimit(1...4)
                    .fixedSize(horizontal: false, vertical: true)
                    .submitLabel(.send)
                    .focused($composerFocused)
                    .onSubmit { Task { await sendDraft() } }
                    .padding(.horizontal, 12)
                    .padding(.vertical, 7)
                    .background(Color(.systemGray6), in: RoundedRectangle(cornerRadius: 20, style: .continuous))
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .layoutPriority(0)

                Button(action: { Task { await sendDraft() } }) {
                    Image(systemName: isSending ? "hourglass" : "arrow.up")
                        .font(.system(size: 16, weight: .bold))
                        .foregroundStyle(.white)
                        .frame(width: 32, height: 32)
                        .background(canSend ? Color.blue : Color(.systemGray3))
                        .clipShape(Circle())
                }
                .buttonStyle(.plain)
                .fixedSize()
                .layoutPriority(1)
                .disabled(!canSend || isSending)
                .accessibilityLabel("Send")
            }
            .padding(.horizontal, 10)
            .padding(.top, 6)
            .padding(.bottom, 4)
        }
        .background {
            Rectangle()
                .fill(.bar)
                .ignoresSafeArea(edges: .bottom)
        }
    }

    private var canSend: Bool {
        !draftText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    private func loadMessages() async {
        isLoadingMessages = messages.isEmpty
        sendError = nil

        do {
            messages = try await ConnectorClient.fetchMessages(chatId: chat.chat_id)
            if !needsReply {
                needsReply = messages.last.map { !$0.is_from_me } ?? chat.needs_reply
            }
        } catch {
            if messages.isEmpty {
                sendError = "Could not load messages. Is the connector running?"
            }
        }

        isLoadingMessages = false
    }

    private func loadSuggestions() async {
        isLoadingSuggestions = true
        suggestionStatus = nil

        do {
            let payload = try await ConnectorClient.fetchReplySuggestions(
                chatId: chat.chat_id,
                limit: 3,
                followUp: false
            )
            suggestions = payload.suggestions
            contextSnippets = payload.context_snippets ?? []
            needsReply = payload.needs_reply ?? !(messages.last?.is_from_me ?? false)
            if payload.reason == "caught_up" || !needsReply {
                suggestionStatus = "You replied last. Ghostbusters only suggests when someone is waiting on you."
            } else if suggestions.isEmpty {
                suggestionStatus = "Generating suggestions from HydraDB…"
            }

            if needsReply, payload.reason != "caught_up" {
                Task { await appendFollowUpContextInBackground() }
            }
        } catch {
            suggestions = []
            contextSnippets = []
            let waiting = messages.last.map { !$0.is_from_me } ?? needsReply
            needsReply = waiting
            suggestionStatus = waiting
                ? "Suggestions still loading or unavailable."
                : "You replied last, no suggestions needed."
        }

        isLoadingSuggestions = false
    }

    private func loadHydraContextIfNeeded() async {
        guard contextSnippets.isEmpty, !isLoadingHydraContext else { return }

        isLoadingHydraContext = true
        defer { isLoadingHydraContext = false }

        do {
            let payload = try await ConnectorClient.fetchHydraContext(chatId: chat.chat_id)
            mergeContextSnippets(payload.context_snippets)
        } catch {
            // Context panel shows a fallback message when snippets stay empty.
        }
    }

    /// Nebius + last 4 messages; merged into Hydra context without blocking the UI.
    private func appendFollowUpContextInBackground() async {
        guard needsReply else { return }

        do {
            let payload = try await ConnectorClient.fetchReplySuggestions(
                chatId: chat.chat_id,
                limit: 3,
                followUp: true
            )
            mergeContextSnippets(payload.context_snippets ?? [])
        } catch {
            // Hydra suggestions already shown; follow-up context is best-effort.
        }
    }

    private func mergeContextSnippets(_ additional: [String]) {
        guard !additional.isEmpty else { return }
        var merged = contextSnippets
        for snippet in additional {
            let trimmed = snippet.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !trimmed.isEmpty, !merged.contains(trimmed) else { continue }
            merged.append(trimmed)
        }
        contextSnippets = merged
    }

    private func sendDraft() async {
        let text = draftText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty, !isSending else { return }

        isSending = true
        sendError = nil
        defer { isSending = false }

        do {
            let sent = try await ConnectorClient.sendMessage(chatId: chat.chat_id, text: text)
            draftText = ""
            suggestions = []
            contextSnippets = []

            if !messages.contains(where: { $0.row_id == sent.row_id }) {
                messages.append(sent)
            }
            needsReply = false

            do {
                messages = try await ConnectorClient.fetchMessages(chatId: chat.chat_id)
                needsReply = messages.last.map { !$0.is_from_me } ?? false
            } catch {
                sendError = "Sent, but could not refresh thread."
            }

            if needsReply {
                await loadSuggestions()
            } else {
                suggestionStatus = "Sent to demo inbox. You replied last."
            }

            await prioritiesStore.refresh(showLoading: false)
            NotificationCenter.default.post(name: .inboxShouldRefresh, object: nil)
            try? await ConnectorClient.triggerPrefetch(limit: 3)
        } catch let error as ConnectorAPIError {
            sendError = error.detail
        } catch {
            sendError = "Could not send message. Is the connector running?"
        }
    }
}

private enum ThreadRow: Identifiable {
    case daySeparator(String)
    case message(MessageItem, isLastOutgoing: Bool)

    var id: String {
        switch self {
        case .daySeparator(let label):
            return "sep-\(label)"
        case .message(let message, _):
            return "msg-\(message.row_id)"
        }
    }

    static func build(from messages: [MessageItem]) -> [ThreadRow] {
        var rows: [ThreadRow] = []
        var previousDayKey: String?

        for (index, message) in messages.enumerated() {
            let dayKey = Formatters.dayKey(message.timestamp)
            if dayKey != previousDayKey {
                rows.append(.daySeparator(Formatters.daySeparator(message.timestamp)))
                previousDayKey = dayKey
            }
            let isLastOutgoing = message.is_from_me && !messages[(index + 1)...].contains { $0.is_from_me }
            rows.append(.message(message, isLastOutgoing: isLastOutgoing))
        }
        return rows
    }
}

struct ReplySuggestionsBar: View {
    let suggestions: [String]
    let contextSnippets: [String]
    let isLoading: Bool
    let isLoadingHydraContext: Bool
    let needsReply: Bool
    let statusMessage: String?
    let selectedText: String
    let onSelect: (String) -> Void
    let onRequestHydraContext: () -> Void

    @State private var showHydraContext = false

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 8) {
                Button {
                    withAnimation(.easeInOut(duration: 0.2)) {
                        showHydraContext.toggle()
                        if showHydraContext {
                            onRequestHydraContext()
                        }
                    }
                } label: {
                    Label("Ghostbusters", systemImage: showHydraContext ? "sparkles" : "sparkle")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(showHydraContext ? .blue : .secondary)
                }
                .buttonStyle(.plain)
                .accessibilityLabel(showHydraContext ? "Hide Hydra context" : "Show Hydra context")

                if (isLoading && suggestions.isEmpty) || isLoadingHydraContext {
                    ProgressView()
                        .controlSize(.small)
                }

                Spacer()

                if showHydraContext {
                    Text("This thread only")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
            }
            .padding(.horizontal, 12)

            if showHydraContext {
                VStack(alignment: .leading, spacing: 6) {
                    if contextSnippets.isEmpty {
                        Text(
                            isLoadingHydraContext
                                ? "Loading Hydra context…"
                                : "No Hydra context for this thread yet."
                        )
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                        .frame(maxWidth: .infinity, alignment: .leading)
                    } else {
                        ForEach(Array(contextSnippets.prefix(6).enumerated()), id: \.offset) { _, snippet in
                            Text(snippet)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                                .fixedSize(horizontal: false, vertical: true)
                                .frame(maxWidth: .infinity, alignment: .leading)
                        }
                    }
                }
                .padding(.horizontal, 12)
                .padding(.vertical, 8)
                .background(Color(.systemGray6))
                .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
                .padding(.horizontal, 12)
            }

            if isLoading, suggestions.isEmpty, !showHydraContext {
                Text(statusMessage ?? "Generating suggestions…")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.horizontal, 12)
                    .padding(.bottom, 4)
            } else if suggestions.isEmpty, !showHydraContext {
                Text(statusMessage ?? "No reply suggestions for this thread.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.horizontal, 12)
                    .padding(.bottom, 4)
            } else {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(alignment: .center, spacing: 8) {
                        ForEach(Array(suggestions.enumerated()), id: \.offset) { _, text in
                            ReplySuggestionChip(
                                text: text,
                                isSelected: selectedText == text,
                                onSelect: { onSelect(text) }
                            )
                        }
                    }
                    .padding(.horizontal, 12)
                    .padding(.bottom, 4)
                }
            }
        }
        .padding(.top, 8)
        .padding(.bottom, 4)
        .background(.bar)
        .overlay(alignment: .top) {
            Divider()
        }
    }
}

struct ReplySuggestionChip: View {
    let text: String
    let isSelected: Bool
    let onSelect: () -> Void

    var body: some View {
        Button(action: onSelect) {
            Text(text)
                .font(.subheadline)
                .foregroundStyle(.primary)
                .multilineTextAlignment(.leading)
                .frame(maxWidth: 240, alignment: .leading)
                .padding(.horizontal, 14)
                .padding(.vertical, 10)
                .background {
                    RoundedRectangle(cornerRadius: 18, style: .continuous)
                        .fill(isSelected ? Color.blue.opacity(0.18) : Color.blue.opacity(0.1))
                }
                .overlay {
                    RoundedRectangle(cornerRadius: 18, style: .continuous)
                        .stroke(isSelected ? Color.blue : Color.blue.opacity(0.25), lineWidth: 1.5)
                }
        }
        .buttonStyle(.plain)
    }
}

struct MessageBubble: View {
    let message: MessageItem
    let isGroup: Bool
    var isLastOutgoing: Bool = false

    private let tailInset: CGFloat = 56
    private let bubbleMaxWidth: CGFloat = 260

    var body: some View {
        HStack(alignment: .bottom, spacing: 0) {
            if message.is_from_me {
                Spacer(minLength: tailInset)
            }

            VStack(alignment: message.is_from_me ? .trailing : .leading, spacing: 4) {
                if isGroup, !message.is_from_me, let sender = message.contact_name, !sender.isEmpty {
                    Text(sender)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .padding(.horizontal, 4)
                }

                Text(message.text)
                    .font(.body)
                    .multilineTextAlignment(.leading)
                    .fixedSize(horizontal: false, vertical: true)
                    .padding(.horizontal, 12)
                    .padding(.vertical, 8)
                    .background(bubbleColor, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
                    .foregroundStyle(message.is_from_me ? .white : .primary)

                HStack(spacing: 6) {
                    Text(Formatters.messageTime(message.timestamp))
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                    if message.is_from_me, isLastOutgoing {
                        Text("Delivered")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                }
                .padding(.horizontal, 4)
            }
            .frame(
                maxWidth: bubbleMaxWidth,
                alignment: message.is_from_me ? .trailing : .leading
            )

            if !message.is_from_me {
                Spacer(minLength: tailInset)
            }
        }
        .frame(maxWidth: .infinity, alignment: message.is_from_me ? .trailing : .leading)
    }

    private var bubbleColor: Color {
        message.is_from_me ? .blue : Color(.systemGray5)
    }
}
