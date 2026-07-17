import { useToastStore } from "../../stores/useToastStore";

export function ToastHost() {
  const toasts = useToastStore((state) => state.toasts);
  const dismiss = useToastStore((state) => state.dismiss);

  if (toasts.length === 0) return null;
  return (
    <div style={{ position: "fixed", right: 22, bottom: 22, width: 320, display: "flex", flexDirection: "column", gap: 11, zIndex: 90 }}>
      {toasts.map((t) => (
        <div
          key={t.id}
          className="dvfu"
          style={{
            background: "#fff",
            borderRadius: 13,
            borderLeft: `3px solid ${t.accent}`,
            boxShadow: "0 2px 6px rgba(28,30,50,.05),0 16px 36px -30px rgba(28,30,50,.4)",
            padding: "12px 14px",
            display: "flex",
            gap: 10,
            alignItems: "flex-start",
            animation: "dvtoast .3s cubic-bezier(.2,.7,.3,1) both",
          }}
        >
          <div style={{ fontSize: 16, lineHeight: 1 }}>{t.icon}</div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: 13, fontWeight: 700, color: "#1a1d29" }}>{t.title}</div>
            <div style={{ fontSize: 11.5, color: "#71768a", marginTop: 2 }}>{t.desc}</div>
          </div>
          <button onClick={() => dismiss(t.id)} style={{ color: "#b0b4c6", fontSize: 12, padding: 2 }}>
            ✕
          </button>
        </div>
      ))}
    </div>
  );
}
