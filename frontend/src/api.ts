export interface Priority {
  rank: number;
  contact_name: string;
  contact_handle: string;
  chat_id: string;
  chat_guid: string;
  last_message_preview: string;
  last_message_at: string;
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
