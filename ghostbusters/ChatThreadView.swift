import SwiftUI

struct ChatThreadView: View {
    let chat: ChatSummary

    @State private var messages: [MessageItem] = []
    @State private var recommendation: PriorityItem?
    @State private var isLoading = true

    var body: some View {
        VStack(spacing: 0) {
            if let recommendation {
                SuggestionBanner(recommendation: recommendation)
            }

            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(spacing: 8) {
                        ForEach(messages) { message in
                            MessageBubble(message: message)
                                .id(message.id)
                        }
                    }
                    .padding(.horizontal, 12)
                    .padding(.vertical, 8)
                }
                .onChange(of: messages.count) { _, _ in
                    if let last = messages.last {
                        proxy.scrollTo(last.id, anchor: .bottom)
                    }
                }
            }

            inputBar
        }
        .navigationTitle(chat.display_name)
        .navigationBarTitleDisplayMode(.inline)
        .task { await load() }
    }

    private var inputBar: some View {
        HStack(spacing: 10) {
            Image(systemName: "plus.circle.fill")
                .font(.title2)
                .foregroundStyle(.gray)
            Text("iMessage")
                .foregroundStyle(.secondary)
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(.vertical, 8)
                .padding(.horizontal, 12)
                .background(Color(.systemGray6))
                .clipShape(Capsule())
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
        .background(.bar)
    }

    private func load() async {
        isLoading = true
        do {
            async let m = ConnectorClient.fetchMessages(chatId: chat.chat_id)
            async let p = ConnectorClient.fetchPriorities(limit: 1, chatId: chat.chat_id)
            messages = try await m
            recommendation = try await p.first
        } catch {
            messages = []
            recommendation = nil
        }
        isLoading = false
    }
}

struct SuggestionBanner: View {
    let recommendation: PriorityItem

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Label("Ghostbusters suggestion", systemImage: "sparkles")
                .font(.caption.weight(.semibold))
                .foregroundStyle(.blue)
            Text(recommendation.suggested_response)
                .font(.subheadline)
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.blue.opacity(0.1))
    }
}

struct MessageBubble: View {
    let message: MessageItem

    var body: some View {
        HStack {
            if message.is_from_me { Spacer(minLength: 48) }
            Text(message.text)
                .font(.body)
                .padding(.horizontal, 14)
                .padding(.vertical, 8)
                .background(message.is_from_me ? Color.blue : Color(.systemGray5))
                .foregroundStyle(message.is_from_me ? .white : .primary)
                .clipShape(RoundedRectangle(cornerRadius: 18))
            if !message.is_from_me { Spacer(minLength: 48) }
        }
    }
}
