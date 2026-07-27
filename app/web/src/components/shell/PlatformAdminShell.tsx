import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../../stores/useAuthStore";
import { Button } from "../shadcn-ui/ui/button";
import { ToastHost } from "../ui/ToastHost";
import { ConfirmHost } from "../ui/ConfirmHost";

const NAV = [
  { id: "dashboard", label: "Dashboard", icon: "📊", to: "/platform-admin/dashboard" },
  { id: "admins", label: "Admin users", icon: "👤", to: "/platform-admin/organizations" },
  { id: "plans", label: "Subscription plans", icon: "💳", to: "/platform-admin/plans" },
  { id: "providers", label: "Providers", icon: "🔌", to: "/platform-admin/providers" },
];

export function PlatformAdminShell() {
  const { user, logout } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const email = user?.kind === "platform_admin" ? user.email : "";

  const handleSignOut = async () => {
    await logout();
    navigate("/");
  };

  return (
    <div className="flex h-screen w-screen overflow-hidden">
      <aside className="flex w-[236px] shrink-0 flex-col bg-[#1a1730] p-3.5 text-white">
        <div className="mb-6 flex items-center gap-2.5">
          <div className="flex size-[34px] shrink-0 items-center justify-center rounded-[10px] bg-gradient-to-br from-[#6d4dff] to-[#2bb8c4] text-base font-extrabold">
            D
          </div>
          <div className="min-w-0">
            <div className="text-[15px] font-extrabold">Datacon</div>
            <div className="font-mono text-[9.5px] font-semibold tracking-[.12em] text-[#8f89c2]">SUPER ADMIN</div>
          </div>
        </div>

        <nav className="flex flex-1 flex-col gap-0.5">
          {NAV.map((item) => {
            const active = location.pathname.startsWith(item.to);
            return (
              <NavLink
                key={item.id}
                to={item.to}
                className={`flex items-center gap-2.5 rounded-[10px] px-2.5 py-2 text-[13.5px] no-underline ${
                  active ? "bg-white/10 font-bold text-white" : "font-medium text-[#b7b2dd]"
                }`}
              >
                <span>{item.icon}</span>
                <span>{item.label}</span>
              </NavLink>
            );
          })}
        </nav>

        <div className="mt-3.5 border-t border-white/10 pt-3.5">
          <div className="mb-2.5 flex items-center gap-2.5">
            <div className="flex size-8 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-[#6d4dff] to-[#8c6eff] text-[13px] font-bold">
              {email.charAt(0).toUpperCase() || "S"}
            </div>
            <div className="min-w-0">
              <div className="truncate text-[12.5px] font-bold">{email}</div>
              <div className="text-[10.5px] text-[#8f89c2]">Platform Admin</div>
            </div>
          </div>
          <Button
            onClick={handleSignOut}
            variant="ghost"
            className="w-full justify-center gap-1.5 bg-white/5 text-[12.5px] font-bold text-[#ff8fa3] hover:bg-white/10 hover:text-[#ff8fa3]"
          >
            ⏻ Sign out
          </Button>
        </div>
      </aside>
      <main className="min-w-0 flex-1 overflow-y-auto bg-[var(--ac-bg)]">
        <Outlet />
      </main>
      <ToastHost />
      <ConfirmHost />
    </div>
  );
}
