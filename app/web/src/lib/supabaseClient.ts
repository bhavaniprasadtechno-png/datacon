import { createClient } from "@supabase/supabase-js";

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL || "https://yicblouwgguhmfvwqdhm.supabase.co";
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY || "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InlpY2Jsb3V3Z2d1aG1mdndxZGhtIiwicm9sZSI6ImFub24iLCJpYXQiOjE3MjE3NDAyMTMsImV4cCI6MjAzNzMxNjIxM30.dummy";

export const supabase = createClient(supabaseUrl, supabaseAnonKey);
