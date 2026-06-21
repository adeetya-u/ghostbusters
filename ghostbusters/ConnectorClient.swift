import Foundation

enum ConnectorClient {
    static let baseURL = URL(string: "http://127.0.0.1:8787")!

    static func fetchChats(limit: Int = 30) async throws -> [ChatSummary] {
        let url = baseURL.appending(path: "api/chats").appending(queryItems: [
            URLQueryItem(name: "limit", value: "\(limit)")
        ])
        let (data, response) = try await URLSession.shared.data(from: url)
        try validate(response)
        return try JSONDecoder().decode([ChatSummary].self, from: data)
    }

    static func fetchMessages(chatId: String, limit: Int = 50) async throws -> [MessageItem] {
        let url = baseURL.appending(path: "api/chats/\(chatId)/messages").appending(queryItems: [
            URLQueryItem(name: "limit", value: "\(limit)")
        ])
        let (data, response) = try await URLSession.shared.data(from: url)
        try validate(response)
        return try JSONDecoder().decode([MessageItem].self, from: data)
    }

    static func fetchPriorities(limit: Int = 3, chatId: String? = nil) async throws -> [PriorityItem] {
        var items = [URLQueryItem(name: "limit", value: "\(limit)")]
        if let chatId {
            items.append(URLQueryItem(name: "chat_id", value: chatId))
        }
        let url = baseURL.appending(path: "api/priorities").appending(queryItems: items)
        let (data, response) = try await URLSession.shared.data(from: url)
        try validate(response)
        return try JSONDecoder().decode([PriorityItem].self, from: data)
    }

    private static func validate(_ response: URLResponse) throws {
        guard let http = response as? HTTPURLResponse, (200...299).contains(http.statusCode) else {
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
        let parser = ISO8601DateFormatter()
        parser.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        var date = parser.date(from: iso)
        if date == nil {
            parser.formatOptions = [.withInternetDateTime]
            date = parser.date(from: iso)
        }
        guard let date else { return "" }

        let cal = Calendar.current
        if cal.isDateInToday(date) {
            return date.formatted(date: .omitted, time: .shortened)
        }
        if cal.isDateInYesterday(date) {
            return "Yesterday"
        }
        return date.formatted(.dateTime.month(.abbreviated).day())
    }
}
