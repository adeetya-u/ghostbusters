import { useCallback, useEffect, useState } from "react";
import type { Chat, Priority, Message } from "./api";
import {
  fetchChats,
  fetchMessages,
  fetchPriorities,
  formatTime,
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
  onSelect: (chatId: string) => void;
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
        <p className="empty-rec">You're all caught up — no urgent replies.</p>
      ) : (
        <div className="recommendation-cards">
          {priorities.map((p) => (
            <button
              key={p.chat_id}
              type="button"
              className="recommendation-card"
              onClick={() => onSelect(p.chat_id)}
            >
              <div className="rec-card-top">
                <span className="rec-rank">#{p.rank}</span>
                <span className={`rec-severity ${p.severity}`}>
                  {severityLabel(p.severity)}
                </span>
              </div>
              <p className="rec-contact">{p.contact_name}</p>
              <p className="rec-preview">"{p.last_message_preview}"</p>
              <p className="rec-suggestion">{p.suggested_response}</p>
            </button>
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
  onOpenChat: (chat: Chat) => void;
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
                        {formatTime(chat.last_message_at)}
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
        onSelect={(chatId) => {
          const chat = chats.find((c) => c.chat_id === chatId);
          if (chat) onOpenChat(chat);
        }}
      />
    </>
  );
}

function ChatDetailScreen({
  chat,
  messages,
  recommendation,
  loadingMessages,
  loadingRec,
  onBack,
}: {
  chat: Chat;
  messages: Message[];
  recommendation: Priority | null;
  loadingMessages: boolean;
  loadingRec: boolean;
  onBack: () => void;
}) {
  return (
    <div className="chat-detail">
      <header className="screen-header chat-header">
        <button type="button" className="back-button" onClick={onBack}>
          ‹ Messages
        </button>
        <div className="chat-header-title">{chat.display_name}</div>
      </header>

      {loadingRec ? (
        <p className="loading">Generating suggestion…</p>
      ) : recommendation ? (
        <div className="chat-context-rec">
          <h3>Ghostbusters suggestion</h3>
          <p>{recommendation.suggested_response}</p>
        </div>
      ) : null}

      {loadingMessages ? (
        <p className="loading">Loading messages…</p>
      ) : (
        <div className="messages-thread">
          {messages.map((msg) => (
            <div
              key={msg.row_id}
              className={`message-bubble ${msg.is_from_me ? "from-me" : "from-them"}`}
            >
              {msg.text}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function App() {
  const [view, setView] = useState<View>({ kind: "list" });
  const [chats, setChats] = useState<Chat[]>([]);
  const [priorities, setPriorities] = useState<Priority[]>([]);
  const [messages, setMessages] = useState<Message[]>([]);
  const [chatRecommendation, setChatRecommendation] = useState<Priority | null>(null);
  const [loadingChats, setLoadingChats] = useState(true);
  const [loadingPriorities, setLoadingPriorities] = useState(true);
  const [loadingMessages, setLoadingMessages] = useState(false);
  const [loadingRec, setLoadingRec] = useState(false);
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

  const openChat = async (chat: Chat) => {
    setView({ kind: "chat", chat });
    setMessages([]);
    setChatRecommendation(null);
    setLoadingMessages(true);
    setLoadingRec(true);

    try {
      const [msgData, recData] = await Promise.all([
        fetchMessages(chat.chat_id),
        fetchPriorities(1, chat.chat_id),
      ]);
      setMessages(msgData);
      setChatRecommendation(recData[0] ?? null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load chat");
    } finally {
      setLoadingMessages(false);
      setLoadingRec(false);
    }
  };

  const goBack = () => {
    setView({ kind: "list" });
    setError(null);
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
          recommendation={chatRecommendation}
          loadingMessages={loadingMessages}
          loadingRec={loadingRec}
          onBack={goBack}
        />
      )}
    </div>
  );
}
