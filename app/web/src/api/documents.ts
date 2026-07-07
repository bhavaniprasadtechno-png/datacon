import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";
import type { DataSourcePreview, DataSourceRecord } from "../lib/types";

export function useDataSources() {
  return useQuery({
    queryKey: ["documents"],
    queryFn: async () => (await api.get<DataSourceRecord[]>("/documents")).data,
  });
}

export function useDataSourcePreview(id: string | null) {
  return useQuery({
    queryKey: ["documents", id, "preview"],
    queryFn: async () => (await api.get<DataSourcePreview>(`/documents/${id}/preview`)).data,
    enabled: !!id,
    retry: false,
  });
}

export function useUploadDataSource() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ file, onProgress }: { file: File; onProgress?: (pct: number) => void }) => {
      const form = new FormData();
      form.append("file", file);
      const res = await api.post<DataSourceRecord>("/documents", form, {
        headers: { "Content-Type": "multipart/form-data" },
        onUploadProgress: (evt) => {
          if (evt.total && onProgress) onProgress(Math.round((evt.loaded / evt.total) * 100));
        },
      });
      return res.data;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["documents"] }),
  });
}
