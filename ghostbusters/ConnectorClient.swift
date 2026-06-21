import Foundation

struct HydraLogEntry: Decodable, Identifiable {
    let at: String
    let event: String
    var id: String { "\(at)-\(event)" }
    let chat_id: String?
    let contact: String?
    let query: String?
    let preview: String?
    let chunks: Int?
    let error: String?
    let reason: String?
}

struct HydraLogsResponse: Decodable {
    let configured: Bool
    let count: Int
    let logs: [HydraLogEntry]
}

struct ChatSuggestionsResponse: Decodable {
    let chat_id: String
    let suggestions: [String]
    let needs_reply: Bool?
    let reason: String?
}

enum ConnectorClient {
    static let baseURL = URL(string: "http://127.0.0.1:8787")!

    private static let session: URLSession = {
        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = 15
        config.timeoutIntervalForResource = 30
        config.waitsForConnectivity = false
        return URLSession(configuration: config)
    }()

    static func fetchChats(limit: Int = 30) async throws -> [ChatSummary] {
        let url = baseURL.appending(path: "api/chats").appending(queryItems: [
            URLQueryItem(name: "limit", value: "\(limit)")
        ])
        let (data, response) = try await session.data(from: url)
        try validate(response)
        return try JSONDecoder().decode([ChatSummary].self, from: data)
    }

    static func fetchMessages(chatId: String, limit: Int = 50) async throws -> [MessageItem] {
        let url = baseURL.appending(path: "api/chats/\(chatId)/messages").appending(queryItems: [
            URLQueryItem(name: "limit", value: "\(limit)")
        ])
        let (data, response) = try await session.data(from: url)
        try validate(response)
        return try JSONDecoder().decode([MessageItem].self, from: data)
    }

    static func fetchPriorities(limit: Int = 3, chatId: String? = nil, refresh: Bool = false) async throws -> [PriorityItem] {
        var items = [URLQueryItem(name: "limit", value: "\(limit)")]
        if let chatId {
            items.append(URLQueryItem(name: "chat_id", value: chatId))
        }
        if refresh {
            items.append(URLQueryItem(name: "refresh", value: "true"))
        }
        let url = baseURL.appending(path: "api/priorities").appending(queryItems: items)
        let (data, response) = try await session.data(from: url)
        try validate(response)
        return try JSONDecoder().decode([PriorityItem].self, from: data)
    }

    static func fetchReplySuggestions(chatId: String, limit: Int = 3) async throws -> ChatSuggestionsResponse {
        let url = baseURL
            .appending(path: "api/chats/\(chatId)/suggestions")
            .appending(queryItems: [URLQueryItem(name: "limit", value: "\(limit)")])
        let (data, response) = try await session.data(from: url)
        try validate(response)
        return try JSONDecoder().decode(ChatSuggestionsResponse.self, from: data)
    }

    static func sendMessage(chatId: String, text: String) async throws -> MessageItem {
        var request = URLRequest(url: baseURL.appending(path: "api/chats/\(chatId)/messages"))
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONEncoder().encode(["text": text])
        let (data, response) = try await session.data(for: request)
        try validate(response)
        return try JSONDecoder().decode(MessageItem.self, from: data)
    }

    static func triggerPrefetch(limit: Int = 3) async throws {
        var request = URLRequest(url: baseURL.appending(path: "api/prefetch").appending(queryItems: [
            URLQueryItem(name: "limit", value: "\(limit)")
        ]))
        request.httpMethod = "POST"
        request.timeoutInterval = 10
        let (_, response) = try await session.data(for: request)
        try validate(response)
    }

    static func fetchHydraLogs(limit: Int = 20) async throws -> HydraLogsResponse {
        let url = baseURL.appending(path: "api/hydra/logs").appending(queryItems: [
            URLQueryItem(name: "limit", value: "\(limit)")
        ])
        let (data, response) = try await session.data(from: url)
        try validate(response)
        return try JSONDecoder().decode(HydraLogsResponse.self, from: data)
    }

    private static func validate(_ response: URLResponse) throws {
        guard let http = response as? HTTPURLResponse else {
            throw URLError(.badServerResponse)
        }
        guard (200...299).contains(http.statusCode) else {
            throw URLError(.badServerResponse)
        }
    }
}

enum Formatters {
    static func initials(_ name: String) -> String {
        let parts = name.split(separator: " ").map(String.init)
        if parts.count >= 2 {
            return String(parts[0].prefix(1) + parts[1].prefix(1)).uppercased()
        }
        let cleaned = name.filter { $0.isLetter || $0.isNumber }
        return String(cleaned.prefix(2)).uppercased()
    }

    static func time(_ iso: String) -> String {
        guard let date = parseISO(iso) else { return "" }

        let cal = Calendar.current
        if cal.isDateInToday(date) {
            return date.formatted(date: .omitted, time: .shortened)
        }
        if cal.isDateInYesterday(date) {
            return "Yesterday"
        }
        return date.formatted(.dateTime.month(.abbreviated).day())
    }

    /// Hours or days since a reply became needed (e.g. "2h", "3d").
    static func replyWait(_ iso: String) -> String {
        guard let date = parseISO(iso) else { return "" }

        let seconds = max(0, Date().timeIntervalSince(date))
        let minutes = Int(seconds / 60)
        if minutes < 60 {
            return minutes <= 1 ? "now" : "\(minutes)m"
        }
        let hours = Int(seconds / 3600)
        if hours < 24 {
            return "\(hours)h"
        }
        let days = Int(seconds / 86400)
        if days < 7 {
            return "\(days)d"
        }
        let weeks = days / 7
        return "\(weeks)w"
    }

    private static func parseISO(_ iso: String) -> Date? {
        let parser = ISO8601DateFormatter()
        parser.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let date = parser.date(from: iso) {
            return date
        }
        parser.formatOptions = [.withInternetDateTime]
        return parser.date(from: iso)
    }
}
