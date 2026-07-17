import type { ReactNode } from "react";
import { useAuth } from "../../stores/useAuthStore";

export function RequireAdmin({ children }: { children: ReactNode }) {
  const { caps } = useAuth();
  if (!caps.admin) {
    return (
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", height: "60vh", textAlign: "center", padding: 24 }}>
        <div style={{ fontSize: 40, marginBottom: 12 }}>🔒</div>
        <div style={{ fontSize: 17, fontWeight: 800, marginBottom: 6 }}>Admin access required</div>
        <div style={{ fontSize: 13, color: "#71768a", maxWidth: 360 }}>
          User, role and permission management is limited to admins. Switch to Tom (Admin) in the sidebar to manage access.
        </div>
      </div>
    );
  }
  return <>{children}</>;
}
