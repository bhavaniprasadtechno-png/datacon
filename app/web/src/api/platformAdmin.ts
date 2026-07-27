import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";

export type AccountStatus = "ACTIVE" | "SUSPENDED";

export interface Organization {
  id: string;
  name: string;
  createdAt: string;
  status: AccountStatus;
  _count: { users: number };
}

export interface OrgUser {
  id: string;
  name: string;
  email: string;
  roleId: string;
  initials: string;
  avatarGrad: string;
  status: AccountStatus;
  role: { name: string };
}

export function useOrganizations() {
  return useQuery({
    queryKey: ["platform-admin", "organizations"],
    queryFn: async () => (await api.get<Organization[]>("/platform-admin/organizations")).data,
  });
}

export function useCreateOrganization() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (dto: { name: string; adminEmail: string; adminName: string }) =>
      (await api.post<Organization>("/platform-admin/organizations", dto)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["platform-admin", "organizations"] }),
  });
}

export function useSetOrganizationStatus() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ orgId, status }: { orgId: string; status: AccountStatus }) =>
      (await api.patch<Organization>(`/platform-admin/organizations/${orgId}/status`, { status })).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["platform-admin", "organizations"] }),
  });
}

export function useOrgUsers(orgId: string | undefined) {
  return useQuery({
    queryKey: ["platform-admin", "organizations", orgId, "users"],
    queryFn: async () => (await api.get<OrgUser[]>(`/platform-admin/organizations/${orgId}/users`)).data,
    enabled: !!orgId,
  });
}

export function useSetUserStatus() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ orgId, userId, status }: { orgId: string; userId: string; status: AccountStatus }) =>
      (await api.patch<OrgUser>(`/platform-admin/organizations/${orgId}/users/${userId}/status`, { status })).data,
    onSuccess: (_data, vars) =>
      qc.invalidateQueries({ queryKey: ["platform-admin", "organizations", vars.orgId, "users"] }),
  });
}
