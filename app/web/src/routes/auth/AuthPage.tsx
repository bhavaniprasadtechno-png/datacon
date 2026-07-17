import { Fragment, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../../stores/useAuthStore";
import { usePersonas } from "../../api/auth";
import { apiErrorMessage } from "../../api/client";
import { Avatar } from "../../components/shell/Sidebar";

const PIPELINE = [
  { label: "Descriptive", color: "#2bb8c4" },
  { label: "Diagnostic", color: "#8c6eff" },
  { label: "Predictive", color: "#5b8def" },
  { label: "Prescriptive", color: "#f2a65a" },
];

export function AuthPage() {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [name, setName] = useState("Jordan Lee");
  const [email, setEmail] = useState("tom@acme.com");
  const [password, setPassword] = useState("Datacon123!");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const brandRef = useRef<HTMLDivElement>(null);
  const { login, register, quickLogin, isAuthenticated } = useAuth();
  const { data: personas } = usePersonas();
  const navigate = useNavigate();

  useEffect(() => {
    if (isAuthenticated) navigate("/chat", { replace: true });
  }, [isAuthenticated, navigate]);

  useEffect(() => {
    function onMove(e: PointerEvent) {
      const el = brandRef.current;
      if (!el) return;
      const rect = el.getBoundingClientRect();
      const mx = Math.max(-0.5, Math.min(0.5, (e.clientX - rect.left) / rect.width - 0.5));
      const my = Math.max(-0.5, Math.min(0.5, (e.clientY - rect.top) / rect.height - 0.5));
      el.style.setProperty("--mx", String(mx));
      el.style.setProperty("--my", String(my));
    }
    window.addEventListener("pointermove", onMove);
    return () => window.removeEventListener("pointermove", onMove);
  }, []);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      if (mode === "login") await login(email, password);
      else await register(name, email, password);
    } catch (err) {
      setError(apiErrorMessage(err, "Something went wrong. Please try again."));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div style={{ height: "100vh", display: "flex" }}>
      <div
        ref={brandRef}
        style={{
          ["--mx" as any]: 0,
          ["--my" as any]: 0,
          width: "44%",
          minWidth: 380,
          background: "linear-gradient(150deg,#221c46 0%,#3a2f73 45%,var(--ac) 120%)",
          color: "#fff",
          padding: "54px 56px",
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
          position: "relative",
          overflow: "hidden",
        }}
      >
        <div className="dv-plx">
          <div style={{ position: "absolute", width: 520, height: 520, borderRadius: "50%", background: "radial-gradient(circle,rgba(43,184,196,.38),transparent 62%)", right: -180, top: -120, animation: "dvDrift1 15s ease-in-out infinite" }} />
          <div style={{ position: "absolute", width: 340, height: 340, borderRadius: "50%", background: "radial-gradient(circle,rgba(140,110,255,.34),transparent 64%)", left: -140, bottom: -90, animation: "dvDrift2 18s ease-in-out infinite" }} />
          <div style={{ position: "absolute", width: 200, height: 200, borderRadius: "50%", background: "radial-gradient(circle,rgba(255,255,255,.14),transparent 66%)", right: 60, bottom: 120, animation: "dvDrift3 12s ease-in-out infinite" }} />
        </div>
        <div
          className="dv-plx2"
          style={{
            backgroundImage: "linear-gradient(rgba(255,255,255,.05) 1px,transparent 1px),linear-gradient(90deg,rgba(255,255,255,.05) 1px,transparent 1px)",
            backgroundSize: "44px 44px",
            opacity: 0.5,
            maskImage: "radial-gradient(circle at 70% 30%,#000,transparent 70%)",
            WebkitMaskImage: "radial-gradient(circle at 70% 30%,#000,transparent 70%)",
          }}
        />
        <div style={{ position: "relative", display: "flex", alignItems: "center", gap: 12 }}>
          <div style={{ width: 38, height: 38, borderRadius: 11, background: "var(--ac-logo)", display: "flex", alignItems: "center", justifyContent: "center", fontWeight: 800, fontSize: 19 }}>D</div>
          <span style={{ fontWeight: 800, fontSize: 20, letterSpacing: "-.01em" }}>Datacon</span>
        </div>
        <div style={{ position: "relative" }}>
          <div style={{ font: "600 11px 'IBM Plex Mono',monospace", letterSpacing: ".2em", color: "#b6abff", marginBottom: 18 }}>ENTERPRISE ANALYTICS · OS</div>
          <h1 style={{ margin: 0, fontSize: 38, lineHeight: 1.12, fontWeight: 800, letterSpacing: "-.025em", maxWidth: 440 }}>Ask your whole business one question.</h1>
          <p style={{ margin: "20px 0 0", fontSize: 15, lineHeight: 1.6, color: "#d8d3ff", maxWidth: 420 }}>
            Datacon unifies your databases and your documents behind one conversation — routed to descriptive, diagnostic, predictive and prescriptive agents.
          </p>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 30, flexWrap: "wrap" }}>
            {PIPELINE.map((node, i) => (
              <Fragment key={node.label}>
                <div className="dv-node" style={{ animationDelay: `${i * 0.85}s` }}>
                  <span className="dot" style={{ background: node.color }} />
                  {node.label}
                </div>
                {i < PIPELINE.length - 1 && <span className="dv-arrow">→</span>}
              </Fragment>
            ))}
          </div>
        </div>
        <div style={{ position: "relative", display: "flex", alignItems: "center", gap: 10, font: "600 11px 'IBM Plex Mono',monospace", letterSpacing: ".12em", color: "#b6abff" }}>
          <span style={{ width: 8, height: 8, borderRadius: "50%", background: "#2bb8c4", flexShrink: 0, animation: "dvPulseDot 2.1s infinite" }} />
          4 AGENTS ONLINE · ROUTING LIVE
          <div style={{ flex: 1, height: 1, background: "rgba(255,255,255,.1)", position: "relative", overflow: "hidden", borderRadius: 2, maxWidth: 150 }}>
            <div style={{ position: "absolute", top: 0, left: 0, width: "40%", height: "100%", background: "linear-gradient(90deg,transparent,#2bb8c4,transparent)", animation: "dvFlow 2.6s linear infinite" }} />
          </div>
        </div>
      </div>

      <div style={{ flex: 1, background: "#f7f8fc", display: "flex", alignItems: "center", justifyContent: "center" }}>
        <div style={{ width: 392, maxWidth: "90vw" }}>
          <h2 style={{ fontSize: 25, fontWeight: 800, letterSpacing: "-.02em", margin: 0 }}>{mode === "login" ? "Sign in to Datacon" : "Create your account"}</h2>
          <p style={{ fontSize: 13.5, color: "#71768a", margin: "6px 0 22px" }}>
            {mode === "login" ? "Use your work account, or jump straight into a role to explore." : "Set up secure, role-based access for your team."}
          </p>
          <form onSubmit={submit}>
            {mode === "register" && (
              <Field label="Full name">
                <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Jordan Lee" style={inputStyle} />
              </Field>
            )}
            <Field label="Work email">
              <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@company.com" style={inputStyle} />
            </Field>
            <Field label="Password">
              <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} style={inputStyle} />
            </Field>
            {error && <div style={{ color: "#c0392b", fontSize: 12.5, marginBottom: 12 }}>{error}</div>}
            <button
              type="submit"
              disabled={submitting}
              style={{
                width: "100%",
                background: "var(--ac-grad)",
                color: "#fff",
                fontWeight: 700,
                fontSize: 14,
                borderRadius: 12,
                padding: "12px 0",
                boxShadow: "0 8px 20px -8px rgba(109,77,255,.7)",
                opacity: submitting ? 0.7 : 1,
              }}
            >
              {mode === "login" ? "Sign in" : "Create account"}
            </button>
          </form>

          <div style={{ display: "flex", alignItems: "center", gap: 10, margin: "22px 0" }}>
            <div style={{ flex: 1, height: 1, background: "#e9eaf2" }} />
            <span style={{ font: "600 10px 'IBM Plex Mono',monospace", letterSpacing: ".14em", color: "#a3a8bd" }}>OR JUMP IN AS</span>
            <div style={{ flex: 1, height: 1, background: "#e9eaf2" }} />
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {personas?.map((p) => (
              <button
                key={p.id}
                onClick={() => quickLogin(p.id)}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 10,
                  width: "100%",
                  padding: "9px 12px",
                  border: "1px solid #e2e4ee",
                  borderRadius: 12,
                  background: "#fff",
                  textAlign: "left",
                }}
              >
                <Avatar grad={p.avatarGrad} initials={p.initials} size={36} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 13, fontWeight: 700 }}>{p.name}</div>
                  <div style={{ fontSize: 11, color: "#9499ad" }}>{p.title}</div>
                </div>
                <span
                  style={{
                    font: "600 9.5px 'IBM Plex Mono',monospace",
                    padding: "3px 8px",
                    borderRadius: 20,
                    color: p.role.colorHex ?? "#71768a",
                    background: p.role.bgHex ?? "#f0f1f6",
                  }}
                >
                  {p.role.name.toUpperCase()}
                </span>
              </button>
            ))}
          </div>

          <div style={{ fontSize: 12.5, color: "#9499ad", marginTop: 18, textAlign: "center" }}>
            {mode === "login" ? "New to Datacon? " : "Already have an account? "}
            <button onClick={() => setMode(mode === "login" ? "register" : "login")} style={{ color: "var(--ac)", fontWeight: 700 }}>
              {mode === "login" ? "Create one" : "Sign in"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

const inputStyle: React.CSSProperties = {
  width: "100%",
  padding: "11px 13px",
  border: "1px solid #e2e4ee",
  borderRadius: 11,
  fontSize: 13.5,
};

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: 14 }}>
      <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "#5a5f72", marginBottom: 6 }}>{label}</label>
      {children}
    </div>
  );
}
