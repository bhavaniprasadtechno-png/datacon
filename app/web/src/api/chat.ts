import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";
import type { ChatMessage, Conversation } from "../lib/types";

export function useConversations() {
  return useQuery({
    queryKey: ["chat-conversations"],
    queryFn: async () => (await api.get<Conversation[]>("/chat/conversations")).data,
  });
}

export function useCreateConversation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async () => (await api.post<Conversation>("/chat/conversations")).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["chat-conversations"] });
      // ["chat-messages", null] means "whatever's the default/most-recent
      // conversation" server-side — creating or deleting a conversation
      // changes what that resolves to. invalidateQueries alone still shows
      // the old cached conversationId first (stale-while-revalidate) before
      // the background refetch lands — and the page's own effect trusts
      // that conversationId to re-set activeConversationId, which reanchors
      // the UI on a conversation that (in the delete case) no longer exists.
      // removeQueries drops the stale entry outright so nothing reads it.
      qc.removeQueries({ queryKey: ["chat-messages", null], exact: true });
    },
  });
}

export function useDeleteConversation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => api.delete(`/chat/conversations/${id}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["chat-conversations"] });
      qc.removeQueries({ queryKey: ["chat-messages", null], exact: true });
    },
  });
}

export function useChatMessages(conversationId: string | null) {
  return useQuery({
    queryKey: ["chat-messages", conversationId],
    queryFn: async () =>
      (await api.get<{ conversationId: string; messages: ChatMessage[] }>("/chat/messages", { params: { conversationId: conversationId ?? undefined } })).data,
    // A 404 (conversation just deleted, e.g. via a stale in-flight request
    // racing the delete mutation) will never succeed on retry.
    retry: false,
  });
}

export function useFeedback() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, vote }: { id: string; vote: -1 | 0 | 1 }) => (await api.patch(`/chat/messages/${id}/feedback`, { vote })).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["chat-messages"] }),
  });
}

interface StreamHandlers {
  onConversation: (conversationId: string) => void;
  onIntent: (intent: string) => void;
  onToken: (text: string) => void;
  onDone: (final: { intent: string; text: string; payload: unknown }) => void;
  onError: (message: string) => void;
}

export async function streamChat(message: string, conversationId: string | null, model: string | null, handlers: StreamHandlers): Promise<void> {
  const res = await fetch("/api/chat/stream", {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, conversationId: conversationId ?? undefined, model: model ?? undefined }),
  });

  if (!res.ok || !res.body) {
    const data = await res.json().catch(() => ({}));
    handlers.onError(data.message ?? "Couldn't reach the chat service.");
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let idx: number;
    while ((idx = buffer.indexOf("\n\n")) >= 0) {
      const frame = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      const eventMatch = frame.match(/^event: (.+)$/m);
      const dataMatch = frame.match(/^data: (.+)$/m);
      if (!eventMatch || !dataMatch) continue;
      const event = eventMatch[1];
      const data = JSON.parse(dataMatch[1]);
      if (event === "conversation") handlers.onConversation(data.conversationId);
      else if (event === "intent") handlers.onIntent(data.intent);
      else if (event === "token") handlers.onToken(data.text);
      else if (event === "done") handlers.onDone(data);
    }
  }
}
