/**
 * Seeds the exact demo dataset from the Datacon design prototype
 * (project/Datacon.dc.html, script block lines 1150-1850) so the real
 * app starts in the same state the prototype demoed.
 */
import * as path from "path";
import * as dotenv from "dotenv";
import { PrismaClient, ConnectorEngine, ConnectorStatus, DocType, DocStatus } from "./index";
import * as bcrypt from "bcryptjs";

dotenv.config({ path: path.resolve(__dirname, "../../.env") });

const prisma = new PrismaClient();

// Seed login password for all demo personas — documented in app/README, not for production use.
const SEED_PASSWORD = "Datacon123!";

const PERMISSIONS = [
  { key: "view_dashboards", label: "View dashboards & forecasts", group: "Analytics" },
  { key: "ask_agents", label: "Ask the AI agents", group: "Analytics" },
  { key: "export_data", label: "Export data & reports", group: "Analytics" },
  { key: "upload_docs", label: "Upload & index documents", group: "Data" },
  { key: "manage_connectors", label: "Manage data connectors", group: "Data" },
  { key: "manage_users", label: "Create & manage users", group: "Administration" },
  { key: "manage_roles", label: "Manage roles & permissions", group: "Administration" },
];

const ROLES = [
  {
    id: "viewer",
    name: "Viewer",
    colorHex: "#b9743a",
    bgHex: "#fbeede",
    isSystem: true,
    perms: ["view_dashboards", "ask_agents"],
  },
  {
    id: "analyst",
    name: "Analyst",
    colorHex: "#5b3fd6",
    bgHex: "#efeaff",
    isSystem: true,
    perms: ["view_dashboards", "ask_agents", "export_data", "upload_docs", "manage_connectors"],
  },
  {
    id: "admin",
    name: "Admin",
    colorHex: "#1d8e9c",
    bgHex: "#e3f6f9",
    isSystem: true,
    perms: [
      "view_dashboards",
      "ask_agents",
      "export_data",
      "upload_docs",
      "manage_connectors",
      "manage_users",
      "manage_roles",
    ],
  },
];

const USERS = [
  {
    id: "sarah",
    name: "Sarah Okonkwo",
    email: "sarah@acme.com",
    initials: "S",
    avatarGrad: "var(--ac-grad)",
    title: "Senior Analyst",
    roleId: "analyst",
    isCore: true,
  },
  {
    id: "david",
    name: "David Reyes",
    email: "david@acme.com",
    initials: "D",
    avatarGrad: "linear-gradient(135deg,#ff8a5c,#ff5c7a)",
    title: "VP Sales & Ops",
    roleId: "viewer",
    isCore: true,
  },
  {
    id: "tom",
    name: "Tom Halvorsen",
    email: "tom@acme.com",
    initials: "T",
    avatarGrad: "linear-gradient(135deg,#1fb6a6,#13a06b)",
    title: "Database Admin",
    roleId: "admin",
    isCore: true,
  },
  {
    id: "maria",
    name: "Maria Santos",
    email: "maria@acme.com",
    initials: "M",
    avatarGrad: "linear-gradient(135deg,#5b8def,#3f6fd6)",
    title: "Analyst",
    roleId: "analyst",
    isCore: false,
  },
];

const CONNECTORS = [
  {
    id: "conn-prod-postgres",
    name: "Production Postgres",
    engine: ConnectorEngine.POSTGRES,
    config: { host: "prod-pg.internal", port: "5432", database: "analytics", username: "analyst", schema: "public", sslMode: "prefer" },
    status: ConnectorStatus.SYNCED,
    lastSyncedAt: new Date(Date.now() - 2 * 60 * 1000),
    syncInterval: "Every 15 minutes",
  },
  {
    id: "conn-snowflake-finance",
    name: "Snowflake — Finance",
    engine: ConnectorEngine.SNOWFLAKE,
    config: { account: "abc-xy12345", username: "analyst", warehouse: "COMPUTE_WH", database: "ANALYTICS", schema: "PUBLIC", role: "ANALYST" },
    status: ConnectorStatus.SYNCED,
    lastSyncedAt: new Date(Date.now() - 9 * 60 * 1000),
    syncInterval: "Hourly",
  },
  {
    id: "conn-support-mysql",
    name: "Support MySQL",
    engine: ConnectorEngine.MYSQL,
    config: { host: "support-mysql.internal", port: "3306", database: "analytics", username: "analyst" },
    status: ConnectorStatus.SYNCING,
    lastSyncedAt: null,
    syncInterval: "Every 30 minutes",
  },
  {
    id: "conn-bigquery-product",
    name: "BigQuery — Product",
    engine: ConnectorEngine.BIGQUERY,
    config: { projectId: "acme-product", dataset: "analytics", location: "US" },
    status: ConnectorStatus.SYNCED,
    lastSyncedAt: new Date(Date.now() - 6 * 60 * 1000),
    syncInterval: "Hourly",
  },
];

const TABLES = [
  {
    connectorId: "conn-prod-postgres",
    name: "orders",
    columns: ["order_id", "customer_id", "region", "amount", "status", "created_at"],
    rowCount: 8420,
    status: "synced",
    sampleRows: [
      ["ORD-10482", "CUS-2231", "NA", "$1,240.00", "paid", "2026-06-29"],
      ["ORD-10481", "CUS-1187", "EMEA", "$860.00", "paid", "2026-06-29"],
      ["ORD-10480", "CUS-3390", "APAC", "$410.00", "refunded", "2026-06-28"],
    ],
  },
  {
    connectorId: "conn-prod-postgres",
    name: "customers",
    columns: ["customer_id", "name", "tier", "mrr", "seats", "active"],
    rowCount: 2310,
    status: "synced",
    sampleRows: [
      ["CUS-2231", "Nimbus Retail", "Enterprise", "$4,200", "80", "true"],
      ["CUS-1187", "Fenwick & Co", "Growth", "$1,100", "22", "true"],
    ],
  },
  {
    connectorId: "conn-support-mysql",
    name: "tickets",
    columns: ["ticket_id", "account", "region", "priority", "category", "opened_at"],
    rowCount: 1284,
    status: "syncing",
    sampleRows: [
      ["TCK-88213", "Nimbus Retail", "EMEA", "High", "Billing", "2026-06-29"],
      ["TCK-88190", "Fenwick & Co", "NA", "Medium", "Onboarding", "2026-06-28"],
    ],
  },
  {
    connectorId: "conn-snowflake-finance",
    name: "revenue_daily",
    columns: ["date", "region", "revenue", "new_arr", "churned_arr", "net"],
    rowCount: 540,
    status: "synced",
    sampleRows: [
      ["2026-06-29", "NA", "$64,200", "$5,100", "$1,800", "$3,300"],
      ["2026-06-29", "EMEA", "$38,900", "$2,400", "$900", "$1,500"],
    ],
  },
  {
    connectorId: "conn-bigquery-product",
    name: "product_events",
    columns: ["event_id", "user_id", "event", "feature", "ts"],
    rowCount: 91200,
    status: "synced",
    sampleRows: [
      ["EVT-99812310", "USR-4471", "feature_used", "forecast_export", "2026-06-29T18:02:11Z"],
      ["EVT-99812309", "USR-2290", "session_start", "-", "2026-06-29T18:01:58Z"],
    ],
  },
  {
    connectorId: "conn-snowflake-finance",
    name: "churn_scores",
    columns: ["customer_id", "score", "risk", "top_signal", "updated"],
    rowCount: 827,
    status: "synced",
    sampleRows: [
      ["CUS-9021", "0.82", "high", "usage_drop", "2026-06-29"],
      ["CUS-4410", "0.61", "medium", "support_volume", "2026-06-29"],
    ],
  },
];

// Note: the prototype's own seed copy uses the placeholder email "analyst@lyra.ai"
// for several documents' "uploaded by" field. We map that placeholder to Sarah
// Okonkwo (our real analyst persona) rather than inventing a non-existent user.
const DOCUMENTS = [
  {
    id: "doc-inc-2026-074",
    title: "INC-2026-074 Billing incident",
    filename: "INC-2026-074.pdf",
    type: DocType.PDF,
    status: DocStatus.INDEXED,
    sizeBytes: 812_000,
    chunkCount: 48,
    uploadedById: "sarah",
    createdAt: new Date("2026-06-29T18:11:28"),
  },
  {
    id: "doc-support-sop",
    title: "Support runbook",
    filename: "support_sop.md",
    type: DocType.MD,
    status: DocStatus.INDEXED,
    sizeBytes: 41_000,
    chunkCount: 12,
    uploadedById: "sarah",
    createdAt: new Date("2026-06-29T18:11:28"),
  },
  {
    id: "doc-test-incident",
    title: "TEST_incident",
    filename: "TEST_incident.txt",
    type: DocType.TXT,
    status: DocStatus.INDEXED,
    sizeBytes: 2_100,
    chunkCount: 1,
    uploadedById: "sarah",
    createdAt: new Date("2026-06-29T17:45:19"),
  },
  {
    id: "doc-test-upload",
    title: "TEST_upload",
    filename: "TEST_upload.csv",
    type: DocType.CSV,
    status: DocStatus.INDEXED,
    sizeBytes: 340,
    rowCount: 2,
    colCount: 3,
    uploadedById: "sarah",
    createdAt: new Date("2026-06-29T17:45:19"),
  },
  {
    id: "doc-q2-research-brief",
    title: "Q2 research brief",
    filename: "q2_research_brief.pdf",
    type: DocType.PDF,
    status: DocStatus.INDEXING,
    sizeBytes: 1_240_000,
    chunkCount: 0,
    uploadedById: "sarah",
    createdAt: new Date("2026-06-30T09:02:11"),
  },
];

async function main() {
  console.log("Seeding permissions...");
  for (const p of PERMISSIONS) {
    await prisma.permission.upsert({ where: { key: p.key }, update: p, create: p });
  }

  console.log("Seeding roles...");
  for (const r of ROLES) {
    await prisma.role.upsert({
      where: { id: r.id },
      update: { name: r.name, colorHex: r.colorHex, bgHex: r.bgHex, isSystem: r.isSystem },
      create: { id: r.id, name: r.name, colorHex: r.colorHex, bgHex: r.bgHex, isSystem: r.isSystem },
    });
    await prisma.rolePermission.deleteMany({ where: { roleId: r.id } });
    for (const key of r.perms) {
      await prisma.rolePermission.create({ data: { roleId: r.id, permissionKey: key } });
    }
  }

  console.log("Seeding users...");
  const passwordHash = await bcrypt.hash(SEED_PASSWORD, 12);
  for (const u of USERS) {
    await prisma.user.upsert({
      where: { id: u.id },
      update: { ...u, passwordHash },
      create: { ...u, passwordHash },
    });
  }

  console.log("Seeding connectors...");
  for (const c of CONNECTORS) {
    await prisma.connector.upsert({
      where: { id: c.id },
      update: { ...c, secrets: {} },
      create: { ...c, secrets: {} },
    });
  }

  console.log("Seeding unified datasets...");
  for (const t of TABLES) {
    const existing = await prisma.unifiedDataset.findFirst({ where: { connectorId: t.connectorId, name: t.name } });
    if (existing) {
      await prisma.unifiedDataset.update({ where: { id: existing.id }, data: { ...t, syncedAt: new Date() } });
    } else {
      await prisma.unifiedDataset.create({ data: { ...t, syncedAt: new Date() } });
    }
  }

  console.log("Seeding data sources...");
  for (const d of DOCUMENTS) {
    await prisma.dataSource.upsert({ where: { id: d.id }, update: d, create: d });
  }

  console.log(`Done. Seed login password for all personas: ${SEED_PASSWORD}`);
}

main()
  .catch((e) => {
    console.error(e);
    process.exit(1);
  })
  .finally(async () => {
    await prisma.$disconnect();
  });
