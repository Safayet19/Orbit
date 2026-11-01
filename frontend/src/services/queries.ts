import { useQuery } from "@tanstack/react-query";
import { api } from "./api";
import type {
  CollectionRun,
  HistoryItem,
  Overview,
  Page,
  Quality,
  QualityIssue,
  RecordItem,
  RecordVersion,
  Source,
  SystemInfo,
} from "../types/api";

export function useOverview(period: number) {
  return useQuery({
    queryKey: ["overview", period],
    queryFn: () => api<Overview>(`/api/admin/overview?period=${period}`),
    refetchInterval: 60_000,
  });
}

export function useSources() {
  return useQuery({
    queryKey: ["sources"],
    queryFn: () => api<{ items: Source[]; total: number }>("/api/admin/sources"),
  });
}

export function useSource(sourceKey: string | undefined) {
  return useQuery({
    enabled: Boolean(sourceKey),
    queryKey: ["source", sourceKey],
    queryFn: () =>
      api<Record<string, unknown>>(`/api/admin/sources/${sourceKey}`),
  });
}

export function useRuns(page = 1, sourceId?: string) {
  const params = new URLSearchParams({ page: String(page), page_size: "20" });
  if (sourceId) params.set("source_id", sourceId);
  return useQuery({
    queryKey: ["runs", page, sourceId],
    queryFn: () => api<Page<CollectionRun>>(`/api/admin/collections?${params}`),
    refetchInterval: 4000,
  });
}

export function useRun(runId: string | undefined) {
  return useQuery({
    enabled: Boolean(runId),
    queryKey: ["run", runId],
    queryFn: () => api<CollectionRun>(`/api/admin/collections/${runId}`),
    refetchInterval: (query) =>
      query.state.data?.status === "running" ? 3000 : false,
  });
}

export function useRecords(params: URLSearchParams) {
  return useQuery({
    queryKey: ["records", params.toString()],
    queryFn: () =>
      api<Page<RecordItem>>(`/api/admin/records?${params.toString()}`),
  });
}

export function useRecord(recordId: string | undefined) {
  return useQuery({
    enabled: Boolean(recordId),
    queryKey: ["record", recordId],
    queryFn: () => api<RecordItem>(`/api/admin/records/${recordId}`),
  });
}

export function useVersions(recordId: string | undefined) {
  return useQuery({
    enabled: Boolean(recordId),
    queryKey: ["record-versions", recordId],
    queryFn: () =>
      api<{ items: RecordVersion[] }>(
        `/api/admin/records/${recordId}/versions`,
      ),
  });
}

export function useHistory(page: number) {
  return useQuery({
    queryKey: ["history", page],
    queryFn: () => api<Page<HistoryItem>>(`/api/admin/history?page=${page}&page_size=20`),
  });
}

export function useQuality() {
  return useQuery({
    queryKey: ["quality"],
    queryFn: () => api<Quality>("/api/admin/quality"),
  });
}

export function useQualityIssues(page: number) {
  return useQuery({
    queryKey: ["quality-issues", page],
    queryFn: () =>
      api<Page<QualityIssue>>(`/api/admin/quality/issues?page=${page}&page_size=20`),
  });
}

export function useSystemInfo() {
  return useQuery({
    queryKey: ["system"],
    queryFn: () => api<SystemInfo>("/api/admin/system"),
  });
}
