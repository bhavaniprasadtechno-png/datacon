-- Dashboards: per-user saved collections of chat insights ("dashlets").
-- Live data — a dashlet stores the original question, not a frozen result;
-- app/ai's /internal/chat/answer replays it on every dashboard view.
CREATE TABLE "dashboards" (
  "id"        TEXT NOT NULL,
  "orgId"     TEXT NOT NULL,
  "userId"    UUID NOT NULL,
  "name"      TEXT NOT NULL,
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updatedAt" TIMESTAMP(3) NOT NULL,
  CONSTRAINT "dashboards_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "dashlets" (
  "id"          TEXT NOT NULL,
  "orgId"       TEXT NOT NULL,
  "dashboardId" TEXT NOT NULL,
  "title"       TEXT NOT NULL,
  "text"        TEXT NOT NULL,
  "intent"      "Intent" NOT NULL,
  "question"    TEXT NOT NULL,
  "model"       TEXT,
  "payload"     JSONB NOT NULL,
  "createdAt"   TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT "dashlets_pkey" PRIMARY KEY ("id")
);

ALTER TABLE "dashboards" ADD CONSTRAINT "dashboards_orgId_fkey" FOREIGN KEY ("orgId") REFERENCES "organizations"("id") ON DELETE RESTRICT ON UPDATE CASCADE;
ALTER TABLE "dashboards" ADD CONSTRAINT "dashboards_userId_fkey" FOREIGN KEY ("userId") REFERENCES "users"("id") ON DELETE RESTRICT ON UPDATE CASCADE;
ALTER TABLE "dashlets" ADD CONSTRAINT "dashlets_orgId_fkey" FOREIGN KEY ("orgId") REFERENCES "organizations"("id") ON DELETE RESTRICT ON UPDATE CASCADE;
ALTER TABLE "dashlets" ADD CONSTRAINT "dashlets_dashboardId_fkey" FOREIGN KEY ("dashboardId") REFERENCES "dashboards"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- RLS: org-scoped, same shape as every other business-data table (see
-- 20260724000000_multi_tenant_workspaces/migration.sql). Per-user ownership
-- within an org (dashboards are private, not org-shared) is enforced at the
-- application layer in DashboardsService, exactly like Conversation/Message's
-- userId scoping.
--
-- No explicit GRANT is needed for app_user here: the multi-tenant migration
-- already set `ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT,
-- INSERT, UPDATE, DELETE ON TABLES TO app_user`, which covers tables created
-- afterwards, including these two.
CREATE POLICY org_isolation ON public.dashboards
  USING ("orgId" = current_setting('app.current_org_id', true));
CREATE POLICY org_isolation ON public.dashlets
  USING ("orgId" = current_setting('app.current_org_id', true));

ALTER TABLE public.dashboards ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.dashlets ENABLE ROW LEVEL SECURITY;
