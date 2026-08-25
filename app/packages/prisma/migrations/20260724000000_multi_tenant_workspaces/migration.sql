-- ── New tables ──
CREATE TABLE "organizations" (
  "id" TEXT NOT NULL,
  "name" TEXT NOT NULL,
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updatedAt" TIMESTAMP(3) NOT NULL,
  CONSTRAINT "organizations_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "platform_admins" (
  "id" UUID NOT NULL,
  "email" TEXT NOT NULL,
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT "platform_admins_pkey" PRIMARY KEY ("id")
);
CREATE UNIQUE INDEX "platform_admins_email_key" ON "platform_admins"("email");

-- Single existing workspace: every row created before this migration belongs here.
INSERT INTO "organizations" ("id", "name", "updatedAt")
VALUES ('acme-corp', 'Acme Corp', now());

-- ── orgId: add nullable, backfill, then require ──
ALTER TABLE "users" ADD COLUMN "orgId" TEXT;
ALTER TABLE "roles" ADD COLUMN "orgId" TEXT;
ALTER TABLE "connectors" ADD COLUMN "orgId" TEXT;
ALTER TABLE "unified_datasets" ADD COLUMN "orgId" TEXT;
ALTER TABLE "data_sources" ADD COLUMN "orgId" TEXT;
ALTER TABLE "conversations" ADD COLUMN "orgId" TEXT;
ALTER TABLE "messages" ADD COLUMN "orgId" TEXT;
ALTER TABLE "feedback" ADD COLUMN "orgId" TEXT;

UPDATE "users" SET "orgId" = 'acme-corp';
UPDATE "roles" SET "orgId" = 'acme-corp';
UPDATE "connectors" SET "orgId" = 'acme-corp';
UPDATE "unified_datasets" SET "orgId" = 'acme-corp';
UPDATE "data_sources" SET "orgId" = 'acme-corp';
UPDATE "conversations" SET "orgId" = 'acme-corp';
UPDATE "messages" SET "orgId" = 'acme-corp';
UPDATE "feedback" SET "orgId" = 'acme-corp';

ALTER TABLE "users" ALTER COLUMN "orgId" SET NOT NULL;
ALTER TABLE "roles" ALTER COLUMN "orgId" SET NOT NULL;
ALTER TABLE "connectors" ALTER COLUMN "orgId" SET NOT NULL;
ALTER TABLE "unified_datasets" ALTER COLUMN "orgId" SET NOT NULL;
ALTER TABLE "data_sources" ALTER COLUMN "orgId" SET NOT NULL;
ALTER TABLE "conversations" ALTER COLUMN "orgId" SET NOT NULL;
ALTER TABLE "messages" ALTER COLUMN "orgId" SET NOT NULL;
ALTER TABLE "feedback" ALTER COLUMN "orgId" SET NOT NULL;

ALTER TABLE "users" ADD CONSTRAINT "users_orgId_fkey" FOREIGN KEY ("orgId") REFERENCES "organizations"("id") ON DELETE RESTRICT ON UPDATE CASCADE;
ALTER TABLE "roles" ADD CONSTRAINT "roles_orgId_fkey" FOREIGN KEY ("orgId") REFERENCES "organizations"("id") ON DELETE RESTRICT ON UPDATE CASCADE;
ALTER TABLE "connectors" ADD CONSTRAINT "connectors_orgId_fkey" FOREIGN KEY ("orgId") REFERENCES "organizations"("id") ON DELETE RESTRICT ON UPDATE CASCADE;
ALTER TABLE "unified_datasets" ADD CONSTRAINT "unified_datasets_orgId_fkey" FOREIGN KEY ("orgId") REFERENCES "organizations"("id") ON DELETE RESTRICT ON UPDATE CASCADE;
ALTER TABLE "data_sources" ADD CONSTRAINT "data_sources_orgId_fkey" FOREIGN KEY ("orgId") REFERENCES "organizations"("id") ON DELETE RESTRICT ON UPDATE CASCADE;
ALTER TABLE "conversations" ADD CONSTRAINT "conversations_orgId_fkey" FOREIGN KEY ("orgId") REFERENCES "organizations"("id") ON DELETE RESTRICT ON UPDATE CASCADE;
ALTER TABLE "messages" ADD CONSTRAINT "messages_orgId_fkey" FOREIGN KEY ("orgId") REFERENCES "organizations"("id") ON DELETE RESTRICT ON UPDATE CASCADE;
ALTER TABLE "feedback" ADD CONSTRAINT "feedback_orgId_fkey" FOREIGN KEY ("orgId") REFERENCES "organizations"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- ── Remove the old single-tenant auto-provisioning trigger ──
-- Self-registration now creates the Organization/Roles/User itself via
-- POST /auth/complete-registration — a plpgsql trigger is the wrong place
-- for that much logic.
DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
DROP FUNCTION IF EXISTS public.handle_new_user();

-- ── Non-bypassing runtime role ──
-- The existing DATABASE_URL/DIRECT_URL role (`postgres`) owns every table
-- and therefore always bypasses RLS regardless of policies, by Postgres's
-- table-owner rule. Prisma's *runtime* connection (DATABASE_URL only — NOT
-- DIRECT_URL, which `prisma migrate` still uses via the owning role) must
-- switch to a non-owning role with no BYPASSRLS for RLS to mean anything.
DO $$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'app_user') THEN
    CREATE ROLE app_user WITH LOGIN PASSWORD 'k6VoeQYsVTjpQH6dGZIPl5iMfuBFYW-O';
  END IF;
END $$;
GRANT USAGE ON SCHEMA public TO app_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO app_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_user;

-- ── RLS policies ──
-- permissions/platform_admins: global, not org data — permissive so the
-- non-bypassing app_user role can still read them at all (RLS was enabled
-- with zero policies for every public table by the prior auth migration,
-- which was a correct deny-all *until now* — these two tables need an
-- explicit allow, since they're not workspace-scoped).
CREATE POLICY permissions_readable ON public.permissions USING (true);
CREATE POLICY platform_admins_readable ON public.platform_admins USING (true);

-- organizations: a member can see their own org; Platform Admin (real or
-- bootstrapping a brand-new org via complete-registration) sees/creates any.
CREATE POLICY org_isolation ON public.organizations
  USING ("id" = current_setting('app.current_org_id', true)
         OR current_setting('app.is_platform_admin', true) = 'true');

-- users/roles: org-scoped, but Platform Admin bypasses (its one allowed
-- cross-org capability).
CREATE POLICY org_isolation ON public.users
  USING ("orgId" = current_setting('app.current_org_id', true)
         OR current_setting('app.is_platform_admin', true) = 'true');
CREATE POLICY org_isolation ON public.roles
  USING ("orgId" = current_setting('app.current_org_id', true)
         OR current_setting('app.is_platform_admin', true) = 'true');

-- role_permissions has no orgId of its own — join to its Role's orgId.
CREATE POLICY org_isolation ON public.role_permissions
  USING (EXISTS (
    SELECT 1 FROM roles r WHERE r.id = role_permissions."roleId"
      AND (r."orgId" = current_setting('app.current_org_id', true)
           OR current_setting('app.is_platform_admin', true) = 'true')
  ));

-- Business data: org-scoped, NO Platform Admin bypass — structurally
-- unreadable to Platform Admin even via a raw query.
CREATE POLICY org_isolation ON public.connectors
  USING ("orgId" = current_setting('app.current_org_id', true));
CREATE POLICY org_isolation ON public.unified_datasets
  USING ("orgId" = current_setting('app.current_org_id', true));
CREATE POLICY org_isolation ON public.data_sources
  USING ("orgId" = current_setting('app.current_org_id', true));
CREATE POLICY org_isolation ON public.conversations
  USING ("orgId" = current_setting('app.current_org_id', true));
CREATE POLICY org_isolation ON public.messages
  USING ("orgId" = current_setting('app.current_org_id', true));
CREATE POLICY org_isolation ON public.feedback
  USING ("orgId" = current_setting('app.current_org_id', true));

ALTER TABLE public.organizations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.platform_admins ENABLE ROW LEVEL SECURITY;
