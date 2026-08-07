import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";
import type { ChatIntent } from "@datacon/shared-types";
import type { ChatPayload } from "../lib/types";

export type DashletIntent = Exclude<ChatIntent, "general">;

export interface DashboardSummary {
  id: string;
  name: string;
  dashletCount: number;
  updatedAt: string;
}

export interface DashletView {
  id: string;
  title: string;
  text: string;
  intent: ChatIntent;
  payload: ChatPayload;
}

export interface DashboardDetail {
  id: string;
  name: string;
  dashlets: DashletView[];
}

export interface SaveDashletInput {
  dashboardId?: string;
  name?: string;
  title: string;
  text: string;
  intent: DashletIntent;
  payload: ChatPayload;
}

export function useDashboards() {
  return useQuery({
    queryKey: ["dashboards"],
    queryFn: async () => (await api.get<DashboardSummary[]>("/dashboards")).data,
  });
}

export function useDashboard(id: string) {
  return useQuery({
    queryKey: ["dashboard", id],
    queryFn: async () => (await api.get<DashboardDetail>(`/dashboards/${id}`)).data,
    enabled: !!id,
  });
}

export function useSaveDashboard() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (input: SaveDashletInput) => (await api.post<DashboardDetail>("/dashboards/save", input)).data,
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ["dashboards"] });
      qc.invalidateQueries({ queryKey: ["dashboard", data.id] });
    },
  });
}

export function useDeleteDashlet() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ dashboardId, dashletId }: { dashboardId: string; dashletId: string }) =>
      api.delete(`/dashboards/${dashboardId}/dashlets/${dashletId}`),
    onSuccess: (_data, { dashboardId }) => {
      qc.invalidateQueries({ queryKey: ["dashboard", dashboardId] });
      qc.invalidateQueries({ queryKey: ["dashboards"] });
    },
  });
}
