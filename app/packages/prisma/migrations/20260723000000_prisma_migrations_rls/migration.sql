-- Close the RLS gap Supabase's advisor flagged after the auth migration:
-- every other public table already has RLS enabled with zero policies
-- (deny-all for anon/authenticated), but Prisma's own bookkeeping table
-- was missed since it's created by `prisma migrate` itself, not by an
-- app migration. No policies needed here either -- Prisma's privileged
-- connection bypasses RLS the same way it does for every other table.
ALTER TABLE public._prisma_migrations ENABLE ROW LEVEL SECURITY;
