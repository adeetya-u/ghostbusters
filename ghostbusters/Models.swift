import Foundation

struct ChatSummary: Codable, Identifiable, Hashable {
    let chat_id: String
    let chat_guid: String
    let display_name: String
    let contact_handle: String
    let last_message: String
    let last_message_at: String
    let is_from_me: Bool
    let is_group: Bool
    let needs_reply: Bool
    let reply_waiting_at: String?
    let unread_count: Int

    var id: String { chat_id }

    var hasUnread: Bool { unread_count > 0 }

    init(
        chat_id: String,
        chat_guid: String,
        display_name: String,
        contact_handle: String,
        last_message: String,
        last_message_at: String,
        is_from_me: Bool,
        is_group: Bool = false,
        needs_reply: Bool = false,
        reply_waiting_at: String? = nil,
        unread_count: Int = 0
    ) {
        self.chat_id = chat_id
        self.chat_guid = chat_guid
        self.display_name = display_name
        self.contact_handle = contact_handle
        self.last_message = last_message
        self.last_message_at = last_message_at
        self.is_from_me = is_from_me
        self.is_group = is_group
        self.needs_reply = needs_reply
        self.reply_waiting_at = reply_waiting_at
        self.unread_count = unread_count
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        chat_id = try container.decode(String.self, forKey: .chat_id)
        chat_guid = try container.decode(String.self, forKey: .chat_guid)
        display_name = try container.decode(String.self, forKey: .display_name)
        contact_handle = try container.decode(String.self, forKey: .contact_handle)
        last_message = try container.decode(String.self, forKey: .last_message)
        last_message_at = try container.decode(String.self, forKey: .last_message_at)
        is_from_me = try container.decode(Bool.self, forKey: .is_from_me)
        is_group = try container.decodeIfPresent(Bool.self, forKey: .is_group) ?? false
        needs_reply = try container.decodeIfPresent(Bool.self, forKey: .needs_reply) ?? false
        reply_waiting_at = try container.decodeIfPresent(String.self, forKey: .reply_waiting_at)
        unread_count = try container.decodeIfPresent(Int.self, forKey: .unread_count) ?? 0
    }
}

extension ChatSummary {
    var inboxTimestamp: String {
        if needs_reply, let reply_waiting_at, !reply_waiting_at.isEmpty {
            return Formatters.replyWait(reply_waiting_at)
        }
        return Formatters.time(last_message_at)
    }
}

struct MessageItem: Codable, Identifiable {
    let row_id: Int
    let chat_id: String
    let chat_guid: String
    let contact_handle: String
    let contact_name: String?
    let text: String
    let is_from_me: Bool
    let timestamp: String
    let is_read: Bool

    var id: Int { row_id }
}

struct PriorityItem: Codable, Identifiable {
    let rank: Int
    let contact_name: String
    let contact_handle: String
    let chat_id: String
    let chat_guid: String
    let last_message_preview: String
    let last_message_at: String
    let reply_waiting_at: String?
    let suggested_response: String
    let severity: String
    let importance_score: Double

    var id: String { "\(rank)-\(chat_id)" }

    var replyWaitLabel: String {
        let iso = reply_waiting_at ?? last_message_at
        let wait = Formatters.replyWait(iso)
        return wait.isEmpty ? Formatters.time(last_message_at) : wait
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        rank = try container.decode(Int.self, forKey: .rank)
        contact_name = try container.decode(String.self, forKey: .contact_name)
        contact_handle = try container.decode(String.self, forKey: .contact_handle)
        chat_id = try container.decode(String.self, forKey: .chat_id)
        chat_guid = try container.decode(String.self, forKey: .chat_guid)
        last_message_preview = try container.decode(String.self, forKey: .last_message_preview)
        last_message_at = try container.decode(String.self, forKey: .last_message_at)
        reply_waiting_at = try container.decodeIfPresent(String.self, forKey: .reply_waiting_at)
        suggested_response = try container.decode(String.self, forKey: .suggested_response)
        severity = try container.decode(String.self, forKey: .severity)
        importance_score = try container.decode(Double.self, forKey: .importance_score)
    }
}

enum InboxDestination: Hashable {
    case ghostbusters
    case chat(chat: ChatSummary, prefilledDraft: String)
}
