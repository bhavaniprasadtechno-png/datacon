import { useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { AVAILABLE_LLM_MODELS, CHAT_SUGGESTIONS, INTENT_META, type ChatIntent } from "@datacon/shared-types";
import { useChatMessages, useConversations, useCreateConversation, useDeleteConversation, useFeedback, streamChat } from "../../api/chat";
import { useToast } from "../../components/ui/ToastContext";
import { AgentVisualization } from "./AgentVisualization";
import type { ChatMessage, ChatPayload } from "../../lib/types";

let localIdSeq = 1;
const STORAGE_MODEL = "datacon:llmModel";

function relativeTime(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime();
  const mins = Math.round(diffMs / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  return `${days}d ago`;
}

export function ChatPage() {
  const qc = useQueryClient();
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null);
  const { data: conversations } = useConversations();
  const { data: history } = useChatMessages(activeConversationId);
  const createConversation = useCreateConversation();
  const deleteConversation = useDeleteConversation();
  const feedback = useFeedback();
  const { addToast } = useToast();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [model, setModel] = useState<string>(() => localStorage.getItem(STORAGE_MODEL) || AVAILABLE_LLM_MODELS[0].id);
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const loadedConversationId = useRef<string | null | undefined>(undefined);
  const sentPending = useRef(false);

  useEffect(() => {
    if (!history || loadedConversationId.current === history.conversationId) return;
    loadedConversationId.current = history.conversationId;
    setMessages(history.messages);
    if (!activeConversationId) setActiveConversationId(history.conversationId);

    if (sentPending.current) return;
    sentPending.current = true;
    const pending = sessionStorage.getItem("datacon:pendingQuestion");
    if (pending) {
      sessionStorage.removeItem("datacon:pendingQuestion");
      send(pending);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [history]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  useEffect(() => {
    localStorage.setItem(STORAGE_MODEL, model);
  }, [model]);

  const send = async (text: string) => {
    const trimmed = text.trim();
    if (!trimmed || sending) return;
    setSending(true);
    setDraft("");

    const userMsg: ChatMessage = { id: `local-${localIdSeq++}`, role: "user", intent: null, text: trimmed, payload: null, vote: 0 };
    const agentId = `local-${localIdSeq++}`;
    const agentMsg: ChatMessage = { id: agentId, role: "agent", intent: null, text: "", payload: null, vote: 0, streaming: true };
    setMessages((prev) => [...prev, userMsg, agentMsg]);

    await streamChat(trimmed, activeConversationId, model, {
      onConversation: (conversationId) => {
        loadedConversationId.current = conversationId;
        setActiveConversationId(conversationId);
      },
      onIntent: (intent) => {
        setMessages((prev) => prev.map((m) => (m.id === agentId ? { ...m, intent: intent as ChatIntent } : m)));
      },
      onToken: (chunk) => {
        setMessages((prev) => prev.map((m) => (m.id === agentId ? { ...m, text: m.text + chunk } : m)));
      },
      onDone: (final) => {
        setMessages((prev) =>
          prev.map((m) => (m.id === agentId ? { ...m, intent: final.intent as ChatIntent, text: final.text, payload: final.payload as ChatPayload, streaming: false } : m)),
        );
        setSending(false);
        // Refreshes the sidebar's title (auto-set from the first message),
        // preview snippet, and updatedAt-based ordering.
        qc.invalidateQueries({ queryKey: ["chat-conversations"] });
      },
      onError: (message) => {
        addToast({ icon: "⚠️", accent: "#e2603f", title: "Chat failed", desc: message });
        setMessages((prev) => prev.filter((m) => m.id !== agentId));
        setSending(false);
      },
    });
  };

  const startNewChat = async () => {
    if (sending) return;
    const conversation = await createConversation.mutateAsync();
    loadedConversationId.current = conversation.id;
    setActiveConversationId(conversation.id);
    setMessages([]);
  };

  const switchConversation = (id: string) => {
    if (id === activeConversationId || sending) return;
    loadedConversationId.current = undefined;
    setActiveConversationId(id);
  };

  const removeConversation = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!window.confirm("Delete this conversation? This can't be undone.")) return;
    await deleteConversation.mutateAsync(id);
    if (id === activeConversationId) {
      loadedConversationId.current = undefined;
      setActiveConversationId(null);
      setMessages([]);
    }
  };

  const vote = (id: string, dir: -1 | 1) => {
    const current = messages.find((m) => m.id === id);
    if (!current) return;
    const nextVote = current.vote === dir ? 0 : dir;
    setMessages((prev) => prev.map((m) => (m.id === id ? { ...m, vote: nextVote } : m)));
    if (!id.startsWith("local-")) feedback.mutate({ id, vote: nextVote });
  };

  return (
    <div style={{ display: "flex", height: "100vh" }}>
      <div style={{ width: 232, flexShrink: 0, borderRight: "1px solid #e9eaf2", background: "#fbfbfd", display: "flex", flexDirection: "column" }}>
        <div style={{ padding: "16px 14px 10px" }}>
          <button
            onClick={startNewChat}
            disabled={createConversation.isPending}
            style={{
              width: "100%",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              gap: 6,
              background: "var(--ac-grad)",
              color: "#fff",
              fontWeight: 700,
              fontSize: 12.5,
              padding: "9px 12px",
              borderRadius: 10,
              opacity: createConversation.isPending ? 0.6 : 1,
            }}
          >
            + New chat
          </button>
        </div>
        <div style={{ flex: 1, overflowY: "auto", padding: "4px 8px 12px" }}>
          {conversations?.map((c) => {
            const active = c.id === activeConversationId;
            return (
              <div
                key={c.id}
                onClick={() => switchConversation(c.id)}
                style={{
                  position: "relative",
                  cursor: "pointer",
                  borderRadius: 10,
                  padding: "9px 10px",
                  marginBottom: 2,
                  background: active ? "#efeaff" : "transparent",
                }}
                className="dv-conv-item"
              >
                <div
                  style={{
                    fontSize: 12.5,
                    fontWeight: active ? 700 : 600,
                    color: active ? "#4a2fc9" : "#1a1d29",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                    paddingRight: 20,
                  }}
                >
                  {c.title}
                </div>
                <div style={{ font: "500 10.5px 'IBM Plex Mono',monospace", color: "#9499ad", marginTop: 2 }}>{relativeTime(c.updatedAt)}</div>
                <button
                  onClick={(e) => removeConversation(c.id, e)}
                  title="Delete conversation"
                  style={{
                    position: "absolute",
                    top: 8,
                    right: 6,
                    fontSize: 12,
                    color: "#b0b4c6",
                    padding: 4,
                    borderRadius: 6,
                    lineHeight: 1,
                  }}
                >
                  ✕
                </button>
              </div>
            );
          })}
        </div>
      </div>

      <div style={{ display: "flex", flexDirection: "column", flex: 1, minWidth: 0 }}>
        <div style={{ padding: "18px 28px", borderBottom: "1px solid #e9eaf2", background: "#fff", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <div>
            <div style={{ fontSize: 16, fontWeight: 800 }}>Multi-agent chat</div>
            <div style={{ fontSize: 11.5, color: "#9499ad" }}>Plain-English questions, routed automatically</div>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
            <div style={{ display: "flex", gap: 6 }}>
              {(Object.keys(INTENT_META) as ChatIntent[]).map((k) => (
                <span key={k} style={{ font: "600 10px 'IBM Plex Mono',monospace", padding: "4px 9px", borderRadius: 7, color: INTENT_META[k].color, background: INTENT_META[k].bg, textTransform: "capitalize" }}>
                  {k}
                </span>
              ))}
            </div>
            <select
              value={model}
              onChange={(e) => setModel(e.target.value)}
              title="LLM model for this chat"
              style={{
                font: "600 11px 'IBM Plex Mono',monospace",
                color: "#5b3fd6",
                background: "#efeaff",
                border: "none",
                borderRadius: 8,
                padding: "6px 8px",
                cursor: "pointer",
              }}
            >
              {AVAILABLE_LLM_MODELS.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.label}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div ref={scrollRef} style={{ flex: 1, overflowY: "auto", background: "linear-gradient(180deg,#f7f8fc,var(--ac-bg))", padding: "24px 0" }}>
          <div style={{ maxWidth: 760, margin: "0 auto", padding: "0 24px" }}>
            {messages.length === 0 && (
              <div style={{ textAlign: "center", marginTop: 40 }}>
                <div style={{ width: 52, height: 52, borderRadius: 16, background: "var(--ac-logo)", display: "flex", alignItems: "center", justifyContent: "center", color: "#fff", fontSize: 22, margin: "0 auto 16px" }}>✦</div>
                <div style={{ fontSize: 19, fontWeight: 800, marginBottom: 6 }}>Ask Datacon anything</div>
                <div style={{ fontSize: 13, color: "#9499ad", marginBottom: 24 }}>Try one of these — each routes to a different agent.</div>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, textAlign: "left" }}>
                  {CHAT_SUGGESTIONS.map((s) => (
                    <button
                      key={s.intent}
                      onClick={() => send(s.question)}
                      style={{ background: "#fff", border: "1px solid #e9eaf2", borderRadius: 14, padding: 14 }}
                    >
                      <div style={{ font: "700 9.5px 'IBM Plex Mono',monospace", color: INTENT_META[s.intent].color, marginBottom: 6, textTransform: "uppercase" }}>{s.intent}</div>
                      <div style={{ fontSize: 13, color: "#1a1d29" }}>{s.question}</div>
                    </button>
                  ))}
                </div>
              </div>
            )}

            {messages.map((m) =>
              m.role === "user" ? (
                <div key={m.id} style={{ display: "flex", justifyContent: "flex-end", marginBottom: 16 }}>
                  <div style={{ maxWidth: "74%", background: "var(--ac-grad)", color: "#fff", padding: "10px 14px", borderRadius: "15px 15px 5px 15px", fontSize: 13.5 }}>{m.text}</div>
                </div>
              ) : (
                <div key={m.id} style={{ marginBottom: 20 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
                    <div style={{ width: 26, height: 26, borderRadius: 8, background: "var(--ac-logo)", color: "#fff", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 12 }}>✦</div>
                    <span style={{ fontSize: 12.5, fontWeight: 700 }}>Datacon</span>
                    {m.intent && (
                      <span style={{ font: "600 9.5px 'IBM Plex Mono',monospace", color: INTENT_META[m.intent].color, background: INTENT_META[m.intent].bg, padding: "2px 8px", borderRadius: 20 }}>
                        {INTENT_META[m.intent].label}
                      </span>
                    )}
                  </div>
                  <div style={{ background: "#fff", border: "1px solid #e9eaf2", borderRadius: "4px 15px 15px 15px", padding: 14 }}>
                    {m.text ? (
                      <div style={{ fontSize: 13.5, lineHeight: 1.55 }}>
                        {m.text}
                        {m.streaming && <span style={{ display: "inline-block", width: 7, height: 14, background: "var(--ac)", marginLeft: 2, animation: "dvblink .9s infinite", verticalAlign: "middle" }} />}
                      </div>
                    ) : (
                      <div style={{ display: "flex", gap: 4 }}>
                        {[0, 1, 2].map((i) => (
                          <span key={i} style={{ width: 6, height: 6, borderRadius: "50%", background: "#c3c7d6", animation: `dvbounce 1.1s ${i * 0.15}s infinite` }} />
                        ))}
                      </div>
                    )}
                    {!m.streaming && <AgentVisualization message={m} />}
                    {!m.streaming && m.text && (
                      <div style={{ display: "flex", alignItems: "center", gap: 12, marginTop: 12, paddingTop: 10, borderTop: "1px solid #f3f4f9" }}>
                        <button
                          onClick={() => vote(m.id, 1)}
                          style={{ fontSize: 11.5, fontWeight: 700, padding: "4px 9px", borderRadius: 7, color: m.vote === 1 ? "#0f8a5c" : "#9499ad", background: m.vote === 1 ? "#e6f7ef" : "transparent" }}
                        >
                          ▲ Helpful
                        </button>
                        <button
                          onClick={() => vote(m.id, -1)}
                          style={{ fontSize: 11.5, fontWeight: 700, padding: "4px 9px", borderRadius: 7, color: m.vote === -1 ? "#c0392b" : "#9499ad", background: m.vote === -1 ? "#fdeee9" : "transparent" }}
                        >
                          ▼
                        </button>
                        <span style={{ marginLeft: "auto", fontSize: 11, color: "#b0b4c6" }}>
                          {m.vote === 1 ? "Thanks — feeds insight accuracy" : m.vote === -1 ? "Noted — we'll improve routing" : "Was this helpful?"}
                        </span>
                      </div>
                    )}
                  </div>
                </div>
              ),
            )}
          </div>
        </div>

        <div style={{ borderTop: "1px solid #e9eaf2", background: "#fff", padding: "14px 24px" }}>
          <div style={{ maxWidth: 760, margin: "0 auto" }}>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                send(draft);
              }}
              style={{ display: "flex", alignItems: "center", gap: 10, border: "1px solid #e2e4ee", borderRadius: 14, padding: "6px 6px 6px 16px" }}
            >
              <input
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                placeholder="Ask about revenue, churn, anomalies, forecasts…"
                style={{ flex: 1, border: "none", fontSize: 13.5, outline: "none" }}
              />
              <button
                type="submit"
                disabled={sending || !draft.trim()}
                style={{ background: "var(--ac-grad)", color: "#fff", fontWeight: 700, fontSize: 13, padding: "9px 16px", borderRadius: 10, opacity: sending || !draft.trim() ? 0.6 : 1 }}
              >
                Ask ✦
              </button>
            </form>
            <div style={{ textAlign: "center", font: "500 10px 'IBM Plex Mono',monospace", color: "#b0b4c6", marginTop: 8 }}>
              Answers stream token-by-token · first token in &lt;1s
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
