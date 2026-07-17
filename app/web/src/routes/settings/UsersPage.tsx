import { useState } from "react";
import { useAuth } from "../../stores/useAuthStore";
import { useCreateUser, useDeleteUser, useRoles, useUpdateUser, useUsers } from "../../api/rbac";
import { useToast } from "../../stores/useToastStore";
import { useConfirm } from "../../stores/useConfirmStore";
import { Modal, ModalHeader } from "../../components/ui/Modal";
import { Button } from "../../components/ui/Button";
import { RoleBadge } from "../../components/ui/RoleBadge";
import { Avatar } from "../../components/shell/Sidebar";
import { apiErrorMessage } from "../../api/client";
import type { RbacUser } from "../../lib/types";

export function UsersPage() {
  const { data: users, isLoading } = useUsers();
  const { data: roles } = useRoles();
  const { user: me } = useAuth();
  const { addToast } = useToast();
  const confirm = useConfirm();
  const createUser = useCreateUser();
  const updateUser = useUpdateUser();
  const deleteUser = useDeleteUser();
  const [editing, setEditing] = useState<RbacUser | "new" | null>(null);

  const remove = async (u: RbacUser) => {
    const ok = await confirm({
      title: `Remove ${u.name}?`,
      body: "They will immediately lose all access to Datacon. This cannot be undone.",
      label: "Remove user",
      tone: "danger",
    });
    if (!ok) return;
    try {
      await deleteUser.mutateAsync(u.id);
      addToast({ icon: "🗑️", accent: "#e2603f", title: "User removed", desc: `${u.name} no longer has access` });
    } catch (err) {
      addToast({ icon: "⚠️", accent: "#e2603f", title: "Couldn't remove user", desc: apiErrorMessage(err) });
    }
  };

  return (
    <div style={{ padding: 32, maxWidth: 1080, margin: "0 auto" }}>
      <PageHeader
        title="Users"
        sub="Create, edit and remove people in this workspace"
        action={<Button variant="primary" onClick={() => setEditing("new")}>+ Create user</Button>}
      />

      <div style={{ background: "#fff", borderRadius: 16, border: "1px solid #e9eaf2", overflow: "hidden" }}>
        <div style={gridHeader}>
          <span>USER</span>
          <span>ROLE</span>
          <span>PERMISSIONS</span>
          <span>ACTIONS</span>
        </div>
        {isLoading && <div style={{ padding: 20, color: "#9499ad" }}>Loading…</div>}
        {users?.map((u) => (
          <div key={u.id} style={gridRow}>
            <div style={{ display: "flex", alignItems: "center", gap: 10, minWidth: 0 }}>
              <Avatar grad={u.avatarGrad} initials={u.initials} size={34} />
              <div style={{ minWidth: 0 }}>
                <div style={{ fontSize: 13, fontWeight: 700 }}>
                  {u.name} {u.id === me?.id && <span style={{ color: "#9499ad", fontWeight: 500 }}>· you</span>}
                </div>
                <div style={{ fontSize: 11.5, color: "#9499ad" }}>{u.email}</div>
              </div>
            </div>
            <div>
              <RoleBadge name={u.role.name} color={u.role.colorHex} bg={u.role.bgHex} />
            </div>
            <div style={{ fontSize: 12.5, color: "#71768a" }}>{u.permissionCount} granted</div>
            <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
              <button onClick={() => setEditing(u)} style={{ color: "var(--ac)", fontWeight: 700, fontSize: 12.5 }}>
                Edit
              </button>
              {u.canDelete && (
                <button onClick={() => remove(u)} title="Delete" style={{ color: "#c0392b" }}>
                  🗑
                </button>
              )}
            </div>
          </div>
        ))}
      </div>

      <Modal open={editing !== null} onClose={() => setEditing(null)}>
        {editing && (
          <UserEditorForm
            user={editing === "new" ? null : editing}
            roles={roles ?? []}
            onClose={() => setEditing(null)}
            onSave={async (dto) => {
              try {
                if (editing === "new") {
                  await createUser.mutateAsync(dto);
                  addToast({ icon: "✅", accent: "#0f8a5c", title: "User created", desc: `${dto.name} added as ${roleName(roles, dto.roleId)}` });
                } else {
                  await updateUser.mutateAsync({ id: editing.id, ...dto });
                  addToast({ icon: "✏️", accent: "var(--ac)", title: "User updated", desc: `${dto.name} saved as ${roleName(roles, dto.roleId)}` });
                }
                setEditing(null);
              } catch (err) {
                addToast({ icon: "⚠️", accent: "#e2603f", title: "Couldn't save user", desc: apiErrorMessage(err) });
              }
            }}
          />
        )}
      </Modal>
    </div>
  );
}

function roleName(roles: { id: string; name: string }[] | undefined, roleId: string) {
  return roles?.find((r) => r.id === roleId)?.name ?? roleId;
}

function UserEditorForm({
  user,
  roles,
  onClose,
  onSave,
}: {
  user: RbacUser | null;
  roles: { id: string; name: string; colorHex: string | null; permissions: string[] }[];
  onClose: () => void;
  onSave: (dto: { name: string; email: string; roleId: string }) => void;
}) {
  const [name, setName] = useState(user?.name ?? "");
  const [email, setEmail] = useState(user?.email ?? "");
  const [roleId, setRoleId] = useState(user?.roleId ?? roles[0]?.id ?? "");

  return (
    <>
      <ModalHeader title={user ? "Edit user" : "Create user"} onClose={onClose} />
      <FieldRow label="FULL NAME">
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Jordan Lee" style={inputStyle} />
      </FieldRow>
      <FieldRow label="WORK EMAIL">
        <input value={email} onChange={(e) => setEmail(e.target.value)} placeholder="jordan@acme.com" style={inputStyle} />
      </FieldRow>
      <FieldRow label="ROLE">
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          {roles.map((r) => (
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
        <Button variant="secondary" onClick={onClose}>
          Cancel
        </Button>
        <Button variant="primary" disabled={!name.trim() || !email.trim()} onClick={() => onSave({ name: name.trim(), email: email.trim(), roleId })}>
          {user ? "Save changes" : "Create user"}
        </Button>
      </div>
    </>
  );
}

export function PageHeader({ title, sub, action }: { title: string; sub: string; action?: React.ReactNode }) {
  return (
    <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: 22 }}>
      <div>
        <h1 style={{ fontSize: 21, fontWeight: 800, margin: 0 }}>{title}</h1>
        <div style={{ fontSize: 12.5, color: "#9499ad", marginTop: 4 }}>{sub}</div>
      </div>
      {action}
    </div>
  );
}

export function FieldRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: 15 }}>
      <label style={{ display: "block", font: "600 10.5px 'IBM Plex Mono',monospace", letterSpacing: ".06em", color: "#5a5f72", marginBottom: 6 }}>{label}</label>
      {children}
    </div>
  );
}

export const inputStyle: React.CSSProperties = {
  width: "100%",
  padding: "10px 12px",
  border: "1px solid #e2e4ee",
  borderRadius: 10,
  fontSize: 13,
};

const gridHeader: React.CSSProperties = {
  display: "grid",
  gridTemplateColumns: "1.5fr 1fr 150px 96px",
  padding: "12px 18px",
  fontSize: 10.5,
  fontWeight: 700,
  letterSpacing: ".06em",
  color: "#9499ad",
  borderBottom: "1px solid #f0f1f6",
};

const gridRow: React.CSSProperties = {
  display: "grid",
  gridTemplateColumns: "1.5fr 1fr 150px 96px",
  alignItems: "center",
  padding: "12px 18px",
  borderBottom: "1px solid #f5f6fb",
};
