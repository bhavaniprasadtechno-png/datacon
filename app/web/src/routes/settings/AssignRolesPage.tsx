import { useState } from "react";
import { useAssignRole, useRoles, useUsers } from "../../api/rbac";
import { useToast } from "../../stores/useToastStore";
import { useConfirm } from "../../stores/useConfirmStore";
import { Modal, ModalHeader } from "../../components/ui/Modal";
import { Button } from "../../components/ui/Button";
import { RoleBadge } from "../../components/ui/RoleBadge";
import { Avatar } from "../../components/shell/Sidebar";
import { apiErrorMessage } from "../../api/client";
import { PageHeader, FieldRow } from "./UsersPage";
import type { RbacUser } from "../../lib/types";

export function AssignRolesPage() {
  const { data: users, isLoading } = useUsers();
  const { data: roles } = useRoles();
  const { addToast } = useToast();
  const confirm = useConfirm();
  const assignRole = useAssignRole();
  const [target, setTarget] = useState<RbacUser | null>(null);
  const [roleId, setRoleId] = useState<string>("");

  const openAssign = (u: RbacUser) => {
    setTarget(u);
    setRoleId(u.roleId);
  };

  const save = async () => {
    if (!target) return;
    const role = roles?.find((r) => r.id === roleId);
    const ok = await confirm({
      title: `Assign ${role?.name ?? roleId} to ${target.name}?`,
      body: `Their access will change immediately to match the ${role?.name ?? roleId} permission set.`,
      label: "Assign role",
      tone: "primary",
    });
    if (!ok) return;
    try {
      await assignRole.mutateAsync({ id: target.id, roleId });
      addToast({ icon: "🔑", accent: "var(--ac)", title: "Role assigned", desc: `${target.name} is now ${role?.name ?? roleId}` });
      setTarget(null);
    } catch (err) {
      addToast({ icon: "⚠️", accent: "#e2603f", title: "Couldn't assign role", desc: apiErrorMessage(err) });
    }
  };

  return (
    <div style={{ padding: 32, maxWidth: 1080, margin: "0 auto" }}>
      <PageHeader title="Assign roles" sub="Give each user exactly one role" />

      <div style={{ background: "#fff", borderRadius: 16, border: "1px solid #e9eaf2", overflow: "hidden" }}>
        <div style={{ display: "grid", gridTemplateColumns: "1.6fr 1fr 120px", padding: "12px 18px", fontSize: 10.5, fontWeight: 700, letterSpacing: ".06em", color: "#9499ad", borderBottom: "1px solid #f0f1f6" }}>
          <span>USER</span>
          <span>CURRENT ROLE</span>
          <span>ACTION</span>
        </div>
        {isLoading && <div style={{ padding: 20, color: "#9499ad" }}>Loading…</div>}
        {users?.map((u) => (
          <div key={u.id} style={{ display: "grid", gridTemplateColumns: "1.6fr 1fr 120px", alignItems: "center", padding: "12px 18px", borderBottom: "1px solid #f5f6fb" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <Avatar grad={u.avatarGrad} initials={u.initials} size={32} />
              <div>
                <div style={{ fontSize: 13, fontWeight: 700 }}>{u.name}</div>
                <div style={{ fontSize: 11, color: "#9499ad" }}>{u.email}</div>
              </div>
            </div>
            <div>
              <RoleBadge name={u.role.name} color={u.role.colorHex} bg={u.role.bgHex} />
            </div>
            <button onClick={() => openAssign(u)} style={{ color: "var(--ac)", fontWeight: 700, fontSize: 12.5, textAlign: "left" }}>
              Change role
            </button>
          </div>
        ))}
      </div>

      <Modal open={!!target} onClose={() => setTarget(null)}>
        {target && (
          <>
            <ModalHeader title="Assign role" onClose={() => setTarget(null)} />
            <div style={{ display: "flex", alignItems: "center", gap: 10, background: "#f5f6fb", borderRadius: 11, padding: "9px 11px", marginBottom: 16 }}>
              <Avatar grad={target.avatarGrad} initials={target.initials} size={32} />
              <div>
                <div style={{ fontSize: 13, fontWeight: 700 }}>{target.name}</div>
                <div style={{ fontSize: 11, color: "#9499ad" }}>{target.email}</div>
              </div>
            </div>
            <FieldRow label="SELECT ROLE">
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                {roles?.map((r) => (
                  <button
                    key={r.id}
                    onClick={() => setRoleId(r.id)}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 10,
                      padding: "9px 11px",
                      borderRadius: 10,
                      border: `1px solid ${roleId === r.id ? "var(--ac-ring)" : "#e2e4ee"}`,
                      background: roleId === r.id ? "var(--ac-softer)" : "#fff",
                      textAlign: "left",
                    }}
                  >
                    <span style={{ width: 10, height: 10, borderRadius: "50%", background: r.colorHex ?? "var(--ac)" }} />
                    <div>
                      <div style={{ fontSize: 13, fontWeight: 700 }}>{r.name}</div>
                      <div style={{ fontSize: 11, color: "#9499ad" }}>{r.permissions.length} permissions</div>
                    </div>
                  </button>
                ))}
              </div>
            </FieldRow>
            <div style={{ display: "flex", justifyContent: "flex-end", gap: 10, marginTop: 18 }}>
              <Button variant="secondary" onClick={() => setTarget(null)}>
                Cancel
              </Button>
              <Button variant="primary" onClick={save}>
                Assign role
              </Button>
            </div>
          </>
        )}
      </Modal>
    </div>
  );
}
