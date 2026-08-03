import { useState } from "react";
import { Link } from "react-router-dom";
import { useCreateOrganization, useOrganizations, useSetOrganizationStatus, type Organization } from "../../api/platformAdmin";
import { PageHeader, FieldRow, inputStyle } from "../settings/UsersPage";
import { Button } from "../../components/ui/Button";
import { Modal, ModalHeader } from "../../components/ui/Modal";
import { StatusBadge } from "../../components/ui/StatusBadge";
import { useToast } from "../../stores/useToastStore";
import { useConfirm } from "../../stores/useConfirmStore";
import { apiErrorMessage } from "../../api/client";
import { ListEntrySkeleton } from "../../components/ui/Skeleton";

const CHIP_PALETTE = ["#5b5fc7", "#0f8a5c", "#c0405a", "#b8791f", "#2178c9"];

function chipColor(name: string): string {
  let hash = 0;
  for (let i = 0; i < name.length; i++) hash = (hash * 31 + name.charCodeAt(i)) >>> 0;
  return CHIP_PALETTE[hash % CHIP_PALETTE.length];
}

function orgInitials(name: string): string {
  const words = name.trim().split(/\s+/).slice(0, 2);
  return words.map((w) => w[0]?.toUpperCase() ?? "").join("") || "W";
}

export function OrganizationsPage() {
  const { data: orgs, isLoading } = useOrganizations();
  const createOrg = useCreateOrganization();
  const setOrgStatus = useSetOrganizationStatus();
  const { addToast } = useToast();
  const confirm = useConfirm();
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [adminName, setAdminName] = useState("");
  const [adminEmail, setAdminEmail] = useState("");
  const [search, setSearch] = useState("");
  const filteredOrgs = (orgs ?? []).filter((o) => o.name.toLowerCase().includes(search.trim().toLowerCase()));

  const now = new Date();
  const newThisMonth = (orgs ?? []).filter((o) => {
    const d = new Date(o.createdAt);
    return d.getFullYear() === now.getFullYear() && d.getMonth() === now.getMonth();
  }).length;
  const totalUsers = (orgs ?? []).reduce((sum, o) => sum + o._count.users, 0);

  const submit = async () => {
    try {
      await createOrg.mutateAsync({ name, adminName, adminEmail });
      addToast({ icon: "✅", accent: "#0f8a5c", title: "Workspace created", desc: `${name} is ready — invite sent to ${adminEmail}` });
      setCreating(false);
      setName("");
      setAdminName("");
      setAdminEmail("");
    } catch (err) {
      addToast({ icon: "⚠️", accent: "#e2603f", title: "Couldn't create workspace", desc: apiErrorMessage(err) });
    }
  };

  const toggleOrgStatus = async (e: React.MouseEvent, o: Organization) => {
    e.preventDefault();
    e.stopPropagation();
    const suspending = o.status === "ACTIVE";
    if (suspending) {
      const ok = await confirm({
        title: `Suspend ${o.name}?`,
        body: "All users in this workspace will be immediately blocked from signing in.",
        label: "Suspend workspace",
        tone: "danger",
      });
      if (!ok) return;
    }
    try {
      await setOrgStatus.mutateAsync({ orgId: o.id, status: suspending ? "SUSPENDED" : "ACTIVE" });
      addToast({
        icon: suspending ? "⛔" : "✅",
        accent: suspending ? "#c0405a" : "#0f8a5c",
        title: suspending ? "Workspace suspended" : "Workspace activated",
        desc: o.name,
      });
    } catch (err) {
      addToast({ icon: "⚠️", accent: "#e2603f", title: "Couldn't update workspace", desc: apiErrorMessage(err) });
    }
  };

  return (
    <div style={{ padding: 32, maxWidth: 1080, margin: "0 auto" }}>
      <PageHeader title="Workspaces" sub="Create and manage every organization on the platform" action={<Button variant="primary" onClick={() => setCreating(true)}>+ Create workspace</Button>} />

      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 16, marginBottom: 20 }}>
        <StatTile label="Workspaces" value={orgs?.length ?? 0} />
        <StatTile label="Total users" value={totalUsers} />
        <StatTile label="New this month" value={newThisMonth} />
      </div>

      <input
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        placeholder="Search workspaces..."
        style={{ ...inputStyle, marginBottom: 16 }}
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
          filteredOrgs.length === 0 && (
            <div style={{ padding: 20, color: "#9499ad", fontSize: 13 }}>No workspaces match "{search}".</div>
          )
        )}
        {!isLoading && filteredOrgs.map((o) => (
          <Link
            key={o.id}
            to={`/platform-admin/organizations/${o.id}/users`}
            style={{ display: "flex", alignItems: "center", gap: 14, padding: "14px 18px", minHeight: 56, borderBottom: "1px solid #f5f6fb" }}
          >
            <div
              style={{
                width: 34,
                height: 34,
                borderRadius: "50%",
                background: chipColor(o.name),
                color: "#fff",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                fontWeight: 700,
                fontSize: 13,
                flexShrink: 0,
              }}
            >
              {orgInitials(o.name)}
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontWeight: 700, fontSize: 13.5 }}>{o.name}</div>
              <div style={{ fontSize: 11.5, color: "#9499ad" }}>
                {o._count.users} {o._count.users === 1 ? "user" : "users"} · Created{" "}
                {new Date(o.createdAt).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })}
              </div>
            </div>
            <StatusBadge status={o.status} />
            <Button
              variant={o.status === "ACTIVE" ? "danger" : "secondary"}
              onClick={(e) => toggleOrgStatus(e, o)}
              style={{ padding: "4px 10px", fontSize: 11.5, flexShrink: 0 }}
            >
              {o.status === "ACTIVE" ? "Suspend" : "Activate"}
            </Button>
            <span style={{ color: "var(--ac)", fontWeight: 700, fontSize: 12.5, flexShrink: 0 }}>Manage users →</span>
          </Link>
        ))}
      </div>

      <Modal open={creating} onClose={() => setCreating(false)}>
        <ModalHeader title="Create workspace" onClose={() => setCreating(false)} />
        <FieldRow label="WORKSPACE NAME">
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Globex Inc" style={inputStyle} />
        </FieldRow>
        <FieldRow label="FIRST ADMIN — FULL NAME">
          <input value={adminName} onChange={(e) => setAdminName(e.target.value)} placeholder="Jordan Lee" style={inputStyle} />
        </FieldRow>
        <FieldRow label="FIRST ADMIN — EMAIL">
          <input value={adminEmail} onChange={(e) => setAdminEmail(e.target.value)} placeholder="jordan@globex.com" style={inputStyle} />
        </FieldRow>
        <div style={{ display: "flex", justifyContent: "flex-end", gap: 10, marginTop: 18 }}>
          <Button variant="secondary" onClick={() => setCreating(false)}>Cancel</Button>
          <Button variant="primary" disabled={!name.trim() || !adminName.trim() || !adminEmail.trim()} onClick={submit}>Create</Button>
        </div>
      </Modal>
    </div>
  );
}

function StatTile({ label, value }: { label: string; value: number }) {
  return (
    <div style={{ background: "#fff", border: "1px solid #e9eaf2", borderRadius: 16, padding: "20px 22px" }}>
      <div style={{ font: "600 10.5px 'IBM Plex Mono',monospace", letterSpacing: ".06em", color: "#9499ad", marginBottom: 8 }}>
        {label.toUpperCase()}
      </div>
      <div style={{ fontSize: 26, fontWeight: 800 }}>{value}</div>
    </div>
  );
}
