-- Drop legacy refresh-token bookkeeping (Supabase Auth owns session lifecycle now)
DROP TABLE "refresh_tokens";

-- Drop FK constraints that reference users.id so its type can change
ALTER TABLE "data_sources" DROP CONSTRAINT "data_sources_uploadedById_fkey";
ALTER TABLE "conversations" DROP CONSTRAINT "conversations_userId_fkey";
ALTER TABLE "feedback" DROP CONSTRAINT "feedback_userId_fkey";

-- users.id now comes from Supabase Auth (auth.users.id), not Prisma's cuid()
ALTER TABLE "users" ALTER COLUMN "id" TYPE UUID USING "id"::uuid;
ALTER TABLE "data_sources" ALTER COLUMN "uploadedById" TYPE UUID USING "uploadedById"::uuid;
ALTER TABLE "conversations" ALTER COLUMN "userId" TYPE UUID USING "userId"::uuid;
ALTER TABLE "feedback" ALTER COLUMN "userId" TYPE UUID USING "userId"::uuid;

-- Re-add the FK constraints
ALTER TABLE "data_sources" ADD CONSTRAINT "data_sources_uploadedById_fkey" FOREIGN KEY ("uploadedById") REFERENCES "users"("id") ON DELETE RESTRICT ON UPDATE CASCADE;
ALTER TABLE "conversations" ADD CONSTRAINT "conversations_userId_fkey" FOREIGN KEY ("userId") REFERENCES "users"("id") ON DELETE RESTRICT ON UPDATE CASCADE;
ALTER TABLE "feedback" ADD CONSTRAINT "feedback_userId_fkey" FOREIGN KEY ("userId") REFERENCES "users"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- Drop local-credential columns (Supabase Auth owns passwords/sessions)
ALTER TABLE "users" DROP COLUMN "passwordHash";
ALTER TABLE "users" DROP COLUMN "tokenVersion";

-- Auto-provision a public.users profile row (default "viewer" role) whenever
-- someone signs up directly through supabase-js (self-serve register flow).
-- Requires the "viewer" role to already exist (seed.ts creates it) —
-- signups before the first seed run will fail with an FK violation.
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER SET search_path = public
AS $$
DECLARE
  full_name text := COALESCE(NEW.raw_user_meta_data ->> 'name', split_part(NEW.email, '@', 1));
BEGIN
  -- "updatedAt" has no DB-level default (Prisma's @updatedAt is applied by
  -- Prisma Client on writes it makes, not as a column default), so this
  -- trigger — which bypasses Prisma entirely — must supply it explicitly.
  INSERT INTO public.users (id, email, name, initials, "roleId", "updatedAt")
  VALUES (NEW.id, NEW.email, full_name, upper(left(full_name, 1)), 'viewer', now())
  ON CONFLICT (id) DO NOTHING;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();

-- Lock every public table out of Supabase's auto-generated PostgREST API.
-- Only NestJS (connecting as the privileged `postgres` role, which bypasses
-- RLS) talks to this database — the anon/authenticated roles used by
-- supabase-js in the browser should never reach these tables directly.
-- No policies are added: the app has no browser-side Postgres access path,
-- so zero policies (deny-all for anon/authenticated) is the correct state.
ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.roles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.permissions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.role_permissions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.connectors ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.unified_datasets ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.data_sources ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.feedback ENABLE ROW LEVEL SECURITY;
