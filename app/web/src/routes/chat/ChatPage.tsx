import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { AVAILABLE_LLM_MODELS, CHAT_SUGGESTIONS, INTENT_META, type ChatIntent, type Citation } from "@datacon/shared-types";
import { useChatMessages, useFeedback, streamChat } from "../../api/chat";
import { useToast } from "../../stores/useToastStore";
import { AgentVisualization } from "./AgentVisualization";
import type { ChatMessage, ChatPayload } from "../../lib/types";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../../components/ui/select";
import {
  Sparkles,
  ArrowUp,
  ThumbsUp,
  ThumbsDown,
  AlertCircle,
  FileText,
  Compass,
  LineChart,
  Play
} from "lucide-react";

let localIdSeq = 1;
const STORAGE_MODEL = "datacon:llmModel";

const INTENT_ICON: Record<ChatIntent, typeof FileText> = {
  descriptive: FileText,
  diagnostic: Compass,
  predictive: LineChart,
  prescriptive: Play,
};

const CONFIDENCE_LABEL = { high: "High confidence", medium: "Medium confidence", low: "Low confidence" } as const;
const CONFIDENCE_COLOR = { high: "#0f8a5c", medium: "#a3730c", low: "#7a7f8a" } as const;

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
  const [model, setModel] = useState<string>(() => localStorage.getItem(STORAGE_MODEL) || AVAILABLE_LLM_MODELS[0].id);
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const sendingRef = useRef(false);
  const sentPending = useRef(false);
  const [openCitation, setOpenCitation] = useState<Citation | null>(null);

  useEffect(() => {
    // Mirror server history into local state whenever it (re)loads — except
    // mid-stream, when local streaming placeholders are ahead of the server.
    if (!history || sendingRef.current) return;
    setMessages(history.messages);
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
        addToast({ icon: <AlertCircle size={16} />, accent: "#e2603f", title: "Chat failed", desc: message });
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
        <div style={{ padding: "18px 28px", borderBottom: "1px solid var(--ac-border)", background: "#fff", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <div>
            <div style={{ fontSize: 16, fontWeight: 800 }}>Multi-agent chat</div>
            <div style={{ fontSize: 11.5, color: "var(--ac-muted)" }}>Plain-English questions, routed automatically</div>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
            <div style={{ display: "flex", gap: 6 }}>
              {(Object.keys(INTENT_META) as ChatIntent[]).map((k) => (
                <span key={k} style={{ font: "600 10px 'IBM Plex Mono',monospace", padding: "4px 9px", borderRadius: "var(--radius-sm)", color: INTENT_META[k].color, background: INTENT_META[k].bg, textTransform: "capitalize" }}>
                  {k}
                </span>
              ))}
            </div>
            <Select value={model} onValueChange={setModel}>
              <SelectTrigger title="LLM model for this chat">
                <SelectValue placeholder="Select model" />
              </SelectTrigger>
              <SelectContent>
                {AVAILABLE_LLM_MODELS.map((m) => (
                  <SelectItem key={m.id} value={m.id}>
                    {m.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>

        <div ref={scrollRef} style={{ flex: 1, overflowY: "auto", background: "linear-gradient(180deg,#f7f8fc,var(--ac-bg))", padding: "24px 0" }}>
          <div style={{ maxWidth: 760, margin: "0 auto", padding: "0 24px" }}>
            {messages.length === 0 && (
              <div style={{ textAlign: "center", marginTop: 40 }}>
                <div style={{ width: 48, height: 48, borderRadius: "var(--radius-lg)", background: "var(--ac)", display: "flex", alignItems: "center", justifyContent: "center", color: "#fff", margin: "0 auto 16px" }}>
                  <Sparkles size={24} />
                </div>
                <div style={{ fontSize: 19, fontWeight: 800, marginBottom: 6 }}>Ask Datacon anything</div>
                <div style={{ fontSize: 13, color: "var(--ac-muted)", marginBottom: 24 }}>Try one of these — each routes to a different agent.</div>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, textAlign: "left" }}>
                  {CHAT_SUGGESTIONS.map((s) => (
                    <button
                      key={s.intent}
                      onClick={() => send(s.question)}
                      style={{ background: "#fff", border: "1px solid var(--ac-border)", borderRadius: "var(--radius-lg)", padding: 18, textAlign: "left" }}
                    >
                      <div style={{ display: "flex", alignItems: "center", gap: 6, font: "600 9.5px 'IBM Plex Mono',monospace", color: INTENT_META[s.intent].color, marginBottom: 6, textTransform: "uppercase" }}>
                        {s.intent === "descriptive" && <FileText size={11} />}
                        {s.intent === "diagnostic" && <Compass size={11} />}
                        {s.intent === "predictive" && <LineChart size={11} />}
                        {s.intent === "prescriptive" && <Play size={11} />}
                        <span>{s.intent}</span>
                      </div>
                      <div style={{ fontSize: 13.5, color: "var(--ac-fg)", lineHeight: 1.4 }}>{s.question}</div>
                    </button>
                  ))}
                </div>
              </div>
            )}

            {messages.map((m) =>
              m.role === "user" ? (
                <div key={m.id} style={{ display: "flex", justifyContent: "flex-end", marginBottom: 16 }}>
                  <div style={{ maxWidth: "74%", background: "var(--ac)", color: "#fff", padding: "12px 18px", borderRadius: "12px 12px 0 12px", fontSize: 14, lineHeight: 1.5 }}>{m.text}</div>
                </div>
              ) : (
                <div key={m.id} style={{ marginBottom: 20 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
                    <div style={{ width: 24, height: 24, borderRadius: "var(--radius-sm)", background: "var(--ac)", color: "#fff", display: "flex", alignItems: "center", justifyContent: "center" }}>
                      <Sparkles size={13} />
                    </div>
                    <span style={{ fontSize: 12.5, fontWeight: 700 }}>Datacon</span>
                    {m.intent && (
                      <span style={{ display: "inline-flex", alignItems: "center", gap: 4, font: "600 9.5px 'IBM Plex Mono',monospace", color: INTENT_META[m.intent].color, background: INTENT_META[m.intent].bg, padding: "2px 8px", borderRadius: 20 }}>
                        {(() => {
                          const Icon = INTENT_ICON[m.intent];
                          return <Icon size={10} />;
                        })()}
                        {INTENT_META[m.intent].label}
                      </span>
                    )}
                    {!m.streaming && m.payload && (
                      <span style={{ marginLeft: "auto", fontSize: 11, fontWeight: 700, color: CONFIDENCE_COLOR[m.payload.confidence] }}>
                        {CONFIDENCE_LABEL[m.payload.confidence]}
                      </span>
                    )}
                  </div>
                  <div style={{ background: "#fff", border: "1px solid var(--ac-border)", borderRadius: "var(--radius-lg)", padding: 20 }}>
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
                    {!m.streaming && <AgentVisualization message={m} onOpenCitation={setOpenCitation} />}
                    {!m.streaming && m.text && (
                      <div style={{ display: "flex", alignItems: "center", gap: 12, marginTop: 12, paddingTop: 10, borderTop: "1px solid var(--ac-border)" }}>
                        <button
                          onClick={() => vote(m.id, 1)}
                          style={{ display: "inline-flex", alignItems: "center", gap: 4, fontSize: 11.5, fontWeight: 700, padding: "4px 9px", borderRadius: "var(--radius-sm)", color: m.vote === 1 ? "#0f8a5c" : "var(--ac-muted)", background: m.vote === 1 ? "#e6f7ef" : "transparent" }}
                        >
                          <ThumbsUp size={12} /> Helpful
                        </button>
                        <button
                          onClick={() => vote(m.id, -1)}
                          style={{ display: "inline-flex", alignItems: "center", gap: 4, fontSize: 11.5, fontWeight: 700, padding: "4px 9px", borderRadius: "var(--radius-sm)", color: m.vote === -1 ? "#c0392b" : "var(--ac-muted)", background: m.vote === -1 ? "#fdeee9" : "transparent" }}
                        >
                          <ThumbsDown size={12} />
                        </button>
                        <span style={{ marginLeft: "auto", fontSize: 11, color: "var(--ac-muted)" }}>
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

        <div style={{ borderTop: "1px solid var(--ac-border)", background: "#fff", padding: "16px 24px" }}>
          <div style={{ maxWidth: 760, margin: "0 auto" }}>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                send(draft);
              }}
              style={{ display: "flex", alignItems: "center", gap: 10, border: "1px solid var(--ac-border)", borderRadius: "var(--radius-md)", padding: "6px 6px 6px 14px" }}
            >
              <input
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                placeholder="Ask about revenue, churn, anomalies, forecasts…"
                style={{ flex: 1, border: "none", fontSize: 13.5, outline: "none", color: "var(--ac-fg)" }}
              />
              <button
                type="submit"
                disabled={sending || !draft.trim()}
                style={{ display: "inline-flex", alignItems: "center", gap: 6, background: "var(--ac)", color: "#fff", fontWeight: 600, fontSize: 13.5, padding: "8px 14px", borderRadius: "var(--radius-sm)", opacity: sending || !draft.trim() ? 0.6 : 1 }}
              >
                Ask <ArrowUp size={14} />
              </button>
            </form>
            <div style={{ textAlign: "center", font: "500 10px 'IBM Plex Mono',monospace", color: "var(--ac-muted)", marginTop: 8 }}>
              Answers stream token-by-token · first token in &lt;1s
            </div>
          </div>
        </div>

        {openCitation && (
          <div
            onClick={() => setOpenCitation(null)}
            style={{ position: "fixed", inset: 0, zIndex: 40, background: "rgba(0,0,0,0.3)" }}
          >
            <div
              onClick={(e) => e.stopPropagation()}
              style={{
                position: "absolute",
                right: 0,
                top: 0,
                height: "100%",
                width: "min(480px, 100%)",
                background: "#fff",
                borderLeft: "1px solid var(--ac-border)",
                padding: 24,
                overflowY: "auto",
              }}
            >
              <div style={{ font: "600 10px 'IBM Plex Mono',monospace", letterSpacing: ".1em", color: "var(--ac-muted)" }}>SOURCE CITATION</div>
              <div style={{ fontSize: 19, fontWeight: 800, marginTop: 8 }}>{openCitation.documentTitle}</div>
              <div style={{ font: "500 11px 'IBM Plex Mono',monospace", color: "var(--ac-muted)", marginTop: 4 }}>
                {openCitation.filename} · chunk {openCitation.chunkIndex}
              </div>
              <div style={{ fontSize: 13, lineHeight: 1.6, color: "var(--ac-fg)", marginTop: 16, background: "var(--ac-bg-muted)", border: "1px solid var(--ac-border)", borderRadius: "var(--radius-sm)", padding: 14, whiteSpace: "pre-wrap" }}>
                {openCitation.snippet}
              </div>
              <button
                onClick={() => setOpenCitation(null)}
                style={{ marginTop: 20, padding: "8px 14px", borderRadius: "var(--radius-sm)", background: "var(--ac-bg-muted)", border: "1px solid var(--ac-border)", fontSize: 12.5, fontWeight: 600 }}
              >
                Close
              </button>
            </div>
          </div>
        )}
    </div>
  );
}
