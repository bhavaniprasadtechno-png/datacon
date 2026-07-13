import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { AVAILABLE_LLM_MODELS, CHAT_SUGGESTIONS, INTENT_META, type ChatIntent } from "@datacon/shared-types";
import { useChatMessages, useFeedback, streamChat } from "../../api/chat";
import { useToast } from "../../components/ui/ToastContext";
import { AgentVisualization } from "./AgentVisualization";
import type { ChatMessage, ChatPayload } from "../../lib/types";

let localIdSeq = 1;
const STORAGE_MODEL = "datacon:llmModel";

export function ChatPage() {
  const qc = useQueryClient();
  // The active conversation lives in the URL (?c=...) — the sidebar's
  // "New chat" button and RECENT CONVERSATIONS list drive it by navigating,
  // so they work from any page, not just this one.
  const [searchParams, setSearchParams] = useSearchParams();
  const activeConversationId = searchParams.get("c");
  const { data: history } = useChatMessages(activeConversationId);
  const feedback = useFeedback();
  const { addToast } = useToast();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [activeIntents, setActiveIntents] = useState<ChatIntent[]>([]);
  const [model, setModel] = useState<string>(() => localStorage.getItem(STORAGE_MODEL) || AVAILABLE_LLM_MODELS[0].id);
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const sendingRef = useRef(false);
  const sentPending = useRef(false);

  useEffect(() => {
    // Mirror server history into local state whenever it (re)loads — except
    // mid-stream, when local streaming placeholders are ahead of the server.
    if (!history || sendingRef.current) return;
    setMessages(history.messages);
    // Seed the header indicator from the most recent turn's agents (the
    // agent messages after the last user message), so reopening a chat
    // still shows which agents handled the last question rather than
    // resetting to "none yet".
    const lastUserIdx = history.messages.map((m) => m.role).lastIndexOf("user");
    const lastTurnIntents = history.messages
      .slice(lastUserIdx + 1)
      .filter((m) => m.role === "agent" && m.intent)
      .map((m) => m.intent as ChatIntent);
    setActiveIntents(lastTurnIntents);
    if (!activeConversationId) setSearchParams({ c: history.conversationId }, { replace: true });

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
    if (!trimmed || sendingRef.current) return;
    sendingRef.current = true;
    setSending(true);
    setDraft("");

    const userMsg: ChatMessage = { id: `local-${localIdSeq++}`, role: "user", intent: null, text: trimmed, payload: null, vote: 0 };
    setMessages((prev) => [...prev, userMsg]);

    // One question can fan out to several agents (e.g. "why did X happen and
    // what should we do?" → diagnostic + prescriptive), each streaming into
    // its own bubble. Ids assigned per intent when the agents frame arrives.
    const agentIds = new Map<string, string>();

    await streamChat(trimmed, activeConversationId, model, {
      onConversation: (conversationId) => {
        if (conversationId !== activeConversationId) setSearchParams({ c: conversationId }, { replace: true });
      },
      onAgents: (intents) => {
        setActiveIntents(intents as ChatIntent[]);
        const placeholders = intents.map((intent) => {
          const id = `local-${localIdSeq++}`;
          agentIds.set(intent, id);
          return { id, role: "agent", intent: intent as ChatIntent, text: "", payload: null, vote: 0, streaming: true } as ChatMessage;
        });
        setMessages((prev) => [...prev, ...placeholders]);
      },
      onAgentDelta: (intent, chunk) => {
        const id = agentIds.get(intent);
        setMessages((prev) => prev.map((m) => (m.id === id ? { ...m, text: m.text + chunk } : m)));
      },
      onAgentDone: (result) => {
        const id = agentIds.get(result.intent);
        setMessages((prev) =>
          prev.map((m) => (m.id === id ? { ...m, text: result.text, payload: result.payload as ChatPayload, streaming: false } : m)),
        );
      },
      onDone: () => {
        sendingRef.current = false;
        setSending(false);
        // Refreshes the sidebar's title (auto-set from the first message),
        // preview snippet, and updatedAt-based ordering.
        qc.invalidateQueries({ queryKey: ["chat-conversations"] });
      },
      onError: (message) => {
        addToast({ icon: "⚠️", accent: "#e2603f", title: "Chat failed", desc: message });
        const pendingIds = new Set(agentIds.values());
        setMessages((prev) => prev.filter((m) => !pendingIds.has(m.id)));
        sendingRef.current = false;
        setSending(false);
      },
    });
  };

  const vote = (id: string, dir: -1 | 1) => {
    const current = messages.find((m) => m.id === id);
    if (!current) return;
    const nextVote = current.vote === dir ? 0 : dir;
    setMessages((prev) => prev.map((m) => (m.id === id ? { ...m, vote: nextVote } : m)));
    if (!id.startsWith("local-")) feedback.mutate({ id, vote: nextVote });
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100vh", minWidth: 0 }}>
        <div style={{ padding: "18px 28px", borderBottom: "1px solid #e9eaf2", background: "#fff", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <div>
            <div style={{ fontSize: 16, fontWeight: 800 }}>Multi-agent chat</div>
            <div style={{ fontSize: 11.5, color: "#9499ad" }}>Plain-English questions, routed automatically</div>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
            <div style={{ display: "flex", gap: 6 }}>
              {(Object.keys(INTENT_META) as ChatIntent[]).map((k) => {
                const isStreaming = messages.some((m) => m.streaming && m.intent === k);
                const isActive = activeIntents.includes(k);
                return (
                  <span
                    key={k}
                    title={isStreaming ? `${INTENT_META[k].label} is responding…` : isActive ? `${INTENT_META[k].label} handled the last question` : `${INTENT_META[k].label} — not used yet`}
                    style={{
                      font: "600 10px 'IBM Plex Mono',monospace",
                      padding: "4px 9px",
                      borderRadius: 7,
                      textTransform: "capitalize",
                      color: isActive || isStreaming ? INTENT_META[k].color : "#b0b4c6",
                      background: isActive || isStreaming ? INTENT_META[k].bg : "#f3f4f9",
                      opacity: isActive || isStreaming ? 1 : 0.6,
                      animation: isStreaming ? "dvblink 1.1s ease-in-out infinite" : undefined,
                      transition: "background .25s, color .25s, opacity .25s",
                    }}
                  >
                    {k}
                  </span>
                );
              })}
            </div>
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
                    {m.intent && INTENT_META[m.intent as ChatIntent] && (
                      <span
                        style={{
                          font: "600 9.5px 'IBM Plex Mono',monospace",
                          color: INTENT_META[m.intent as ChatIntent].color,
                          background: INTENT_META[m.intent as ChatIntent].bg,
                          padding: "2px 8px",
                          borderRadius: 20,
                        }}
                      >
                        {INTENT_META[m.intent as ChatIntent].label}
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
                  flexShrink: 0,
                }}
              >
                {AVAILABLE_LLM_MODELS.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.label}
                  </option>
                ))}
              </select>
              <button
                type="submit"
                disabled={sending || !draft.trim()}
                style={{ background: "var(--ac-grad)", color: "#fff", fontWeight: 700, fontSize: 13, padding: "9px 16px", borderRadius: 10, opacity: sending || !draft.trim() ? 0.6 : 1, flexShrink: 0 }}
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
  );
}
