import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useConversations, useCreateConversation, useDeleteConversation } from "../../api/chat";
import { useConfirm } from "../../stores/useConfirmStore";

function relativeTime(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime();
  const mins = Math.round(diffMs / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  if (days < 30) return `${days}d ago`;
  return new Date(iso).toLocaleDateString();
}

export function ChatHistoryPage() {
  const navigate = useNavigate();
  const [search, setSearch] = useState("");
  const { data: conversations, isLoading } = useConversations(search);
  const createConversation = useCreateConversation();
  const deleteConversation = useDeleteConversation();
  const confirm = useConfirm();

  const startNewChat = async () => {
    const conversation = await createConversation.mutateAsync();
    navigate(`/chat?c=${conversation.id}`);
  };

  const removeConversation = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    const ok = await confirm({
      title: "Delete conversation",
      body: "Delete this conversation? This can't be undone.",
      label: "Delete",
      tone: "danger",
    });
    if (!ok) return;
    await deleteConversation.mutateAsync(id);
  };

  const searching = search.trim().length > 0;

  return (
    <div style={{ padding: 32, maxWidth: 760, margin: "0 auto" }}>
      <div style={{ font: "600 11px 'IBM Plex Mono',monospace", letterSpacing: ".2em", color: "#9489c4", marginBottom: 8 }}>YOUR CHATS</div>
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: 20, gap: 16 }}>
        <h1 style={{ fontSize: 30, fontWeight: 800, letterSpacing: "-.03em", margin: 0 }}>Chat history</h1>
        <button
          onClick={startNewChat}
          disabled={createConversation.isPending}
          style={{
            flexShrink: 0,
            background: "var(--ac-grad)",
            color: "#fff",
            fontWeight: 700,
            fontSize: 13.5,
            padding: "10px 16px",
            borderRadius: 11,
            opacity: createConversation.isPending ? 0.6 : 1,
          }}
        >
          + New chat
        </button>
      </div>

      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 10,
          border: "1px solid #e2e4ee",
          borderRadius: 12,
          padding: "10px 14px",
          marginBottom: 20,
          background: "#fff",
        }}
      >
        <span style={{ fontSize: 15, color: "#9499ad" }}>🔍</span>
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search your chats by title or what was said…"
          style={{ flex: 1, border: "none", fontSize: 14, outline: "none", background: "transparent" }}
        />
        {searching && (
          <button onClick={() => setSearch("")} title="Clear" style={{ fontSize: 13, color: "#9499ad" }}>
            ✕
          </button>
        )}
      </div>

      {isLoading && <div style={{ padding: 20, color: "#9499ad" }}>Loading…</div>}

      {!isLoading && conversations?.length === 0 && (
        <div style={{ textAlign: "center", padding: "48px 20px", color: "#9499ad" }}>
          {searching ? (
            <>
              <div style={{ fontSize: 15, fontWeight: 700, color: "#71768a", marginBottom: 6 }}>No chats match "{search.trim()}"</div>
              <div style={{ fontSize: 13 }}>Try a different word, or clear the search.</div>
            </>
          ) : (
            <>
              <div style={{ fontSize: 15, fontWeight: 700, color: "#71768a", marginBottom: 6 }}>No conversations yet</div>
              <div style={{ fontSize: 13 }}>Start a new chat to ask about revenue, churn, anomalies and forecasts.</div>
            </>
          )}
        </div>
      )}

      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {conversations?.map((c) => (
          <div
            key={c.id}
            onClick={() => navigate(`/chat?c=${c.id}`)}
            className="dvfu"
            style={{
              position: "relative",
              cursor: "pointer",
              background: "#fff",
              border: "1px solid #e9eaf2",
              borderRadius: 14,
              padding: "14px 44px 14px 16px",
            }}
          >
            <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 12 }}>
              <div style={{ fontSize: 14.5, fontWeight: 700, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{c.title}</div>
              <div style={{ font: "500 11px 'IBM Plex Mono',monospace", color: "#b0b4c6", flexShrink: 0 }}>{relativeTime(c.updatedAt)}</div>
            </div>
            {c.preview && (
              <div style={{ fontSize: 13, color: "#9499ad", marginTop: 4, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {c.preview}
              </div>
            )}
            <button
              onClick={(e) => removeConversation(c.id, e)}
              title="Delete conversation"
              style={{ position: "absolute", top: 12, right: 12, fontSize: 13, color: "#b0b4c6", padding: 6, borderRadius: 8, lineHeight: 1 }}
            >
              🗑
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
