import { createClient, SupabaseClient } from "@supabase/supabase-js";

let cached: SupabaseClient | undefined;

/** Server-only Supabase client (service-role key). Used to verify bearer
 * tokens (getClaims) and for admin operations (inviting users). Never
 * import this from web/. */
export function getSupabaseAdminClient(): SupabaseClient {
  if (!cached) {
    const url = process.env.SUPABASE_URL;
    const serviceRoleKey = process.env.SUPABASE_SERVICE_ROLE_KEY;
    if (!url || !serviceRoleKey) {
      throw new Error("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set.");
    }
    cached = createClient(url, serviceRoleKey, {
      auth: { autoRefreshToken: false, persistSession: false },
    });
  }
  return cached;
}
