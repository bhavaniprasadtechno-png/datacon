import axios from "axios";
import { supabase } from "../lib/supabaseClient";

export const api = axios.create({
  baseURL: "/api",
});

api.interceptors.request.use(async (config) => {
  const { data } = await supabase.auth.getSession();
  if (data.session?.access_token) {
    config.headers.Authorization = `Bearer ${data.session.access_token}`;
  }
  return config;
});

export interface ApiErrorShape {
  message: string | string[];
  statusCode: number;
}

export function apiErrorMessage(err: unknown, fallback = "Something went wrong."): string {
  if (axios.isAxiosError(err)) {
    const data = err.response?.data as ApiErrorShape | undefined;
    if (data?.message) return Array.isArray(data.message) ? data.message.join(" ") : data.message;
  }
  return fallback;
}
