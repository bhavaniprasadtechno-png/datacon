import { Link, useParams } from "react-router-dom";
import { useOrganizations, useOrgUsers, useSetUserStatus, type OrgUser } from "../../api/platformAdmin";
import { PageHeader } from "../settings/UsersPage";
import { RoleBadge } from "../../components/ui/RoleBadge";
import { StatusBadge } from "../../components/ui/StatusBadge";
import { Button } from "../../components/ui/Button";
import { Avatar } from "../../components/shell/Sidebar";
import { useToast } from "../../stores/useToastStore";
import { useConfirm } from "../../stores/useConfirmStore";
import { apiErrorMessage } from "../../api/client";
import { ListEntrySkeleton } from "../../components/ui/Skeleton";

export function OrgUsersPage() {
  const { orgId } = useParams<{ orgId: string }>();
  const { data: users, isLoading } = useOrgUsers(orgId);
  const { data: orgs } = useOrganizations();
  const org = orgs?.find((o) => o.id === orgId);
  const setUserStatus = useSetUserStatus();
  const { addToast } = useToast();
  const confirm = useConfirm();

  const toggleUserStatus = async (u: OrgUser) => {
    const suspending = u.status === "ACTIVE";
    if (suspending) {
      const ok = await confirm({
        title: `Suspend ${u.name}?`,
        body: "They will be immediately blocked from signing in.",
        label: "Suspend user",
        tone: "danger",
      });
      if (!ok) return;
    }
    try {
      await setUserStatus.mutateAsync({ orgId: orgId!, userId: u.id, status: suspending ? "SUSPENDED" : "ACTIVE" });
      addToast({
        icon: suspending ? "⛔" : "✅",
        accent: suspending ? "#c0405a" : "#0f8a5c",
        title: suspending ? "User suspended" : "User activated",
        desc: u.name,
      });
    } catch (err) {
      addToast({ icon: "⚠️", accent: "#e2603f", title: "Couldn't update user", desc: apiErrorMessage(err) });
    }
  };

  return (
    <div style={{ padding: 32, maxWidth: 1080, margin: "0 auto" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12.5, color: "#9499ad", marginBottom: 14 }}>
        <Link to="/platform-admin/organizations" style={{ color: "#9499ad" }}>
          ← Workspaces
        </Link>
        {org && (
          <>
            <span>/</span>
            <span style={{ color: "var(--ac-fg)", fontWeight: 600 }}>{org.name}</span>
          </>
        )}
      </div>
      <PageHeader
        title={org ? org.name : "Workspace users"}
        sub={`${users?.length ?? 0} ${users?.length === 1 ? "user" : "users"} in this organization`}
      />
      <div style={{ background: "#fff", borderRadius: 16, border: "1px solid #e9eaf2", overflow: "hidden" }}>
        {isLoading ? (
          <>
            <ListEntrySkeleton />
            <ListEntrySkeleton />
            <ListEntrySkeleton />
            <ListEntrySkeleton />
          </>
        ) : (
          users?.map((u) => (
            <div key={u.id} style={{ display: "flex", alignItems: "center", gap: 12, padding: "12px 18px", minHeight: 56, borderBottom: "1px solid #f5f6fb" }}>
              <Avatar grad={u.avatarGrad} initials={u.initials} size={34} />
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 13, fontWeight: 700 }}>{u.name}</div>
                <div style={{ fontSize: 11.5, color: "#9499ad" }}>{u.email}</div>
              </div>
              <StatusBadge status={u.status} />
              <Button
                variant={u.status === "ACTIVE" ? "danger" : "secondary"}
                onClick={() => toggleUserStatus(u)}
                style={{ padding: "4px 10px", fontSize: 11.5, flexShrink: 0 }}
              >
                {u.status === "ACTIVE" ? "Suspend" : "Activate"}
              </Button>
              <RoleBadge name={u.role.name} color={null} bg={null} />
            </div>
          ))
        )}
      </div>
    </div>
  );
}
