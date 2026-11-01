import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { api } from "./api";
import type {
  AgentDecisionItem,
  AgentJobItem,
  AgentSchedule,
  AgentStatus,
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
    queryFn: ({ signal }) =>
      api<Overview>(`/api/admin/overview?period=${period}`, { signal }),
    refetchInterval: (query) =>
      query.state.data?.running_runs ? 15_000 : 60_000,
  });
}

export function useApiHealth() {
  return useQuery({
    queryKey: ["api-health"],
    queryFn: ({ signal }) =>
      api<{ status: string }>("/health", { signal }),
    staleTime: 10_000,
    refetchInterval: 30_000,
  });
}

export function useSources() {
  return useQuery({
    queryKey: ["sources"],
    queryFn: ({ signal }) =>
      api<{ items: Source[]; total: number }>("/api/admin/sources", { signal }),
    staleTime: 5 * 60_000,
  });
}

export function useSource(sourceKey: string | undefined) {
  return useQuery({
    enabled: Boolean(sourceKey),
    queryKey: ["source", sourceKey],
    queryFn: ({ signal }) =>
      api<Record<string, unknown>>(`/api/admin/sources/${sourceKey}`, { signal }),
    staleTime: 60_000,
  });
}

export function useRuns(
  page = 1,
  sourceId?: string,
  pollActiveRuns = true,
) {
  const params = new URLSearchParams({ page: String(page), page_size: "20" });
  if (sourceId) params.set("source_id", sourceId);
  return useQuery({
    queryKey: ["runs", page, sourceId],
    queryFn: ({ signal }) =>
      api<Page<CollectionRun>>(`/api/admin/collections?${params}`, { signal }),
    refetchInterval: (query) =>
      pollActiveRuns &&
      query.state.data?.items.some((run) => run.status === "running")
        ? 30_000
        : 60_000,
  });
}

export function useRun(runId: string | undefined) {
  return useQuery({
    enabled: Boolean(runId),
    queryKey: ["run", runId],
    queryFn: ({ signal }) =>
      api<CollectionRun>(`/api/admin/collections/${runId}`, { signal }),
    refetchInterval: (query) =>
      query.state.data?.status === "running" ? 30_000 : false,
  });
}

export function useRecords(params: URLSearchParams, enabled = true) {
  return useQuery({
    queryKey: ["records", params.toString()],
    queryFn: ({ signal }) =>
      api<Page<RecordItem>>(`/api/admin/records?${params.toString()}`, { signal }),
    placeholderData: keepPreviousData,
    enabled,
  });
}

export function useRecord(recordId: string | undefined) {
  return useQuery({
    enabled: Boolean(recordId),
    queryKey: ["record", recordId],
    queryFn: ({ signal }) =>
      api<RecordItem>(`/api/admin/records/${recordId}`, { signal }),
  });
}

export function useVersions(recordId: string | undefined) {
  return useQuery({
    enabled: Boolean(recordId),
    queryKey: ["record-versions", recordId],
    queryFn: ({ signal }) =>
      api<{ items: RecordVersion[] }>(
        `/api/admin/records/${recordId}/versions`,
        { signal },
      ),
  });
}

export function useHistory(page: number) {
  return useQuery({
    queryKey: ["history", page],
    queryFn: ({ signal }) =>
      api<Page<HistoryItem>>(`/api/admin/history?page=${page}&page_size=20`, {
        signal,
      }),
    placeholderData: keepPreviousData,
  });
}

export function useQuality() {
  return useQuery({
    queryKey: ["quality"],
    queryFn: ({ signal }) => api<Quality>("/api/admin/quality", { signal }),
  });
}

export function useQualityIssues(page: number) {
  return useQuery({
    queryKey: ["quality-issues", page],
    queryFn: ({ signal }) =>
      api<Page<QualityIssue>>(`/api/admin/quality/issues?page=${page}&page_size=20`, {
        signal,
      }),
    placeholderData: keepPreviousData,
  });
}

export function useSystemInfo() {
  return useQuery({
    queryKey: ["system"],
    queryFn: ({ signal }) => api<SystemInfo>("/api/admin/system", { signal }),
  });
}

export function useAgentStatus() {
  return useQuery({
    queryKey: ["agent-status"],
    queryFn: ({ signal }) =>
      api<AgentStatus>("/api/admin/agent/status", { signal }),
    refetchInterval: (query) =>
      query.state.data?.active_jobs ? 30_000 : 60_000,
  });
}

export function useAgentSchedules() {
  return useQuery({
    queryKey: ["agent-schedules"],
    queryFn: ({ signal }) =>
      api<{ items: AgentSchedule[]; total: number }>(
        "/api/admin/agent/schedules",
        { signal },
      ),
    staleTime: 60_000,
    refetchInterval: 60_000,
  });
}

export function useAgentJobs(page = 1, sourceId?: string, state?: string) {
  const params = new URLSearchParams({ page: String(page), page_size: "20" });
  if (sourceId) params.set("source_id", sourceId);
  if (state) params.set("state", state);
  return useQuery({
    queryKey: ["agent-jobs", page, sourceId, state],
    queryFn: ({ signal }) =>
      api<Page<AgentJobItem>>(`/api/admin/agent/jobs?${params}`, { signal }),
    refetchInterval: (query) => {
      const now = Date.now();
      const hasReadyWork = query.state.data?.items.some(
        (job) =>
          job.status === "running" ||
          (["queued", "retry_wait"].includes(job.status) &&
            Date.parse(job.scheduled_at) <= now),
      );
      return hasReadyWork ? 30_000 : 60_000;
    },
  });
}

export function useAgentDecisions(page = 1, sourceId?: string) {
  const params = new URLSearchParams({ page: String(page), page_size: "20" });
  if (sourceId) params.set("source_id", sourceId);
  return useQuery({
    queryKey: ["agent-decisions", page, sourceId],
    queryFn: ({ signal }) =>
      api<Page<AgentDecisionItem>>(`/api/admin/agent/decisions?${params}`, {
        signal,
      }),
    staleTime: 60_000,
    refetchInterval: 60_000,
  });
}
