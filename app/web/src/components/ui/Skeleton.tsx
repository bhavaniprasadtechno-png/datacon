import { Skeleton as BaseSkeleton } from "../shadcn-ui/ui/skeleton";

// Re-export the base Skeleton for simple usage
export { BaseSkeleton as Skeleton };

// 1. KPI Card Skeleton (Insights & Platform Overview Stats)
export function KpiCardSkeleton() {
  return (
    <div style={{ background: "var(--ac-bg-muted)", borderRadius: 16, border: "1px solid var(--ac-border)", padding: "18px 20px" }}>
      <BaseSkeleton className="h-3 w-1/3 mb-3 bg-slate-200/60 dark:bg-slate-800/50" />
      <BaseSkeleton className="h-7 w-2/3 mb-2 bg-slate-200/60 dark:bg-slate-800/50" />
      <BaseSkeleton className="h-3.5 w-1/2 bg-slate-200/60 dark:bg-slate-800/50" />
    </div>
  );
}

// 2. Connector Card Skeleton (ConnectorsPage Grid)
export function ConnectorCardSkeleton() {
  return (
    <div style={{ background: "var(--ac-bg-muted)", borderRadius: 16, border: "1px solid var(--ac-border)", padding: 16 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <BaseSkeleton className="h-[42px] w-[42px] rounded-xl bg-slate-200/60 dark:bg-slate-800/50" />
        <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 6 }}>
          <BaseSkeleton className="h-4 w-1/2 bg-slate-200/60 dark:bg-slate-800/50" />
          <BaseSkeleton className="h-3 w-1/3 bg-slate-200/60 dark:bg-slate-800/50" />
        </div>
        <BaseSkeleton className="h-5 w-[70px] rounded-full bg-slate-200/60 dark:bg-slate-800/50" />
      </div>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginTop: 12, paddingTop: 12, borderTop: "1px solid var(--ac-border)" }}>
        <BaseSkeleton className="h-3 w-1/3 bg-slate-200/60 dark:bg-slate-800/50" />
        <BaseSkeleton className="h-3 w-[60px] bg-slate-200/60 dark:bg-slate-800/50" />
      </div>
    </div>
  );
}

// 3. Grid-aligned Table Row Skeletons
export function TableRowSkeleton({ gridCols }: { gridCols: string }) {
  return (
    <div style={{ display: "grid", gridTemplateColumns: gridCols, alignItems: "center", padding: "10px 18px", borderBottom: "1px solid var(--ac-border)", minHeight: "47px" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 9 }}>
        <BaseSkeleton className="h-[26px] w-[26px] rounded-lg bg-slate-200/60 dark:bg-slate-800/50" />
        <BaseSkeleton className="h-3.5 w-[120px] bg-slate-200/60 dark:bg-slate-800/50" />
      </div>
      <BaseSkeleton className="h-3.5 w-[80px] bg-slate-200/60 dark:bg-slate-800/50" />
      <BaseSkeleton className="h-3.5 w-[90px] bg-slate-200/60 dark:bg-slate-800/50" />
      <BaseSkeleton className="h-5 w-[70px] rounded-full bg-slate-200/60 dark:bg-slate-800/50" />
      <BaseSkeleton className="h-3.5 w-[50px] bg-slate-200/60 dark:bg-slate-800/50" />
    </div>
  );
}

// 4. Simple List Entry Skeletons (Users, Org lists, ChatHistory)
export function ListEntrySkeleton({ hasAvatar = true, gridCols }: { hasAvatar?: boolean; gridCols?: string }) {
  if (gridCols) {
    return (
      <div style={{ display: "grid", gridTemplateColumns: gridCols, alignItems: "center", padding: "12px 18px", borderBottom: "1px solid #f5f6fb", minHeight: "56px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, minWidth: 0 }}>
          {hasAvatar && <BaseSkeleton className="h-[34px] w-[34px] rounded-full bg-slate-200/60 dark:bg-slate-800/50 flex-shrink-0" />}
          <div style={{ display: "flex", flexDirection: "column", gap: 6, flex: 1 }}>
            <BaseSkeleton className="h-3.5 w-[110px] bg-slate-200/60 dark:bg-slate-800/50" />
            <BaseSkeleton className="h-3 w-[150px] bg-slate-200/60 dark:bg-slate-800/50" />
          </div>
        </div>
        <div>
          <BaseSkeleton className="h-5 w-[65px] rounded-full bg-slate-200/60 dark:bg-slate-800/50" />
        </div>
        <div>
          <BaseSkeleton className="h-3.5 w-[70px] bg-slate-200/60 dark:bg-slate-800/50" />
        </div>
        <div>
          <BaseSkeleton className="h-4 w-[40px] bg-slate-200/60 dark:bg-slate-800/50" />
        </div>
      </div>
    );
  }

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "12px 18px", borderBottom: "1px solid #f5f6fb", minHeight: "56px" }}>
      {hasAvatar && <BaseSkeleton className="h-[34px] w-[34px] rounded-full bg-slate-200/60 dark:bg-slate-800/50 flex-shrink-0" />}
      <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 6 }}>
        <BaseSkeleton className="h-3.5 w-1/4 bg-slate-200/60 dark:bg-slate-800/50" />
        <BaseSkeleton className="h-3 w-1/3 bg-slate-200/60 dark:bg-slate-800/50" />
      </div>
      <BaseSkeleton className="h-5 w-[65px] rounded-full bg-slate-200/60 dark:bg-slate-800/50" />
      <BaseSkeleton className="h-7 w-[60px] bg-slate-200/60 dark:bg-slate-800/50" />
    </div>
  );
}

// 5. Chart Card Loading
export function ChartCardSkeleton() {
  return (
    <div style={{ background: "var(--ac-bg-muted)", borderRadius: 16, border: "1px solid var(--ac-border)", padding: 18, display: "flex", flexDirection: "column", gap: 14 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <BaseSkeleton className="h-4 w-1/3 bg-slate-200/60 dark:bg-slate-800/50" />
        <BaseSkeleton className="h-3.5 w-[110px] bg-slate-200/60 dark:bg-slate-800/50" />
      </div>
      <BaseSkeleton className="h-[150px] w-full bg-slate-200/60 dark:bg-slate-800/50" />
      <div style={{ display: "flex", gap: 16 }}>
        <BaseSkeleton className="h-3 w-[70px] bg-slate-200/60 dark:bg-slate-800/50" />
        <BaseSkeleton className="h-3 w-[120px] bg-slate-200/60 dark:bg-slate-800/50" />
      </div>
    </div>
  );
}

// 6. Role Card Placeholder
export function RoleCardSkeleton() {
  return (
    <div style={{ background: "var(--ac-bg-muted)", borderRadius: 16, border: "1px solid var(--ac-border)", padding: 18, display: "flex", flexDirection: "column", gap: 10 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <BaseSkeleton className="h-[38px] w-[38px] rounded-xl bg-slate-200/60 dark:bg-slate-800/50" />
        <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 4 }}>
          <BaseSkeleton className="h-4 w-1/3 bg-slate-200/60 dark:bg-slate-800/50" />
        </div>
      </div>
      <BaseSkeleton className="h-3 w-1/4 bg-slate-200/60 dark:bg-slate-800/50" style={{ marginTop: 4 }} />
      <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 4 }}>
        <BaseSkeleton className="h-6 w-[80px] rounded-full bg-slate-200/60 dark:bg-slate-800/50" />
        <BaseSkeleton className="h-6 w-[100px] rounded-full bg-slate-200/60 dark:bg-slate-800/50" />
        <BaseSkeleton className="h-6 w-[60px] rounded-full bg-slate-200/60 dark:bg-slate-800/50" />
      </div>
      <div style={{ display: "flex", gap: 12, marginTop: 8 }}>
        <BaseSkeleton className="h-4 w-[50px] bg-slate-200/60 dark:bg-slate-800/50" />
        <BaseSkeleton className="h-4 w-[60px] bg-slate-200/60 dark:bg-slate-800/50" />
      </div>
    </div>
  );
}

// 7. Conversation Card Placeholder (ChatHistoryPage)
export function ConversationCardSkeleton() {
  return (
    <div style={{ padding: "14px 18px", background: "var(--ac-bg-muted)", borderRadius: 16, border: "1px solid var(--ac-border)", marginBottom: 10, display: "flex", alignItems: "center", justifyContent: "space-between", minHeight: 64 }}>
      <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 6 }}>
        <BaseSkeleton className="h-4 w-1/3 bg-slate-200/60 dark:bg-slate-800/50" />
        <BaseSkeleton className="h-3 w-1/4 bg-slate-200/60 dark:bg-slate-800/50" />
      </div>
      <BaseSkeleton className="h-4 w-4 bg-slate-200/60 dark:bg-slate-800/50" />
    </div>
  );
}
