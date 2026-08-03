import { useOrganizations } from "../../api/platformAdmin";
import { PageHeader } from "../settings/UsersPage";
import { Card, CardContent, CardHeader, CardTitle } from "../../components/shadcn-ui/ui/card";
import { Skeleton } from "../../components/shadcn-ui/ui/skeleton";

const MOCK_MRR = { label: "MONTHLY RECURRING REVENUE", value: "$284,900", trend: "↑ 12.4% vs last month" };
const MOCK_CHURN = { label: "CHURN RATE", value: "1.8%", trend: "↓ 0.3pt improved" };

const MOCK_PLANS = [
  { name: "Starter", price: 99, orgCount: 18, color: "#9499ad" },
  { name: "Growth", price: 299, orgCount: 34, color: "#6d4dff" },
  { name: "Enterprise", price: 899, orgCount: 11, color: "#2bb8c4" },
];

const MOCK_ACTIVITY = [
  { icon: "👤", text: "Jordan Lee (Acme Corp) signed in", time: "2h ago" },
  { icon: "💳", text: "Nimbus Retail upgraded to Growth", time: "6h ago" },
  { icon: "🔌", text: "Snowflake provider reconnected", time: "1d ago" },
  { icon: "⛔", text: "FinTrail admin account suspended", time: "13d ago" },
];

export function PlatformOverviewPage() {
  const { data: orgs, isLoading } = useOrganizations();

  const now = new Date();
  const newThisMonth = (orgs ?? []).filter((o) => {
    const d = new Date(o.createdAt);
    return d.getFullYear() === now.getFullYear() && d.getMonth() === now.getMonth();
  }).length;
  const activeOrgCount = (orgs ?? []).filter((o) => o.status === "ACTIVE").length;
  const totalUsers = (orgs ?? []).reduce((sum, o) => sum + o._count.users, 0);
  const planTotal = MOCK_PLANS.reduce((sum, p) => sum + p.price * p.orgCount, 0);

  return (
    <div className="mx-auto max-w-[1080px] p-8">
      <PageHeader title="Platform overview" sub="Revenue, growth and account health across every organization" />

      <div className="mb-5 grid grid-cols-4 gap-4">
        <KpiCard label={MOCK_MRR.label} value={MOCK_MRR.value} trend={MOCK_MRR.trend} loading={isLoading} />
        <KpiCard label="ACTIVE ORGANIZATIONS" value={String(activeOrgCount)} trend={`↑ ${newThisMonth} new this month`} loading={isLoading} />
        <KpiCard label="TOTAL USERS" value={totalUsers.toLocaleString()} loading={isLoading} />
        <KpiCard label={MOCK_CHURN.label} value={MOCK_CHURN.value} trend={MOCK_CHURN.trend} loading={isLoading} />
      </div>

      <div className="grid grid-cols-2 gap-4">
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-bold">Revenue by plan</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-3.5">
            {isLoading ? (
              [1, 2, 3].map((n) => (
                <div key={n} className="flex flex-col gap-2">
                  <div className="flex justify-between">
                    <Skeleton className="h-4 w-1/4" />
                    <Skeleton className="h-4 w-1/6" />
                  </div>
                  <Skeleton className="h-2 w-full" />
                </div>
              ))
            ) : (
              MOCK_PLANS.map((p) => {
                const val = p.price * p.orgCount;
                const pct = Math.round((val / planTotal) * 100);
                return (
                  <div key={p.name}>
                    <div className="mb-1.5 flex justify-between text-[12.5px] font-bold">
                      <span>{p.name}</span>
                      <span>
                        ${val.toLocaleString()} · {pct}%
                      </span>
                    </div>
                    <div className="h-2 overflow-hidden rounded-full bg-[#eceaf8]">
                      <div className="h-full rounded-full" style={{ width: `${pct}%`, background: p.color }} />
                    </div>
                  </div>
                );
              })
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-bold">Recent admin activity</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-3.5">
            {isLoading ? (
              [1, 2, 3, 4].map((n) => (
                <div key={n} className="flex items-start gap-2.5">
                  <Skeleton className="h-5 w-5 rounded-full flex-shrink-0" />
                  <div className="flex-1 flex flex-col gap-1.5">
                    <Skeleton className="h-3.5 w-2/3" />
                    <Skeleton className="h-3 w-1/4" />
                  </div>
                </div>
              ))
            ) : (
              MOCK_ACTIVITY.map((a) => (
                <div key={a.text} className="flex items-start gap-2.5">
                  <span className="text-[15px]">{a.icon}</span>
                  <div>
                    <div className="text-[12.5px] font-semibold">{a.text}</div>
                    <div className="text-[11px] text-[#9499ad]">{a.time}</div>
                  </div>
                </div>
              ))
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function KpiCard({ label, value, trend, loading }: { label: string; value: string; trend?: string; loading?: boolean }) {
  return (
    <Card>
      <CardContent>
        <div className="mb-2 font-mono text-[10.5px] font-semibold tracking-[.06em] text-[#9499ad]">{label}</div>
        {loading ? (
          <>
            <Skeleton className="mb-2 h-7 w-2/3" />
            {trend && <Skeleton className="h-3.5 w-1/2" />}
          </>
        ) : (
          <>
            <div className="text-2xl font-extrabold">{value}</div>
            {trend && <div className="mt-1.5 text-[11.5px] font-bold text-[#1a9d6c]">{trend}</div>}
          </>
        )}
      </CardContent>
    </Card>
  );
}
