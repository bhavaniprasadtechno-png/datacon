import { useState } from "react";
import { useCreateRole, useDeleteRole, usePermissionCatalog, useUpdateRole, useRoles } from "../../api/rbac";
import { useToast } from "../../stores/useToastStore";
import { useConfirm } from "../../stores/useConfirmStore";
import { Modal, ModalHeader } from "../../components/ui/Modal";
import { Button } from "../../components/ui/Button";
import { apiErrorMessage } from "../../api/client";
import { PageHeader, FieldRow, inputStyle } from "./UsersPage";
import type { RbacRole } from "../../lib/types";
import type { PermissionKey } from "@datacon/shared-types";

const ROLE_COLORS = ["var(--ac)", "#2bb8c4", "#e2603f", "#3f6fd6", "#13a06b", "#b9743a", "#c0392b"];

export function RolesPage() {
  const { data: roles, isLoading } = useRoles();
  const { data: perms } = usePermissionCatalog();
  const { addToast } = useToast();
  const confirm = useConfirm();
  const createRole = useCreateRole();
  const updateRole = useUpdateRole();
  const deleteRole = useDeleteRole();
  const [editing, setEditing] = useState<RbacRole | "new" | null>(null);

  const remove = async (r: RbacRole) => {
    if (r.userCount > 0) {
      addToast({ icon: "⚠️", accent: "#d9a23a", title: "Role in use", desc: `${r.name} is assigned to ${r.userCount} user(s). Reassign them first.` });
      return;
    }
    const ok = await confirm({
      title: `Delete the ${r.name} role?`,
      body: "The role and its permission set will be permanently removed.",
      label: "Delete role",
      tone: "danger",
    });
    if (!ok) return;
    try {
      await deleteRole.mutateAsync(r.id);
      addToast({ icon: "🗑️", accent: "#e2603f", title: "Role deleted", desc: `${r.name} was removed` });
    } catch (err) {
      addToast({ icon: "⚠️", accent: "#e2603f", title: "Couldn't delete role", desc: apiErrorMessage(err) });
    }
  };

  return (
    <div style={{ padding: 32, maxWidth: 1080, margin: "0 auto" }}>
      <PageHeader title="Roles" sub="Define roles and the permissions each one grants" action={<Button variant="primary" onClick={() => setEditing("new")}>+ Create role</Button>} />

      <div style={{ display: "grid", gridTemplateColumns: "repeat(2,1fr)", gap: 16 }}>
        {isLoading && <div style={{ color: "#9499ad" }}>Loading…</div>}
        {roles?.map((r) => (
          <div key={r.id} style={{ background: "#fff", borderRadius: 16, border: "1px solid #e9eaf2", padding: 18 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 4 }}>
              <div style={{ width: 38, height: 38, borderRadius: 11, background: r.bgHex ?? "#f0f1f6", color: r.colorHex ?? "#71768a", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 17 }}>🛡</div>
              <div style={{ fontSize: 14, fontWeight: 800 }}>{r.name}</div>
              {r.isSystem && <span style={{ font: "600 9px 'IBM Plex Mono',monospace", padding: "2px 7px", borderRadius: 6, background: "#f0f1f6", color: "#71768a" }}>SYSTEM</span>}
            </div>
            <div style={{ fontSize: 11.5, color: "#9499ad", marginBottom: 10 }}>
              {r.permissions.length} permissions · {r.userCount} users
            </div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 14 }}>
              {r.permissions.slice(0, 3).map((p) => (
                <span key={p} style={{ fontSize: 10.5, background: "#f5f6fb", color: "#5a5f72", padding: "3px 8px", borderRadius: 20 }}>
                  {perms?.find((pd) => pd.key === p)?.label ?? p}
                </span>
              ))}
              {r.permissions.length > 3 && <span style={{ fontSize: 10.5, color: "#9499ad" }}>+{r.permissions.length - 3} more</span>}
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 12, paddingTop: 10, borderTop: "1px solid #f3f4f9" }}>
              <button onClick={() => setEditing(r)} style={{ color: "var(--ac)", fontWeight: 700, fontSize: 12.5 }}>
                Edit permissions
              </button>
              <div style={{ flex: 1 }} />
              {r.isSystem ? (
                <span style={{ fontSize: 11.5, color: "#9499ad" }}>🔒 Protected</span>
              ) : (
                <button onClick={() => remove(r)} style={{ color: "#c0392b", fontWeight: 700, fontSize: 12.5 }}>
                  Delete
                </button>
              )}
            </div>
          </div>
        ))}
      </div>

      <Modal open={editing !== null} onClose={() => setEditing(null)} width={480}>
        {editing && perms && (
          <RoleEditorForm
            role={editing === "new" ? null : editing}
            perms={perms}
            onClose={() => setEditing(null)}
            onSave={async (dto) => {
              try {
                if (editing === "new") {
                  await createRole.mutateAsync(dto);
                  addToast({ icon: "✅", accent: "#0f8a5c", title: "Role created", desc: `${dto.name} · ${dto.permissions.length} permissions` });
                } else {
                  await updateRole.mutateAsync({ id: editing.id, ...dto });
                  addToast({ icon: "✏️", accent: "var(--ac)", title: "Role updated", desc: `${dto.name} · ${dto.permissions.length} permissions` });
                }
                setEditing(null);
              } catch (err) {
                addToast({ icon: "⚠️", accent: "#e2603f", title: "Couldn't save role", desc: apiErrorMessage(err) });
              }
            }}
          />
        )}
      </Modal>
    </div>
  );
}

function RoleEditorForm({
  role,
  perms,
  onClose,
  onSave,
}: {
  role: RbacRole | null;
  perms: { key: PermissionKey; label: string; group: string }[];
  onClose: () => void;
  onSave: (dto: { name: string; colorHex: string; permissions: PermissionKey[] }) => void;
}) {
  const [name, setName] = useState(role?.name ?? "");
  const [color, setColor] = useState(role?.colorHex ?? ROLE_COLORS[0]);
  const [selected, setSelected] = useState<PermissionKey[]>(role?.permissions ?? ["view_dashboards"]);

  const toggle = (key: PermissionKey) => {
    setSelected((prev) => (prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key]));
  };

  return (
    <>
      <ModalHeader title={role ? "Edit role" : "Create role"} onClose={onClose} />
      <FieldRow label="ROLE NAME">
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Finance analyst" style={inputStyle} />
      </FieldRow>
      <FieldRow label="COLOR">
        <div style={{ display: "flex", gap: 8 }}>
          {ROLE_COLORS.map((c) => (
            <button
              key={c}
              onClick={() => setColor(c)}
              style={{
                width: 26,
                height: 26,
                borderRadius: "50%",
                background: c,
                boxShadow: color === c ? "0 0 0 2px #1a1d29, inset 0 0 0 2px #fff" : "none",
              }}
            />
          ))}
        </div>
      </FieldRow>
      <FieldRow label="PERMISSIONS">
        <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
          {perms.map((p) => (
            <button
              key={p.key}
              onClick={() => toggle(p.key)}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 10,
                padding: "8px 10px",
                borderRadius: 9,
                border: "1px solid #e9eaf2",
                background: selected.includes(p.key) ? "var(--ac-softer)" : "#fff",
                textAlign: "left",
              }}
            >
              <span
                style={{
                  width: 16,
                  height: 16,
                  borderRadius: 4,
                  border: `1px solid ${selected.includes(p.key) ? "var(--ac)" : "#c9cbd6"}`,
                  background: selected.includes(p.key) ? "var(--ac)" : "#fff",
                  color: "#fff",
                  fontSize: 11,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  flexShrink: 0,
                }}
              >
                {selected.includes(p.key) && "✓"}
              </span>
              <span style={{ flex: 1, fontSize: 12.5 }}>{p.label}</span>
              <span style={{ font: "600 9.5px 'IBM Plex Mono',monospace", color: "#a3a8bd" }}>{p.group}</span>
            </button>
          ))}
        </div>
      </FieldRow>
      <div style={{ display: "flex", justifyContent: "flex-end", gap: 10, marginTop: 18 }}>
        <Button variant="secondary" onClick={onClose}>
          Cancel
        </Button>
        <Button variant="primary" disabled={!name.trim() || selected.length === 0} onClick={() => onSave({ name: name.trim(), colorHex: color, permissions: selected })}>
          {role ? "Save changes" : "Create role"}
        </Button>
      </div>
    </>
  );
}
