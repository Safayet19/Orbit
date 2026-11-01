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
