import { useState, useEffect } from "react";
import { NavLink, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { useAuth } from "../../stores/useAuthStore";
import { useConversations, useCreateConversation, useDeleteConversation } from "../../api/chat";
import { useConfirm } from "../../stores/useConfirmStore";
import {
  MessageSquare,
  TrendingUp,
  Plug,
  Database,
  // LineChart,
  Settings,
  Palette,
  User,
  Shield,
  Link as LinkIcon,
  Key,
  ChevronLeft,
  ChevronRight,
  LogOut,
  X,
  Mail,
  Clock
} from "lucide-react";

interface NavDef {
  id: string;
  icon: React.ReactNode;
  label: string;
  to: string;
  divider?: boolean;
}

const NAV: NavDef[] = [
  { id: "chat", icon: <MessageSquare size={16} />, label: "Chat", to: "/chat/history" },
  { id: "insights", icon: <TrendingUp size={16} />, label: "Insights", to: "/insights" },
  { id: "connectors", icon: <Plug size={16} />, label: "Connectors", to: "/connectors" },
  { id: "documents", icon: <Database size={16} />, label: "Data Sources", to: "/data-sources" },
  // { id: "forecasts", icon: <LineChart size={16} />, label: "Forecasts", to: "/forecasts" },
  { id: "settings", icon: <Settings size={16} />, label: "User management", to: "/settings/users" },
  { id: "themes", icon: <Palette size={16} />, label: "Themes", to: "/themes", divider: true },
];

const SUB_NAV = [
  { id: "users", icon: <User size={14} />, label: "Users", to: "/settings/users" },
  { id: "roles", icon: <Shield size={14} />, label: "Roles", to: "/settings/roles" },
  { id: "assign", icon: <LinkIcon size={14} />, label: "Assign roles", to: "/settings/assign" },
  { id: "permissions", icon: <Key size={14} />, label: "Permissions", to: "/settings/permissions" },
];

export function Sidebar() {
  const [collapsed, setCollapsed] = useState(false);
  const [showProfile, setShowProfile] = useState(false);
  const { user, caps, logout } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { data: conversations } = useConversations();
  const createConversation = useCreateConversation();
  const deleteConversation = useDeleteConversation();
  const confirm = useConfirm();

  const onUserMgmtPage = location.pathname.startsWith("/settings");
  const [userMgmtOpen, setUserMgmtOpen] = useState(onUserMgmtPage);

  useEffect(() => {
    setUserMgmtOpen(onUserMgmtPage);
  }, [onUserMgmtPage]);

  // Keep "Chat" highlighted both on the history list (/chat/history) and inside
  // an actual conversation (/chat?c=…), since the nav item now opens history.
  const onChatArea = location.pathname === "/chat" || location.pathname.startsWith("/chat/");
  const activeConversationId = location.pathname === "/chat" ? searchParams.get("c") : null;

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
    // If the open conversation was just deleted, fall back to the default
    // (most recent / freshly created) one by dropping the URL param.
    if (id === activeConversationId) navigate("/chat", { replace: true });
  };

  return (
    <>
      <aside
        className={`dv-side${collapsed ? " dv-collapsed" : ""}`}
        style={{
          background: "#fff",
          borderRight: "1px solid var(--ac-border)",
          padding: "20px 14px",
          display: "flex",
          flexDirection: "column",
          flexShrink: 0,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 24, justifyContent: collapsed ? "center" : "space-between" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10, minWidth: 0 }}>
            <div
              style={{
                width: collapsed ? 34 : 32,
                height: collapsed ? 34 : 32,
                borderRadius: 10,
                background: "var(--ac-logo)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                color: "#fff",
                fontWeight: 800,
                flexShrink: 0,
              }}
            >
              D
            </div>
            {!collapsed && <span style={{ fontWeight: 800, fontSize: 17 }}>Datacon</span>}
          </div>
          {!collapsed && (
            <button title="Collapse menu" onClick={() => setCollapsed(true)} style={{ color: "#9499ad", display: "flex", alignItems: "center" }}>
              <ChevronLeft size={16} />
            </button>
          )}
        </div>
        {collapsed && (
          <button title="Expand menu" onClick={() => setCollapsed(false)} style={{ color: "#9499ad", marginBottom: 12, display: "flex", alignItems: "center" }}>
            <ChevronRight size={16} />
          </button>
        )}

        {!collapsed && (
          <button
            onClick={startNewChat}
            disabled={createConversation.isPending}
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              gap: 8,
              width: "100%",
              background: "var(--ac)",
              color: "#fff",
              fontWeight: 600,
              fontSize: 13.5,
              padding: "10px 12px",
              borderRadius: "var(--radius-md)",
              marginBottom: 16,
              opacity: createConversation.isPending ? 0.6 : 1,
            }}
          >
            + New chat
          </button>
        )}

        {/* One scrollable region for nav + recent conversations, so expanding
            User Management (or a long chat list) scrolls here instead of
            pushing the pinned user card off the bottom. */}
        <div style={{ flex: 1, minHeight: 0, overflowY: "auto", display: "flex", flexDirection: "column" }} className="dv-side-scroll">
        <nav style={{ display: "flex", flexDirection: "column", gap: 3, flexShrink: 0 }}>
          {NAV.map((item) => {
            if (item.id === "settings" && !caps.admin) return null;
            const active = location.pathname === item.to || (item.id === "settings" && onUserMgmtPage) || (item.id === "chat" && onChatArea);
            return (
              <div key={item.id}>
                {item.divider && <div style={{ height: 1, background: "var(--ac-border)", margin: "10px 4px" }} />}
                <NavLink
                  to={item.to}
                  title={item.label}
                  onClick={(e) => {
                    if (item.id === "settings") {
                      if (onUserMgmtPage) {
                        e.preventDefault();
                        setUserMgmtOpen(!userMgmtOpen);
                      }
                    }
                  }}
                  className="dv-navitem"
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 10,
                    padding: "9px 11px",
                    borderRadius: "var(--radius-sm)",
                    fontSize: 13.5,
                    textDecoration: "none",
                    background: active ? "var(--ac-soft)" : "transparent",
                    color: active ? "var(--ac)" : "var(--ac-muted)",
                    fontWeight: active ? 600 : 500,
                  }}
                >
                  <span style={{ display: "flex", alignItems: "center" }}>{item.icon}</span>
                  {!collapsed && <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{item.label}</span>}
                  {collapsed && <span className="dv-tip">{item.label}</span>}
                </NavLink>
                {item.id === "settings" && caps.admin && userMgmtOpen && (
                  <div className="dv-sub" style={{ display: "flex", flexDirection: "column", gap: 2, marginTop: 3, marginBottom: 3 }}>
                    {SUB_NAV.map((s) => (
                      <NavLink
                        key={s.id}
                        to={s.to}
                        title={s.label}
                        className="dv-navitem"
                        style={({ isActive }) => ({
                          display: "flex",
                          alignItems: "center",
                          gap: 9,
                          padding: "7px 10px",
                          borderRadius: "var(--radius-sm)",
                          fontSize: 12.5,
                          textDecoration: "none",
                          background: isActive ? "var(--ac-soft)" : "transparent",
                          color: isActive ? "var(--ac)" : "var(--ac-muted)",
                          fontWeight: isActive ? 600 : 500,
                        })}
                      >
                        <span>{s.icon}</span>
                        {!collapsed && <span>{s.label}</span>}
                        {collapsed && <span className="dv-tip">{s.label}</span>}
                      </NavLink>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </nav>
        {!collapsed && (
          <div style={{ marginTop: 16 }}>
            <div style={{ font: "600 9.5px 'IBM Plex Mono',monospace", letterSpacing: ".14em", color: "var(--ac-muted)", marginBottom: 6, padding: "0 4px" }}>
              RECENT CONVERSATIONS
            </div>
            <div>
              {conversations?.map((c) => {
                const active = c.id === activeConversationId;
                return (
                  <div
                    key={c.id}
                    onClick={() => navigate(`/chat?c=${c.id}`)}
                    style={{
                      position: "relative",
                      cursor: "pointer",
                      borderRadius: "var(--radius-sm)",
                      padding: "8px 28px 8px 8px",
                      marginBottom: 2,
                      background: active ? "var(--ac-soft)" : "transparent",
                    }}
                  >
                    <div
                      style={{
                        fontSize: 13,
                        fontWeight: active ? 700 : 500,
                        color: active ? "var(--ac)" : "var(--ac-fg)",
                        lineHeight: 1.35,
                        display: "-webkit-box",
                        WebkitLineClamp: 2,
                        WebkitBoxOrient: "vertical",
                        overflow: "hidden",
                      }}
                    >
                      {c.title}
                    </div>
                    <button
                      onClick={(e) => removeConversation(c.id, e)}
                      title="Delete conversation"
                      style={{
                        position: "absolute",
                        top: 7,
                        right: 4,
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        color: "var(--ac-muted)",
                        padding: 4,
                        borderRadius: "var(--radius-sm)",
                        lineHeight: 1
                      }}
                    >
                      <X size={12} />
                    </button>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>

      <div style={{ padding: "16px 14px", borderTop: "1px solid var(--ac-border)", display: "flex", flexDirection: "column", gap: 10, flexShrink: 0 }}>
        {user && !collapsed && (
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 4 }}>
            <Avatar grad={user.avatarGrad} initials={user.initials} size={36} />
            <div style={{ minWidth: 0 }}>
              <div style={{ fontSize: 12.5, fontWeight: 700, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{user.name}</div>
              <div style={{ fontSize: 10.5, color: "var(--ac-muted)" }}>
                {user.roleName} · {user.title}
              </div>
            </div>
          </div>
        )}
        {collapsed && user && (
          <div style={{ display: "flex", justifyContent: "center", marginBottom: 8 }}>
            <Avatar grad={user.avatarGrad} initials={user.initials} size={30} />
          </div>
        )}
        <div style={{ display: "flex", gap: 6, justifyContent: collapsed ? "center" : "stretch" }}>
          <button
            title="Profile"
            onClick={() => setShowProfile(true)}
            className="dv-navitem"
            style={{
              flex: collapsed ? undefined : 1,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              gap: 6,
              padding: "7px 0",
              borderRadius: "var(--radius-sm)",
              fontSize: 12,
              color: "var(--ac-fg)",
              background: "var(--ac-bg-muted)",
              border: "1px solid var(--ac-border)",
            }}
          >
            <User size={14} />
            {!collapsed && " Profile"}
            {collapsed && <span className="dv-tip">Profile</span>}
          </button>
          <button
            title="Sign out"
            onClick={() => logout()}
            className="dv-navitem"
            style={{
              flex: collapsed ? undefined : 1,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              gap: 6,
              padding: "7px 0",
              borderRadius: "var(--radius-sm)",
              fontSize: 12,
              color: "#c0405a",
              background: "var(--ac-bg-muted)",
              border: "1px solid var(--ac-border)",
            }}
          >
            <LogOut size={14} />
            {!collapsed && " Sign out"}
            {collapsed && <span className="dv-tip">Sign out</span>}
          </button>
        </div>
      </div>
      </aside>
      {showProfile && user && <ProfileModal onClose={() => setShowProfile(false)} onSignOut={() => { setShowProfile(false); logout(); navigate("/"); }} />}
    </>
  );
}

export function Avatar({ grad, initials, size, ring }: { grad: string; initials: string; size: number; ring?: boolean }) {
  return (
    <div
      style={{
        width: size,
        height: size,
        borderRadius: "50%",
        background: grad,
        color: "#fff",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        fontWeight: 700,
        fontSize: size * 0.4,
        flexShrink: 0,
        boxShadow: ring ? "0 0 0 2px var(--ac)" : "none",
      }}
    >
      {initials}
    </div>
  );
}

function ProfileModal({ onClose, onSignOut }: { onClose: () => void; onSignOut: () => void }) {
  const { user } = useAuth();
  if (!user) return null;
  return (
    <div onClick={onClose} style={{ position: "fixed", inset: 0, background: "rgba(26,29,41,.5)", backdropFilter: "blur(3px)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 60 }}>
      <div onClick={(e) => e.stopPropagation()} className="dvfu" style={{ width: 440, maxWidth: "92vw", background: "#fff", borderRadius: 20, overflow: "hidden", boxShadow: "0 30px 70px -20px rgba(26,29,41,.5)" }}>
        <div style={{ height: 96, background: "linear-gradient(135deg,#221c46,#3a2f73 55%,var(--ac))", position: "relative" }}>
          <button onClick={onClose} style={{ position: "absolute", top: 12, right: 12, width: 28, height: 28, borderRadius: "50%", background: "rgba(255,255,255,.18)", color: "#fff", display: "flex", alignItems: "center", justifyContent: "center" }}>
            <X size={16} />
          </button>
        </div>
        <div style={{ padding: "0 24px 24px", marginTop: -38 }}>
          <Avatar grad={user.avatarGrad} initials={user.initials} size={76} />
          <div style={{ fontSize: 20, fontWeight: 800, marginTop: 10 }}>{user.name}</div>
          <div style={{ fontSize: 13, color: "#71768a", marginBottom: 16 }}>{user.title}</div>
          <div style={{ border: "1px solid #e9eaf2", borderRadius: 12, overflow: "hidden" }}>
            <InfoRow icon={<Mail size={16} />} label="EMAIL" value={user.email} shaded />
            <InfoRow icon={<Shield size={16} />} label="ROLE & ACCESS" value={`${user.roleName} · ${user.permissions.length} permissions`} />
            <InfoRow icon={<Clock size={16} />} label="LAST ACTIVE" value="Just now · This session" shaded />
          </div>
          <div style={{ display: "flex", gap: 10, marginTop: 20 }}>
            <button onClick={onClose} style={{ flex: 1, padding: "10px 0", borderRadius: 10, border: "1px solid #e2e4ee", fontWeight: 700, fontSize: 13 }}>
              Close
            </button>
            <button onClick={onSignOut} style={{ flex: 1, padding: "10px 0", borderRadius: 10, border: "1px solid #e8a9b4", color: "#c0405a", fontWeight: 700, fontSize: 13, display: "flex", alignItems: "center", justifyContent: "center", gap: 6 }}>
              <LogOut size={14} /> Sign out
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function InfoRow({ icon, label, value, shaded }: { icon: React.ReactNode; label: string; value: string; shaded?: boolean }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "11px 14px", background: shaded ? "#fafbfe" : "#fff" }}>
      <span style={{ display: "flex", alignItems: "center", color: "var(--ac-muted)" }}>{icon}</span>
      <div style={{ flex: 1 }}>
        <div style={{ font: "600 9.5px 'IBM Plex Mono',monospace", letterSpacing: ".1em", color: "#a3a8bd" }}>{label}</div>
        <div style={{ fontSize: 13, fontWeight: 600 }}>{value}</div>
      </div>
    </div>
  );
}
