export interface AuthenticatedUser {
  username: string;
  csrf_token: string;
}

export interface Page<T> {
  items: T[];
  pagination: { page: number; page_size: number; total: number; pages: number };
}

export interface Source {
  id: string;
  name: string;
  source_key: string;
  category: string;
  source_type: string;
  official_url: string;
  enabled: boolean;
  last_collection_at: string | null;
  last_result: "running" | "completed" | "failed" | null;
  latest_record_count: number;
  latest_error: string | null;
  supported: boolean;
}

export interface CollectionRun {
  id: string;
  source_id: string;
  source_name: string;
  status: "running" | "completed" | "failed";
  started_at: string;
  completed_at: string | null;
  duration_seconds: number | null;
  records_fetched: number;
  records_new: number;
  records_changed: number;
  records_unchanged: number;
  records_invalid: number;
  error_summary: string | null;
  quality_status: AgentHealth;
}

export interface RecordItem {
  id: string;
  source_id: string;
  source_name: string;
  external_record_id: string;
  category: string;
  data: Record<string, unknown>;
  source_url: string;
  first_observed_at: string;
  last_observed_at: string;
  status: string;
  version_number: number;
}

export interface RecordVersion {
  id: string;
  version_number: number;
  data: Record<string, unknown>;
  fingerprint: string;
  observed_at: string;
  provenance: Record<string, unknown>;
  previous_data: Record<string, unknown> | null;
}

export interface HistoryItem {
  version_id: string;
  record_id: string;
  external_record_id: string;
  source_name: string;
  source_key: string;
  observed_at: string;
  version_number: number;
  previous_data: Record<string, unknown>;
  data: Record<string, unknown>;
}

export interface Overview {
  refreshed_at: string;
  total_records: number;
  registered_sources: number;
  successful_runs: number;
  failed_runs: number;
  running_runs: number;
  enabled_sources: number;
  stale_sources: number | null;
  chart: { date: string; new_records: number; changed_records: number; failed_runs: number }[];
  recent_runs: CollectionRun[];
  recent_changes: {
    version_id: string;
    record_id: string;
    external_record_id: string;
    source_name: string;
    version_number: number;
    observed_at: string;
    previous_data: Record<string, unknown>;
    data: Record<string, unknown>;
  }[];
}

export interface Quality {
  status: "healthy" | "warning" | "error" | "unknown";
  valid_records: number;
  invalid_records: number;
  failed_runs: number;
  sources_with_recent_errors: number;
  stale_sources: number;
  potential_duplicates: number | null;
  potential_duplicates_measurable: boolean;
}

export interface QualityIssue {
  id: string;
  source_name: string;
  source_key: string;
  run_id: string;
  external_record_id: string | null;
  error_details: { field: string; type: string }[];
  created_at: string;
  severity: "warning" | "error";
}

export interface SystemInfo {
  application: string;
  version: string;
  environment: string;
  api_status: string;
  database: {
    status: string;
    provider: string;
    name: string;
    tls_active: boolean;
    checked_at: string;
  };
  collectors: { source_id: string; name: string; category: string }[];
  scheduling: { configured: boolean; status: string };
}

export type AgentHealth = "healthy" | "degraded" | "failed" | "paused" | "unknown";

export interface AgentWorker {
  worker_id: string;
  status: "starting" | "idle" | "executing" | "stopping" | "unhealthy" | "offline";
  started_at: string;
  last_heartbeat_at: string;
  active_job_id: string | null;
  last_error: string | null;
  version: string;
}

export interface AgentStatus {
  checked_at: string;
  worker_online: boolean;
  workers: AgentWorker[];
  active_jobs: number;
  scheduled_jobs: number;
  scheduled_sources: number;
  next_execution_at: string | null;
  healthy_sources: number;
  degraded_sources: number;
  latest_success: {
    run_id: string;
    source_name: string;
    status: string;
    started_at: string;
    completed_at: string | null;
    quality_status: AgentHealth;
    error_summary: string | null;
  } | null;
  latest_failure: {
    run_id: string;
    source_name: string;
    status: string;
    started_at: string;
    completed_at: string | null;
    quality_status: AgentHealth;
    error_summary: string | null;
  } | null;
  successful_jobs: number;
  failed_jobs: number;
  average_duration_seconds: number | null;
  average_duration_sample_size: number;
  retry_count: number;
  worker_offline_after_seconds: number;
}

export interface AgentSchedule {
  source_id: string;
  source_name: string;
  approved: boolean;
  source_enabled: boolean;
  mode: "fixed" | "adaptive" | "paused";
  enabled: boolean;
  base_interval_seconds: number;
  minimum_interval_seconds: number;
  maximum_interval_seconds: number;
  priority: number;
  next_due_at: string | null;
  last_attempted_at: string | null;
  last_successful_at: string | null;
  consecutive_failures: number;
  consecutive_unchanged: number;
  health_status: AgentHealth;
  health_reason: string | null;
  quality_ratio: number | null;
  latest_run: {
    run_id: string;
    status: string;
    started_at: string;
    completed_at: string | null;
    quality_status: AgentHealth;
    records_fetched: number;
    records_invalid: number;
    error_summary: string | null;
  } | null;
}

export interface AgentDecisionItem {
  decision_id: string;
  source_name: string;
  source_id: string | null;
  job_id: string | null;
  decision_type: string;
  reason_code: string;
  explanation: string;
  context: Record<string, unknown>;
  created_at: string;
  next_action_at: string | null;
}

export interface AgentJobItem {
  job_id: string;
  source_id: string;
  source_name: string;
  trigger_type: "manual" | "scheduled";
  created_at: string;
  scheduled_at: string;
  started_at: string | null;
  completed_at: string | null;
  status: "queued" | "running" | "retry_wait" | "completed" | "failed" | "cancelled";
  attempt_count: number;
  worker_id: string | null;
  lease_expires_at: string | null;
  lease_generation: number;
  collection_run_id: string | null;
  failure_category: string | null;
  error_summary: string | null;
  quality_status: AgentHealth;
}
