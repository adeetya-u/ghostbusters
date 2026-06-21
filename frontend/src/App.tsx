import { useCallback, useEffect, useState } from "react";
import type { Chat, Priority, Message } from "./api";
import {
  fetchChats,
  fetchMessages,
  fetchPriorities,
  fetchReplySuggestions,
  sendMessage,
  formatTime,
  chatInboxTimestamp,
  initials,
  severityLabel,
} from "./api";

type View = { kind: "list" } | { kind: "chat"; chat: Chat };

function GhostbustersRecommendations({
  priorities,
  loading,
  onSelect,
}: {
  priorities: Priority[];
  loading: boolean;
  onSelect: (chatId: string, suggestedResponse: string) => void;
}) {
  return (
    <section className="recommendations-section">
      <div className="recommendations-header">
        <span className="ghost-icon" aria-hidden>
          👻
        </span>
        <h2>Ghostbusters</h2>
      </div>
      <p className="recommendations-subtitle">
        Top 3 conversations you should respond to
      </p>

      {loading ? (
        <p className="loading">Loading recommendations…</p>
      ) : priorities.length === 0 ? (
        <p className="empty-rec">You're all caught up. No urgent replies.</p>
      ) : (
        <div className="recommendation-cards">
          {priorities.map((p) => (
            <article key={p.chat_id} className="recommendation-card">
              <div className="rec-card-top">
                <span className="rec-rank">#{p.rank}</span>
                <span className={`rec-severity ${p.severity}`}>
                  {severityLabel(p.severity)}
                </span>
              </div>
              <p className="rec-contact">{p.contact_name}</p>
              <p className="rec-preview">"{p.last_message_preview}"</p>
              <button
                type="button"
                className="rec-suggestion"
                onClick={() => onSelect(p.chat_id, p.suggested_response)}
              >
                {p.suggested_response}
              </button>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}

function MessageListScreen({
  chats,
  priorities,
  loadingChats,
  loadingPriorities,
  onOpenChat,
}: {
  chats: Chat[];
  priorities: Priority[];
  loadingChats: boolean;
  loadingPriorities: boolean;
  onOpenChat: (chat: Chat, prefilledDraft?: string) => void;
}) {
  return (
    <>
      <header className="screen-header">
        <h1>Messages</h1>
      </header>

      {loadingChats ? (
        <p className="loading">Loading conversations…</p>
      ) : (
        <>
          <p className="section-label">Recent</p>
          <ul className="chat-list">
            {chats.map((chat) => (
              <li key={chat.chat_id}>
                <button
                  type="button"
                  className="chat-row"
                  onClick={() => onOpenChat(chat)}
                >
                  <div className="avatar">{initials(chat.display_name)}</div>
                  <div className="chat-row-body">
                    <div className="chat-row-top">
                      <span className="chat-row-name">{chat.display_name}</span>
                      <span className="chat-row-time">
                        {chatInboxTimestamp(chat)}
                      </span>
                    </div>
                    <p
                      className={`chat-row-preview${!chat.is_from_me ? " unread" : ""}`}
                    >
                      {chat.is_from_me ? "You: " : ""}
                      {chat.last_message}
                    </p>
                  </div>
                  <span className="chevron" aria-hidden>
                    ›
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </>
      )}

      <GhostbustersRecommendations
        priorities={priorities}
        loading={loadingPriorities}
        onSelect={(chatId, suggestedResponse) => {
          const chat = chats.find((c) => c.chat_id === chatId);
          if (chat) onOpenChat(chat, suggestedResponse);
        }}
      />
    </>
  );
}

function ChatDetailScreen({
  chat,
  messages,
  suggestions,
  draft,
  loadingMessages,
  loadingSuggestions,
  onBack,
  onSelectSuggestion,
  onDraftChange,
  onSend,
  sending,
}: {
  chat: Chat;
  messages: Message[];
  suggestions: string[];
  draft: string;
  loadingMessages: boolean;
  loadingSuggestions: boolean;
  onBack: () => void;
  onSelectSuggestion: (text: string) => void;
  onDraftChange: (text: string) => void;
  onSend: () => void;
  sending: boolean;
}) {
  return (
    <div className="chat-detail">
      <header className="screen-header chat-header">
        <button type="button" className="back-button" onClick={onBack}>
          ‹ Messages
        </button>
        <div className="chat-header-title">{chat.display_name}</div>
      </header>

      {loadingMessages ? (
        <p className="loading">Loading messages…</p>
      ) : (
        <div className="messages-thread">
          {messages.map((msg) => (
            <div
              key={msg.row_id}
              className={`message-bubble ${msg.is_from_me ? "from-me" : "from-them"}`}
            >
              {chat.is_group && !msg.is_from_me && msg.contact_name ? (
                <span className="message-sender">{msg.contact_name}</span>
              ) : null}
              {msg.text}
            </div>
          ))}
        </div>
      )}

      <div className="composer-area">
        <div className="reply-suggestions">
          <p className="reply-suggestions-label">Ghostbusters</p>
          {loadingSuggestions ? (
            <p className="loading">Generating suggestions…</p>
          ) : (
            <div className="reply-suggestion-row">
              {suggestions.map((text) => (
                <button
                  key={text}
                  type="button"
                  className="reply-suggestion-chip"
                  onClick={() => onSelectSuggestion(text)}
                >
                  {text}
                </button>
              ))}
            </div>
          )}
        </div>
        <div className="composer-input">
          <input
            type="text"
            value={draft}
            onChange={(e) => onDraftChange(e.target.value)}
            placeholder="iMessage"
            onKeyDown={(e) => {
              if (e.key === "Enter" && draft.trim()) onSend();
            }}
          />
          <button
            type="button"
            className="send-button"
            disabled={!draft.trim() || sending}
            onClick={onSend}
          >
            {sending ? "…" : "Send"}
          </button>
        </div>
      </div>
    </div>
  );
}

export default function App() {
  const [view, setView] = useState<View>({ kind: "list" });
  const [chats, setChats] = useState<Chat[]>([]);
  const [priorities, setPriorities] = useState<Priority[]>([]);
  const [messages, setMessages] = useState<Message[]>([]);
  const [chatSuggestions, setChatSuggestions] = useState<string[]>([]);
  const [draft, setDraft] = useState("");
  const [loadingChats, setLoadingChats] = useState(true);
  const [loadingPriorities, setLoadingPriorities] = useState(true);
  const [loadingMessages, setLoadingMessages] = useState(false);
  const [loadingSuggestions, setLoadingSuggestions] = useState(false);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadListData = useCallback(async () => {
    setLoadingChats(true);
    setLoadingPriorities(true);
    setError(null);
    try {
      const [chatData, priorityData] = await Promise.all([
        fetchChats(20),
        fetchPriorities(3),
      ]);
      setChats(chatData);
      setPriorities(priorityData);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load data");
    } finally {
      setLoadingChats(false);
      setLoadingPriorities(false);
    }
  }, []);

  useEffect(() => {
    loadListData();
  }, [loadListData]);

  const openChat = async (chat: Chat, prefilledDraft = "") => {
    setView({ kind: "chat", chat });
    setMessages([]);
    setChatSuggestions([]);
    setDraft(prefilledDraft);
    setLoadingMessages(true);
    setLoadingSuggestions(true);

    try {
      const [msgData, suggestionData] = await Promise.all([
        fetchMessages(chat.chat_id),
        fetchReplySuggestions(chat.chat_id, 3),
      ]);
      setMessages(msgData);
      setChatSuggestions(suggestionData);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load chat");
    } finally {
      setLoadingMessages(false);
      setLoadingSuggestions(false);
    }
  };

  const goBack = () => {
    setView({ kind: "list" });
    setError(null);
    loadListData();
  };

  const sendDraft = async () => {
    if (view.kind !== "chat" || !draft.trim() || sending) return;
    setSending(true);
    setError(null);
    try {
      await sendMessage(view.chat.chat_id, draft.trim());
      setDraft("");
      setChatSuggestions([]);
      setLoadingSuggestions(true);
      const [msgData, suggestionData] = await Promise.all([
        fetchMessages(view.chat.chat_id),
        fetchReplySuggestions(view.chat.chat_id, 3).catch(() => [] as string[]),
      ]);
      setMessages(msgData);
      setChatSuggestions(suggestionData);
      await loadListData();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to send message");
    } finally {
      setSending(false);
      setLoadingSuggestions(false);
    }
  };

  return (
    <div className="app-shell">
      {error ? <p className="error-banner">{error}</p> : null}

      {view.kind === "list" ? (
        <MessageListScreen
          chats={chats}
          priorities={priorities}
          loadingChats={loadingChats}
          loadingPriorities={loadingPriorities}
          onOpenChat={openChat}
        />
      ) : (
        <ChatDetailScreen
          chat={view.chat}
          messages={messages}
          suggestions={chatSuggestions}
          draft={draft}
          loadingMessages={loadingMessages}
          loadingSuggestions={loadingSuggestions}
          onBack={goBack}
          onSelectSuggestion={setDraft}
          onDraftChange={setDraft}
          onSend={sendDraft}
          sending={sending}
        />
      )}
    </div>
  );
}
