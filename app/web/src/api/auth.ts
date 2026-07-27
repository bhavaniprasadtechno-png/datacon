import { useMutation } from "@tanstack/react-query";
import { api } from "./client";

export function useCompleteRegistration() {
  return useMutation({
    mutationFn: async (dto: { name: string; orgName: string }) => (await api.post("/auth/complete-registration", dto)).data,
  });
}
