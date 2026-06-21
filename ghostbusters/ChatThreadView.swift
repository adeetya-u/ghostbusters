import SwiftUI

struct ChatThreadView: View {
    @Environment(PrioritiesStore.self) private var prioritiesStore
    @FocusState private var composerFocused: Bool

    let chat: ChatSummary
    let initialDraft: String

    @State private var messages: [MessageItem] = []
    @State private var suggestions: [String] = []
    @State private var needsReply = true
    @State private var suggestionStatus: String?
    @State private var draftText: String
    @State private var isLoadingMessages = true
    @State private var isLoadingSuggestions = true
    @State private var isSending = false
    @State private var sendError: String?

    init(chat: ChatSummary, initialDraft: String = "") {
        self.chat = chat
        self.initialDraft = initialDraft
        _draftText = State(initialValue: initialDraft)
        _needsReply = State(initialValue: chat.needs_reply)
    }

    var body: some View {
        VStack(spacing: 0) {
            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(spacing: 8) {
                        ForEach(messages) { message in
                            MessageBubble(message: message, isGroup: chat.is_group)
                                .id(message.id)
                        }
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.horizontal, 16)
                    .padding(.vertical, 8)
                }
                .onChange(of: messages.count) { _, _ in
                    if let last = messages.last {
                        proxy.scrollTo(last.id, anchor: .bottom)
                    }
                }
            }

            composerArea
        }
        .navigationTitle(chat.display_name)
        .navigationBarTitleDisplayMode(.inline)
        .task { await load() }
    }

    private var composerArea: some View {
        VStack(spacing: 0) {
            ReplySuggestionsBar(
                suggestions: suggestions,
                isLoading: isLoadingSuggestions,
                needsReply: needsReply,
                statusMessage: suggestionStatus,
                selectedText: draftText,
                onSelect: { draftText = $0 }
            )

            if let sendError {
                Text(sendError)
                    .font(.caption)
                    .foregroundStyle(.orange)
                    .padding(.horizontal, 12)
            }

            HStack(alignment: .bottom, spacing: 10) {
                Image(systemName: "plus.circle.fill")
                    .font(.title2)
                    .foregroundStyle(.gray)

                HStack(alignment: .bottom, spacing: 8) {
                    TextField("iMessage", text: $draftText, axis: .vertical)
                        .font(.body)
                        .lineLimit(1...4)
                        .submitLabel(.send)
                        .focused($composerFocused)
                        .onSubmit { Task { await sendDraft() } }

                    Button(action: { Task { await sendDraft() } }) {
                        Image(systemName: isSending ? "hourglass" : "arrow.up.circle.fill")
                            .font(.system(size: 28))
                            .foregroundStyle(canSend ? Color.blue : Color(.systemGray3))
                    }
                    .disabled(!canSend || isSending)
                    .accessibilityLabel("Send")
                }
                .padding(.leading, 12)
                .padding(.trailing, 6)
                .padding(.vertical, 8)
                .background(Color(.systemGray6))
                .clipShape(RoundedRectangle(cornerRadius: 22))
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
            .background(.bar)
        }
    }

    private var canSend: Bool {
        !draftText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    private func load() async {
        isLoadingMessages = messages.isEmpty
        isLoadingSuggestions = suggestions.isEmpty
        sendError = nil
        suggestionStatus = nil

        do {
            async let messageData = ConnectorClient.fetchMessages(chatId: chat.chat_id)
            async let suggestionData = ConnectorClient.fetchReplySuggestions(chatId: chat.chat_id, limit: 3)
            messages = try await messageData
            let payload = try await suggestionData
            suggestions = payload.suggestions
            needsReply = payload.needs_reply ?? !(messages.last?.is_from_me ?? false)
            if payload.reason == "caught_up" || !needsReply {
                suggestionStatus = "You replied last — Ghostbusters only suggests when someone is waiting on you."
            } else if suggestions.isEmpty {
                suggestionStatus = "Generating suggestions… pull down to refresh."
            }
        } catch {
            if messages.isEmpty { messages = [] }
            suggestions = []
            needsReply = !(messages.last?.is_from_me ?? false)
            suggestionStatus = needsReply
                ? "Could not load suggestions. Is the connector running?"
                : "You replied last — no suggestions needed."
        }

        isLoadingMessages = false
        isLoadingSuggestions = false
    }

    private func sendDraft() async {
        let text = draftText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty, !isSending else { return }

        isSending = true
        sendError = nil
        defer { isSending = false }

        do {
            _ = try await ConnectorClient.sendMessage(chatId: chat.chat_id, text: text)
            draftText = ""
            suggestions = []
            messages = try await ConnectorClient.fetchMessages(chatId: chat.chat_id)
            needsReply = messages.last.map { !$0.is_from_me } ?? false

            if needsReply {
                isLoadingSuggestions = true
                do {
                    let payload = try await ConnectorClient.fetchReplySuggestions(
                        chatId: chat.chat_id,
                        limit: 3
                    )
                    suggestions = payload.suggestions
                    needsReply = payload.needs_reply ?? needsReply
                    suggestionStatus = suggestions.isEmpty
                        ? "Generating suggestions… pull down to refresh."
                        : nil
                } catch {
                    suggestions = []
                    suggestionStatus = "Could not refresh suggestions."
                }
                isLoadingSuggestions = false
            } else {
                suggestionStatus = "Sent to demo inbox (not real iMessage). You replied last."
                isLoadingSuggestions = false
            }
            await prioritiesStore.refresh(showLoading: false)
            try? await ConnectorClient.triggerPrefetch(limit: 3)
        } catch {
            sendError = "Could not send message. Is the connector running?"
            isLoadingSuggestions = false
        }
    }
}

struct ReplySuggestionsBar: View {
    let suggestions: [String]
    let isLoading: Bool
    let needsReply: Bool
    let statusMessage: String?
    let selectedText: String
    let onSelect: (String) -> Void

    private let chipWidth: CGFloat = 200
    private let chipHeight: CGFloat = 64

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Label("Ghostbusters", systemImage: "sparkles")
                .font(.caption.weight(.semibold))
                .foregroundStyle(.blue)
                .padding(.horizontal, 12)

            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 8) {
                    if isLoading {
                        ForEach(0..<3, id: \.self) { _ in
                            RoundedRectangle(cornerRadius: 14)
                                .fill(Color(.systemGray5))
                                .frame(width: chipWidth, height: chipHeight)
                        }
                    } else if suggestions.isEmpty {
                        Text(statusMessage ?? "No reply suggestions for this thread.")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .frame(minHeight: chipHeight, alignment: .leading)
                    } else {
                        ForEach(Array(suggestions.enumerated()), id: \.offset) { _, text in
                            ReplySuggestionChip(
                                text: text,
                                width: chipWidth,
                                height: chipHeight,
                                isSelected: selectedText == text,
                                onSelect: { onSelect(text) }
                            )
                        }
                    }
                }
                .padding(.horizontal, 12)
            }
            .frame(height: chipHeight)
        }
        .padding(.vertical, 10)
        .background(Color(.systemBackground))
        .overlay(alignment: .top) {
            Divider()
        }
    }
}

struct ReplySuggestionChip: View {
    let text: String
    let width: CGFloat
    let height: CGFloat
    let isSelected: Bool
    let onSelect: () -> Void

    var body: some View {
        Button(action: onSelect) {
            Text(text)
                .font(.subheadline)
                .foregroundStyle(.primary)
                .multilineTextAlignment(.leading)
                .lineLimit(3)
                .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
                .padding(.horizontal, 12)
                .padding(.vertical, 10)
        }
        .buttonStyle(.plain)
        .frame(width: width, height: height, alignment: .topLeading)
        .background(isSelected ? Color.blue.opacity(0.18) : Color.blue.opacity(0.1))
        .overlay {
            RoundedRectangle(cornerRadius: 14)
                .stroke(isSelected ? Color.blue : Color.clear, lineWidth: 1.5)
        }
        .clipShape(RoundedRectangle(cornerRadius: 14))
    }
}

struct MessageBubble: View {
    let message: MessageItem
    let isGroup: Bool

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
