export interface Priority {
  rank: number;
  contact_name: string;
  contact_handle: string;
  chat_id: string;
  chat_guid: string;
  last_message_preview: string;
  last_message_at: string;
  reply_waiting_at?: string | null;
  suggested_response: string;
  severity: "low" | "medium" | "high" | "critical";
  importance_score: number;
}

export interface Chat {
  chat_id: string;
  chat_guid: string;
  display_name: string;
  contact_handle: string;
  last_message: string;
  last_message_at: string;
  is_from_me: boolean;
  is_group?: boolean;
  needs_reply?: boolean;
  reply_waiting_at?: string | null;
}

export interface Message {
  row_id: number;
  chat_id: string;
  chat_guid: string;
  contact_handle: string;
  contact_name: string | null;
  text: string;
  is_from_me: boolean;
  timestamp: string;
  is_read: boolean;
}

export interface HealthStatus {
  status: string;
  imessage_available: boolean;
  imessage_db_path: string;
  hydradb_configured: boolean;
}

const API_BASE = import.meta.env.VITE_API_URL ?? "";

export async function fetchPriorities(limit = 3, chatId?: string): Promise<Priority[]> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (chatId) params.set("chat_id", chatId);
  const res = await fetch(`${API_BASE}/api/priorities?${params}`);
  if (!res.ok) throw new Error(`Failed to load priorities (${res.status})`);
  return res.json();
}

export async function fetchChats(limit = 20): Promise<Chat[]> {
  const res = await fetch(`${API_BASE}/api/chats?limit=${limit}`);
  if (!res.ok) throw new Error(`Failed to load chats (${res.status})`);
  return res.json();
}

export async function fetchMessages(chatId: string, limit = 50): Promise<Message[]> {
  const res = await fetch(`${API_BASE}/api/chats/${chatId}/messages?limit=${limit}`);
  if (!res.ok) throw new Error(`Failed to load messages (${res.status})`);
  return res.json();
}

export async function fetchHealth(): Promise<HealthStatus> {
  const res = await fetch(`${API_BASE}/api/health`);
  if (!res.ok) throw new Error(`Health check failed (${res.status})`);
  return res.json();
}

export async function fetchReplySuggestions(chatId: string, limit = 3): Promise<string[]> {
  const res = await fetch(`${API_BASE}/api/chats/${chatId}/suggestions?limit=${limit}`);
  if (!res.ok) throw new Error(`Failed to load suggestions (${res.status})`);
  const data: { suggestions: string[] } = await res.json();
  return data.suggestions;
}

export async function sendMessage(chatId: string, text: string): Promise<Message> {
  const res = await fetch(`${API_BASE}/api/chats/${chatId}/messages`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
  if (!res.ok) throw new Error(`Failed to send message (${res.status})`);
  return res.json();
}

export async function resetDatabase(): Promise<{ success: boolean; detail: string }> {
  const res = await fetch(`${API_BASE}/api/reset`, { method: "POST" });
  if (!res.ok) throw new Error(`Failed to reset database (${res.status})`);
  return res.json();
}

export async function syncMessages(): Promise<{ success: boolean; detail: string }> {
  const res = await fetch(`${API_BASE}/api/sync`, { method: "POST" });
  return res.json();
}

export function initials(name: string): string {
  const parts = name.replace(/[^a-zA-Z0-9\s]/g, " ").trim().split(/\s+/);
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
  if (parts.length === 1 && parts[0].length >= 2) return parts[0].slice(0, 2).toUpperCase();
  return name.slice(0, 2).toUpperCase() || "?";
}

export function formatReplyWait(iso: string): string {
  const date = new Date(iso);
  const seconds = Math.max(0, (Date.now() - date.getTime()) / 1000);
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return minutes <= 1 ? "now" : `${minutes}m`;
  const hours = Math.floor(seconds / 3600);
  if (hours < 24) return `${hours}h`;
  const days = Math.floor(seconds / 86400);
  if (days < 7) return `${days}d`;
  return `${Math.floor(days / 7)}w`;
}

export function chatInboxTimestamp(chat: Chat): string {
  if (chat.needs_reply && chat.reply_waiting_at) {
    return formatReplyWait(chat.reply_waiting_at);
  }
  return formatTime(chat.last_message_at);
}

export function formatTime(iso: string): string {
  const date = new Date(iso);
  const now = new Date();
  const sameDay =
    date.getDate() === now.getDate() &&
    date.getMonth() === now.getMonth() &&
    date.getFullYear() === now.getFullYear();

  if (sameDay) {
    return date.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  }
  const diffDays = Math.floor((now.getTime() - date.getTime()) / (1000 * 60 * 60 * 24));
  if (diffDays === 1) return "Yesterday";
  if (diffDays < 7) return date.toLocaleDateString([], { weekday: "short" });
  return date.toLocaleDateString([], { month: "short", day: "numeric" });
}

export function severityLabel(severity: Priority["severity"]): string {
  switch (severity) {
    case "critical":
      return "Urgent";
    case "high":
      return "High priority";
    case "medium":
      return "Medium";
    default:
      return "Low";
  }
}
