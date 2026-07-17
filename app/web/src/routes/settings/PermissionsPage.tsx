import { useState } from "react";
import type { PermissionKey } from "@datacon/shared-types";
import { useApplyPermissionsMatrix, usePermissionCatalog, useRoles } from "../../api/rbac";
import { useToast } from "../../stores/useToastStore";
import { useConfirm } from "../../stores/useConfirmStore";
import { Button } from "../../components/ui/Button";
import { apiErrorMessage } from "../../api/client";
import { PageHeader } from "./UsersPage";

export function PermissionsPage() {
  const { data: roles, isLoading } = useRoles();
  const { data: perms } = usePermissionCatalog();
  const { addToast } = useToast();
  const confirm = useConfirm();
  const applyMatrix = useApplyPermissionsMatrix();
  const [draft, setDraft] = useState<Record<string, PermissionKey[]> | null>(null);

  const startEdit = () => {
    if (!roles) return;
    setDraft(Object.fromEntries(roles.map((r) => [r.id, [...r.permissions]])));
  };

  const toggle = (roleId: string, key: PermissionKey) => {
    setDraft((prev) => {
      if (!prev) return prev;
      const current = prev[roleId] ?? [];
      const next = current.includes(key) ? current.filter((k) => k !== key) : [...current, key];
      return { ...prev, [roleId]: next };
    });
  };

  const apply = async () => {
    if (!draft) return;
    const ok = await confirm({
      title: "Apply permission changes?",
      body: "Every user inherits their role's permissions immediately across the app.",
      label: "Apply changes",
      tone: "primary",
    });
    if (!ok) return;
    try {
      await applyMatrix.mutateAsync(draft);
      addToast({ icon: "🛡️", accent: "var(--ac)", title: "Permissions saved", desc: "Role permission sets updated" });
      setDraft(null);
    } catch (err) {
      addToast({ icon: "⚠️", accent: "#e2603f", title: "Couldn't save permissions", desc: apiErrorMessage(err) });
    }
  };

  const editing = draft !== null;

  return (
    <div style={{ padding: 32, maxWidth: 1080, margin: "0 auto" }}>
      <PageHeader
        title="Permissions"
        sub="Toggle what each role can do, then apply"
        action={
          editing ? (
            <div style={{ display: "flex", gap: 10 }}>
              <Button variant="secondary" onClick={() => setDraft(null)}>
                Cancel
              </Button>
              <Button variant="primary" onClick={apply}>
                Apply changes
              </Button>
            </div>
          ) : (
            <Button variant="primary" onClick={startEdit}>
              Edit permissions
            </Button>
          )
        }
      />

      {isLoading && <div style={{ color: "#9499ad" }}>Loading…</div>}
      {roles && perms && (
        <div style={{ background: "#fff", borderRadius: 16, border: "1px solid #e9eaf2", overflow: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12.5 }}>
            <thead>
              <tr style={{ borderBottom: "1px solid #f0f1f6" }}>
                <th style={{ textAlign: "left", padding: "12px 18px", fontSize: 10.5, color: "#9499ad" }}>PERMISSION</th>
                {roles.map((r) => (
                  <th key={r.id} style={{ width: 82, textAlign: "center", padding: "12px 8px", color: r.colorHex ?? "#71768a", fontSize: 10.5 }}>
                    {r.name.toUpperCase()}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {perms.map((p) => (
                <tr key={p.key} style={{ borderBottom: "1px solid #f5f6fb" }}>
                  <td style={{ padding: "10px 18px" }}>
                    <div style={{ fontWeight: 600 }}>{p.label}</div>
                    <div style={{ font: "600 9.5px 'IBM Plex Mono',monospace", color: "#a3a8bd" }}>{p.group.toUpperCase()}</div>
                  </td>
                  {roles.map((r) => {
                    const granted = editing ? draft![r.id]?.includes(p.key) : r.permissions.includes(p.key);
                    return (
                      <td key={r.id} style={{ textAlign: "center" }}>
                        {editing ? (
                          <button
                            onClick={() => toggle(r.id, p.key)}
                            style={{
                              width: 26,
                              height: 26,
                              borderRadius: 8,
                              border: `1px solid ${granted ? "var(--ac-ring)" : "#e2e4ee"}`,
                              background: granted ? "var(--ac-soft)" : "#fff",
                              color: "var(--ac-deep)",
                              fontSize: 13,
                            }}
                          >
                            {granted && "✓"}
                          </button>
                        ) : granted ? (
                          <span style={{ color: "#0f8a5c", fontWeight: 700 }}>✓</span>
                        ) : (
                          <span style={{ color: "#d4d7e2" }}>–</span>
                        )}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
