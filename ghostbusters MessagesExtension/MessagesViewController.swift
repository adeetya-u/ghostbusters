//
//  MessagesViewController.swift
//  ghostbusters MessagesExtension
//

import UIKit
import Messages
import ObjectiveC

struct PriorityOut: Codable {
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
}

class MessagesViewController: MSMessagesAppViewController {

    private let scrollView = UIScrollView()
    private let refreshControl = UIRefreshControl()
    private let contentStack = UIStackView()
    private let loadingIndicator = UIActivityIndicatorView(style: .large)
    private let statusBanner = UILabel()

    private var conversationKey: String?
    private var isInActiveThread = false
    private var mappedChatId: String?

    private let connectorBaseURL = "http://127.0.0.1:8787"

    override func viewDidLoad() {
        super.viewDidLoad()
        view.subviews.forEach { $0.removeFromSuperview() }
        setupUI()
        requestPresentationStyle(.expanded)
    }

    private func setupUI() {
        view.backgroundColor = .systemBackground

        scrollView.translatesAutoresizingMaskIntoConstraints = false
        scrollView.alwaysBounceVertical = true
        refreshControl.addTarget(self, action: #selector(refreshPulled), for: .valueChanged)
        scrollView.refreshControl = refreshControl
        view.addSubview(scrollView)

        contentStack.axis = .vertical
        contentStack.spacing = 16
        contentStack.translatesAutoresizingMaskIntoConstraints = false
        scrollView.addSubview(contentStack)

        statusBanner.font = .systemFont(ofSize: 13)
        statusBanner.textColor = .systemOrange
        statusBanner.numberOfLines = 0
        statusBanner.isHidden = true

        loadingIndicator.translatesAutoresizingMaskIntoConstraints = false
        loadingIndicator.hidesWhenStopped = true
        view.addSubview(loadingIndicator)

        NSLayoutConstraint.activate([
            scrollView.topAnchor.constraint(equalTo: view.safeAreaLayoutGuide.topAnchor),
            scrollView.leadingAnchor.constraint(equalTo: view.leadingAnchor),
            scrollView.trailingAnchor.constraint(equalTo: view.trailingAnchor),
            scrollView.bottomAnchor.constraint(equalTo: view.bottomAnchor),

            contentStack.topAnchor.constraint(equalTo: scrollView.topAnchor, constant: 12),
            contentStack.leadingAnchor.constraint(equalTo: scrollView.leadingAnchor, constant: 16),
            contentStack.trailingAnchor.constraint(equalTo: scrollView.trailingAnchor, constant: -16),
            contentStack.bottomAnchor.constraint(equalTo: scrollView.bottomAnchor, constant: -20),
            contentStack.widthAnchor.constraint(equalTo: scrollView.widthAnchor, constant: -32),

            loadingIndicator.centerXAnchor.constraint(equalTo: view.centerXAnchor),
            loadingIndicator.centerYAnchor.constraint(equalTo: view.centerYAnchor),
        ])
    }

    @objc private func refreshPulled() {
        loadRecommendations()
    }

    // MARK: - UI building blocks

    private func brandHeader() -> UIView {
        let row = UIStackView()
        row.axis = .horizontal
        row.alignment = .center
        row.spacing = 10

        let icon = UILabel()
        icon.text = "👻"
        icon.font = .systemFont(ofSize: 28)

        let titles = UIStackView()
        titles.axis = .vertical
        titles.spacing = 2

        let name = UILabel()
        name.text = "Ghostbusters"
        name.font = .boldSystemFont(ofSize: 22)

        let tagline = UILabel()
        tagline.text = isInActiveThread
            ? "Suggestion for this chat"
            : "Top conversations to respond to"
        tagline.font = .systemFont(ofSize: 14)
        tagline.textColor = .secondaryLabel

        titles.addArrangedSubview(name)
        titles.addArrangedSubview(tagline)

        row.addArrangedSubview(icon)
        row.addArrangedSubview(titles)
        return row
    }

    private func sectionHeader(_ title: String, subtitle: String? = nil) -> UIView {
        let stack = UIStackView()
        stack.axis = .vertical
        stack.spacing = 4

        let titleLabel = UILabel()
        titleLabel.text = title
        titleLabel.font = .boldSystemFont(ofSize: 17)
        stack.addArrangedSubview(titleLabel)

        if let subtitle {
            let sub = UILabel()
            sub.text = subtitle
            sub.font = .systemFont(ofSize: 13)
            sub.textColor = .secondaryLabel
            sub.numberOfLines = 0
            stack.addArrangedSubview(sub)
        }
        return stack
    }

    private func divider() -> UIView {
        let line = UIView()
        line.backgroundColor = .separator
        line.translatesAutoresizingMaskIntoConstraints = false
        line.heightAnchor.constraint(equalToConstant: 1).isActive = true
        return line
    }

    private func severityColor(_ severity: String) -> UIColor {
        switch severity.lowercased() {
        case "high": return .systemRed
        case "medium": return .systemOrange
        default: return .systemGreen
        }
    }

    private func priorityCard(_ priority: PriorityOut, style: CardStyle) -> UIView {
        let card = UIView()
        card.backgroundColor = style == .hero
            ? UIColor.systemBlue.withAlphaComponent(0.10)
            : UIColor.secondarySystemBackground
        card.layer.cornerRadius = 14
        card.layer.borderWidth = style == .hero ? 1.5 : 0
        card.layer.borderColor = style == .hero
            ? UIColor.systemBlue.withAlphaComponent(0.35).cgColor
            : nil
        card.translatesAutoresizingMaskIntoConstraints = false

        let headerRow = UIStackView()
        headerRow.axis = .horizontal
        headerRow.alignment = .center
        headerRow.spacing = 8

        let rankLabel = UILabel()
        rankLabel.text = "#\(priority.rank)"
        rankLabel.font = .boldSystemFont(ofSize: style == .hero ? 18 : 15)
        rankLabel.textColor = .systemBlue
        rankLabel.setContentHuggingPriority(.required, for: .horizontal)

        let nameLabel = UILabel()
        nameLabel.text = priority.contact_name
        nameLabel.font = .boldSystemFont(ofSize: style == .hero ? 17 : 15)
        nameLabel.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)

        let badge = UILabel()
        badge.text = "  \(priority.severity.uppercased())  "
        badge.font = .boldSystemFont(ofSize: 10)
        badge.textColor = .white
        badge.backgroundColor = severityColor(priority.severity)
        badge.layer.cornerRadius = 6
        badge.clipsToBounds = true
        badge.setContentHuggingPriority(.required, for: .horizontal)

        headerRow.addArrangedSubview(rankLabel)
        headerRow.addArrangedSubview(nameLabel)
        headerRow.addArrangedSubview(UIView())
        headerRow.addArrangedSubview(badge)

        let previewLabel = UILabel()
        previewLabel.text = "They said: \"\(priority.last_message_preview)\""
        previewLabel.font = .italicSystemFont(ofSize: style == .hero ? 14 : 13)
        previewLabel.textColor = .secondaryLabel
        previewLabel.numberOfLines = 2

        let suggestionTitle = UILabel()
        suggestionTitle.text = "Suggested reply"
        suggestionTitle.font = .systemFont(ofSize: 12, weight: .semibold)
        suggestionTitle.textColor = .secondaryLabel

        let suggestionLabel = UILabel()
        suggestionLabel.text = priority.suggested_response
        suggestionLabel.font = .systemFont(ofSize: style == .hero ? 16 : 15)
        suggestionLabel.numberOfLines = 0

        let insertHint = UILabel()
        insertHint.text = "Tap to insert into message field"
        insertHint.font = .systemFont(ofSize: 12)
        insertHint.textColor = .systemBlue

        let stack = UIStackView(arrangedSubviews: [
            headerRow, previewLabel, suggestionTitle, suggestionLabel, insertHint,
        ])
        stack.axis = .vertical
        stack.spacing = style == .hero ? 10 : 6
        stack.translatesAutoresizingMaskIntoConstraints = false
        card.addSubview(stack)

        NSLayoutConstraint.activate([
            stack.topAnchor.constraint(equalTo: card.topAnchor, constant: 14),
            stack.leadingAnchor.constraint(equalTo: card.leadingAnchor, constant: 14),
            stack.trailingAnchor.constraint(equalTo: card.trailingAnchor, constant: -14),
            stack.bottomAnchor.constraint(equalTo: card.bottomAnchor, constant: -14),
        ])

        let tap = UITapGestureRecognizer(target: self, action: #selector(cardTapped(_:)))
        card.addGestureRecognizer(tap)
        card.isUserInteractionEnabled = true
        objc_setAssociatedObject(card, &AssociatedKeys.priority, priority, .OBJC_ASSOCIATION_RETAIN_NONATOMIC)

        return card
    }

    private enum CardStyle {
        case hero
        case standard
    }

    @objc private func cardTapped(_ gesture: UITapGestureRecognizer) {
        guard let card = gesture.view,
              let priority = objc_getAssociatedObject(card, &AssociatedKeys.priority) as? PriorityOut
        else { return }

        if isInActiveThread, let key = conversationKey {
            UserDefaults.standard.set(priority.chat_id, forKey: "ghostbusters_chat_\(key)")
            mappedChatId = priority.chat_id
        }

        activeConversation?.insertText(priority.suggested_response, completionHandler: nil)
    }

    private func reloadContent(contextPriority: PriorityOut?, topPriorities: [PriorityOut], apiError: Bool) {
        contentStack.arrangedSubviews.forEach { $0.removeFromSuperview() }

        contentStack.addArrangedSubview(brandHeader())

        if apiError {
            statusBanner.text = "Could not reach connector at \(connectorBaseURL). Showing cached/empty state."
            statusBanner.isHidden = false
            contentStack.addArrangedSubview(statusBanner)
        }

        if isInActiveThread {
            buildThreadLayout(contextPriority: contextPriority, topPriorities: topPriorities)
        } else {
            buildBrowseLayout(topPriorities: topPriorities)
        }
    }

    /// Opened from Messages list / no active thread — top 3 is the entire focus.
    private func buildBrowseLayout(topPriorities: [PriorityOut]) {
        contentStack.addArrangedSubview(
            sectionHeader(
                "Respond to these first",
                subtitle: "Highest-priority conversations across your messages"
            )
        )

        if topPriorities.isEmpty {
            contentStack.addArrangedSubview(emptyState("You're all caught up — no urgent replies."))
        } else {
            topPriorities.forEach { contentStack.addArrangedSubview(priorityCard($0, style: .hero)) }
        }

        contentStack.addArrangedSubview(footerNote(
            "Open a conversation in Messages, then tap the Ghostbusters icon below the keyboard for a reply suggestion for that chat."
        ))
    }

    /// Inside a chat thread — this conversation's suggestion is primary; other priorities below.
    private func buildThreadLayout(contextPriority: PriorityOut?, topPriorities: [PriorityOut]) {
        contentStack.addArrangedSubview(
            sectionHeader(
                "This conversation",
                subtitle: mappedChatId != nil
                    ? "Ghostbusters recommendation for the chat you're in"
                    : "Tap a card below once to link this thread, then reopen for chat-specific suggestions"
            )
        )

        if let context = contextPriority {
            contentStack.addArrangedSubview(priorityCard(context, style: .hero))
        } else if mappedChatId == nil {
            contentStack.addArrangedSubview(emptyState(
                "No linked chat yet. Tap any recommendation in \"Also worth responding to\" to associate it with this thread."
            ))
        } else {
            contentStack.addArrangedSubview(emptyState("No suggestion for this thread right now."))
        }

        let others = topPriorities.filter { $0.chat_id != mappedChatId }
        if !others.isEmpty {
            contentStack.addArrangedSubview(divider())
            contentStack.addArrangedSubview(
                sectionHeader(
                    "Also worth responding to",
                    subtitle: "Other high-priority conversations"
                )
            )
            others.prefix(3).forEach { contentStack.addArrangedSubview(priorityCard($0, style: .standard)) }
        }
    }

    private func emptyState(_ text: String) -> UIView {
        let label = UILabel()
        label.text = text
        label.font = .systemFont(ofSize: 14)
        label.textColor = .secondaryLabel
        label.numberOfLines = 0
        label.textAlignment = .center

        let wrap = UIView()
        wrap.backgroundColor = UIColor.secondarySystemBackground
        wrap.layer.cornerRadius = 12
        label.translatesAutoresizingMaskIntoConstraints = false
        wrap.addSubview(label)
        NSLayoutConstraint.activate([
            label.topAnchor.constraint(equalTo: wrap.topAnchor, constant: 16),
            label.leadingAnchor.constraint(equalTo: wrap.leadingAnchor, constant: 14),
            label.trailingAnchor.constraint(equalTo: wrap.trailingAnchor, constant: -14),
            label.bottomAnchor.constraint(equalTo: wrap.bottomAnchor, constant: -16),
        ])
        return wrap
    }

    private func footerNote(_ text: String) -> UIView {
        let label = UILabel()
        label.text = text
        label.font = .systemFont(ofSize: 12)
        label.textColor = .tertiaryLabel
        label.numberOfLines = 0
        return label
    }

    // MARK: - Networking

    private func fetchPriorities(
        limit: Int,
        chatId: String? = nil,
        completion: @escaping (_ items: [PriorityOut], _ error: Bool) -> Void
    ) {
        var components = URLComponents(string: "\(connectorBaseURL)/api/priorities")!
        var queryItems = [URLQueryItem(name: "limit", value: "\(limit)")]
        if let chatId {
            queryItems.append(URLQueryItem(name: "chat_id", value: chatId))
        }
        components.queryItems = queryItems

        guard let url = components.url else {
            completion([], true)
            return
        }

        URLSession.shared.dataTask(with: url) { data, response, error in
            let httpError = (response as? HTTPURLResponse).map { !(200...299).contains($0.statusCode) } ?? false
            guard error == nil, !httpError, let data = data else {
                DispatchQueue.main.async { completion([], true) }
                return
            }
            let items = (try? JSONDecoder().decode([PriorityOut].self, from: data)) ?? []
            DispatchQueue.main.async { completion(items, false) }
        }.resume()
    }

    private func loadRecommendations() {
        if !refreshControl.isRefreshing {
            loadingIndicator.startAnimating()
            contentStack.isHidden = true
        }
        statusBanner.isHidden = true

        mappedChatId = conversationKey.flatMap {
            UserDefaults.standard.string(forKey: "ghostbusters_chat_\($0)")
        }

        let group = DispatchGroup()
        var contextItems: [PriorityOut] = []
        var topItems: [PriorityOut] = []
        var hadError = false

        if isInActiveThread, let chatId = mappedChatId {
            group.enter()
            fetchPriorities(limit: 1, chatId: chatId) { items, error in
                contextItems = items
                hadError = hadError || error
                group.leave()
            }
        }

        group.enter()
        fetchPriorities(limit: 3) { items, error in
            topItems = items
            hadError = hadError || error
            group.leave()
        }

        group.notify(queue: .main) { [weak self] in
            guard let self else { return }
            self.loadingIndicator.stopAnimating()
            self.refreshControl.endRefreshing()
            self.contentStack.isHidden = false
            self.reloadContent(
                contextPriority: contextItems.first,
                topPriorities: topItems,
                apiError: hadError && topItems.isEmpty && contextItems.isEmpty
            )
        }
    }

    // MARK: - Conversation Handling

    override func willBecomeActive(with conversation: MSConversation) {
        conversationKey = conversation.remoteParticipantIdentifiers
            .map(\.uuidString)
            .sorted()
            .joined(separator: "_")
        isInActiveThread = !conversation.remoteParticipantIdentifiers.isEmpty
        loadRecommendations()
    }

    override func didBecomeActive(with conversation: MSConversation) {
        requestPresentationStyle(.expanded)
    }

    override func didResignActive(with conversation: MSConversation) {}
    override func didReceive(_ message: MSMessage, conversation: MSConversation) {}
    override func didStartSending(_ message: MSMessage, conversation: MSConversation) {}
    override func didCancelSending(_ message: MSMessage, conversation: MSConversation) {}
    override func willTransition(to presentationStyle: MSMessagesAppPresentationStyle) {}
    override func didTransition(to presentationStyle: MSMessagesAppPresentationStyle) {
        if presentationStyle == .compact {
            requestPresentationStyle(.expanded)
        }
    }
}

private enum AssociatedKeys {
    static var priority = "priority"
}
