import Foundation

struct ChatSummary: Codable, Identifiable, Hashable {
    let chat_id: String
    let chat_guid: String
    let display_name: String
    let contact_handle: String
    let last_message: String
    let last_message_at: String
    let is_from_me: Bool

    var id: String { chat_id }
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
    let suggested_response: String
    let severity: String
    let importance_score: Double

    var id: String { "\(rank)-\(chat_id)" }
}

enum InboxDestination: Hashable {
    case ghostbusters
    case chat(ChatSummary)
}
