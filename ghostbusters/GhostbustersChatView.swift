import SwiftUI

struct GhostbustersChatView: View {
    @Environment(PrioritiesStore.self) private var prioritiesStore
    let onOpenChat: (ChatSummary, String) -> Void
    @State private var hydraLogs: HydraLogsResponse?
    @State private var showHydraLogs = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                header

                if prioritiesStore.isRefreshing && prioritiesStore.priorities.isEmpty {
                    ProgressView()
                        .frame(maxWidth: .infinity)
                        .padding(.top, 40)
                } else if let errorMessage = prioritiesStore.lastError, prioritiesStore.priorities.isEmpty {
                    Text(errorMessage)
                        .foregroundStyle(.orange)
                        .padding()
                } else if prioritiesStore.priorities.isEmpty {
                    Text("You're all caught up. No urgent replies.")
                        .foregroundStyle(.secondary)
                        .padding()
                } else {
                    ForEach(prioritiesStore.priorities) { priority in
                        PriorityCard(priority: priority) {
                            openPriority(priority)
                        }
                    }
                }

                hydraLogsSection
            }
            .padding()
        }
        .background(Color(.systemGroupedBackground))
        .navigationTitle("Ghostbusters")
        .navigationBarTitleDisplayMode(.inline)
        .task {
            if prioritiesStore.priorities.isEmpty {
                await prioritiesStore.refresh(showLoading: true)
            }
            await loadHydraLogs()
        }
        .refreshable {
            await prioritiesStore.refresh(showLoading: false)
            await loadHydraLogs()
        }
    }

    private func openPriority(_ priority: PriorityItem) {
        let chat =
            prioritiesStore.chats.first(where: { $0.chat_id == priority.chat_id })
            ?? ChatSummary(
                chat_id: priority.chat_id,
                chat_guid: priority.chat_guid,
                display_name: priority.contact_name,
                contact_handle: priority.contact_handle,
                last_message: priority.last_message_preview,
                last_message_at: priority.last_message_at,
                is_from_me: false,
                is_group: priority.chat_guid.contains(";+;"),
                needs_reply: true
            )
        onOpenChat(chat, priority.suggested_response)
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 8) {
                Text("👻")
                    .font(.largeTitle)
                Text("Your top 3")
                    .font(.title2.bold())
                if prioritiesStore.isRefreshing && !prioritiesStore.priorities.isEmpty {
                    ProgressView()
                        .controlSize(.small)
                }
            }
            Text("These are the conversations that need a reply most urgently.")
                .font(.subheadline)
                .foregroundStyle(.secondary)
        }
    }

    private var hydraLogsSection: some View {
        Group {
            if let hydraLogs {
                DisclosureGroup(isExpanded: $showHydraLogs) {
                    if hydraLogs.logs.isEmpty {
                        Text(hydraLogs.configured ? "No HydraDB calls yet." : "HydraDB not configured in connector/.env")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    } else {
                        ForEach(hydraLogs.logs.reversed()) { entry in
                            VStack(alignment: .leading, spacing: 4) {
                                Text(entry.event)
                                    .font(.caption.weight(.semibold))
                                if let contact = entry.contact {
                                    Text(contact)
                                        .font(.caption2)
                                        .foregroundStyle(.secondary)
                                }
                                if let preview = entry.preview, !preview.isEmpty {
                                    Text(preview)
                                        .font(.caption2)
                                        .foregroundStyle(.secondary)
                                        .lineLimit(2)
                                }
                                if let error = entry.error {
                                    Text(error)
                                        .font(.caption2)
                                        .foregroundStyle(.orange)
                                }
                            }
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .padding(.vertical, 4)
                        }
                    }
                } label: {
                    Label("HydraDB activity", systemImage: "brain.head.profile")
                        .font(.subheadline.weight(.semibold))
                }
                .padding(12)
                .background(Color(.systemBackground))
                .clipShape(RoundedRectangle(cornerRadius: 12))
            }
        }
    }

    private func loadHydraLogs() async {
        hydraLogs = try? await ConnectorClient.fetchHydraLogs(limit: 15)
    }
}

struct PriorityCard: View {
    let priority: PriorityItem
    let onOpen: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text("#\(priority.rank)")
                    .font(.caption.weight(.bold))
                    .foregroundStyle(.blue)
                Text(priority.contact_name)
                    .font(.headline)
                if priority.chat_guid.contains(";+;") {
                    Text("GROUP")
                        .font(.caption2.weight(.bold))
                        .padding(.horizontal, 6)
                        .padding(.vertical, 2)
                        .background(Color.purple.opacity(0.12))
                        .foregroundStyle(.purple)
                        .clipShape(Capsule())
                }
                Spacer()
                Text(priority.replyWaitLabel)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(.orange)
                SeverityBadge(severity: priority.severity)
            }

            Text("\"\(priority.last_message_preview)\"")
                .font(.subheadline)
                .foregroundStyle(.secondary)

            Button(action: onOpen) {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Suggested reply")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(.blue)
                    Text(priority.suggested_response)
                        .font(.body)
                        .foregroundStyle(.primary)
                        .multilineTextAlignment(.leading)
                        .fixedSize(horizontal: false, vertical: true)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
                .padding(.horizontal, 16)
                .padding(.vertical, 12)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(Color.blue.opacity(0.08))
                .overlay {
                    RoundedRectangle(cornerRadius: 12, style: .continuous)
                        .stroke(Color.blue.opacity(0.25), lineWidth: 1)
                }
                .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
            }
            .buttonStyle(.plain)

            Button("Open conversation", action: onOpen)
                .font(.subheadline.weight(.semibold))
        }
        .padding(16)
        .background(Color(.systemBackground))
        .clipShape(RoundedRectangle(cornerRadius: 16))
        .shadow(color: .black.opacity(0.06), radius: 4, y: 2)
    }
}

struct SeverityBadge: View {
    let severity: String

    var body: some View {
        Text(severity.uppercased())
            .font(.caption2.weight(.bold))
            .padding(.horizontal, 8)
            .padding(.vertical, 3)
            .background(color.opacity(0.15))
            .foregroundStyle(color)
            .clipShape(Capsule())
    }

    private var color: Color {
        switch severity {
        case "high", "critical": return .red
        case "medium": return .orange
        default: return .green
        }
    }
}
