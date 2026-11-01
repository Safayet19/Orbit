import {
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  AlertTriangle,
  Clock3,
  Pause,
  Play,
  RefreshCw,
  ShieldCheck,
  Timer,
  Wifi,
  WifiOff,
} from "lucide-react";
import {
  useBeforeUnload,
  useBlocker,
  useSearchParams,
} from "react-router-dom";
import { ConfirmationDialog } from "../../components/ui/ConfirmationDialog";
import {
  Button,
  EmptyState,
  ErrorState,
  formatDateTime,
  formatDuration,
  LoadingState,
  MetricCard,
  PageHeader,
  Pagination,
  Panel,
  StatusBadge,
} from "../../components/ui/Primitives";
import { useToast } from "../../components/ui/Toast";
import { api, userFacingError } from "../../services/api";
import {
  useAgentDecisions,
  useAgentJobs,
  useAgentSchedules,
  useAgentStatus,
  useRun,
  useRuns,
  useSources,
} from "../../services/queries";
import type { AgentSchedule, AgentStatus, CollectionRun } from "../../types/api";

type ScheduleAction = "pause" | "resume" | "enable";
type ScheduleChanges = {
  mode?: "fixed" | "adaptive" | "paused";
  enabled?: boolean;
  base_interval_seconds?: number;
  priority?: number;
};
type ScheduleUpdateResult = {
  mode: "fixed" | "adaptive" | "paused";
  enabled: boolean;
  base_interval_seconds: number;
  priority: number;
};

export default function OperationsPage() {
  const mounted = useRef(false);
  const [params, setParams] = useSearchParams();
  const selectedRunId = params.get("run") ?? undefined;
  const [manualSourceId, setManualSourceId] = useState("");
  const [filterSourceId, setFilterSourceId] = useState("");
  const [jobState, setJobState] = useState("");
  const [decisionPage, setDecisionPage] = useState(1);
  const [runConfirmationOpen, setRunConfirmationOpen] = useState(false);
  const [scheduleConfirmation, setScheduleConfirmation] = useState<{
    schedule: AgentSchedule;
    action: ScheduleAction;
  } | null>(null);
  const [dirtySchedules, setDirtySchedules] = useState<Record<string, true>>({});
  const [savingSchedules, setSavingSchedules] = useState<Record<string, true>>({});
  const status = useAgentStatus();
  const schedules = useAgentSchedules();
  const jobs = useAgentJobs(1, filterSourceId || undefined, jobState || undefined);
  const decisions = useAgentDecisions(decisionPage, filterSourceId || undefined);
  const runs = useRuns(1, undefined, !selectedRunId);
  const sources = useSources();
  const selectedRun = useRun(selectedRunId);
  const notify = useToast();
  const client = useQueryClient();
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const refreshAgent = async (
    queryKeys: string[][] = [
      ["agent-status"],
      ["agent-schedules"],
      ["agent-jobs"],
      ["agent-decisions"],
      ["runs"],
      ["sources"],
    ],
  ) => {
    await Promise.all(
      queryKeys.map((queryKey) => client.invalidateQueries({ queryKey })),
    );
  };

  const start = useMutation({
    mutationFn: (id: string) =>
      api<{ run_id: string; status: string }>("/api/admin/collections", {
        method: "POST",
        body: JSON.stringify({ source_id: id }),
      }),
    onSuccess: async (result) => {
        if (mounted.current) setParams({ run: result.run_id });
      notify("success", `Collection run started · ${result.run_id}`);
      await refreshAgent();
    },
  });

  const updateSchedule = useMutation({
    mutationFn: ({
      sourceKey,
      changes,
    }: {
      sourceKey: string;
      changes: ScheduleChanges;
      successMessage?: string;
    }) =>
      api<ScheduleUpdateResult>(
        `/api/admin/agent/schedules/${encodeURIComponent(sourceKey)}`,
        {
          method: "PATCH",
          body: JSON.stringify(changes),
        },
      ),
    onSuccess: async (_result, { successMessage }) => {
      notify("success", successMessage ?? "Scheduling policy updated.");
      await refreshAgent([
        ["agent-status"],
        ["agent-schedules"],
        ["agent-decisions"],
      ]);
    },
  });

  const toggleSchedule = useMutation({
    mutationFn: ({ sourceKey, paused }: { sourceKey: string; paused: boolean }) =>
      api(
        `/api/admin/agent/schedules/${encodeURIComponent(sourceKey)}/${paused ? "resume" : "pause"}`,
        { method: "POST" },
      ),
    onSuccess: async (_result, { paused }) => {
      notify("success", paused ? "Automatic scheduling resumed." : "Automatic scheduling paused.");
      await refreshAgent([
        ["agent-status"],
        ["agent-schedules"],
        ["agent-decisions"],
      ]);
    },
  });

  const eligible =
    sources.data?.items.filter((source) => source.enabled && source.supported) ?? [];
  const selectedSource = eligible.find(
    (source) => source.source_key === manualSourceId,
  );
  const hasUnsavedChanges = Object.keys(dirtySchedules).length > 0;
  const hasPendingScheduleSave = Object.keys(savingSchedules).length > 0;
  const blocker = useBlocker(
    ({ currentLocation, nextLocation }) =>
      hasUnsavedChanges &&
      currentLocation.pathname !== nextLocation.pathname,
  );
  useEffect(() => {
    if (blocker.state === "blocked" && !hasUnsavedChanges) {
      blocker.proceed();
    }
  }, [blocker, hasUnsavedChanges]);
  useBeforeUnload(
    useCallback(
      (event) => {
        if (hasUnsavedChanges) {
          event.preventDefault();
          event.returnValue = "";
        }
      },
      [hasUnsavedChanges],
    ),
  );
  const updateScheduleDirtyState = useCallback(
    (sourceKey: string, dirty: boolean) => {
      setDirtySchedules((current) => {
        if (dirty) {
          return current[sourceKey] ? current : { ...current, [sourceKey]: true };
        }
        if (!current[sourceKey]) return current;
        const next = { ...current };
        delete next[sourceKey];
        return next;
      });
    },
    [],
  );
  const updateScheduleSavingState = useCallback(
    (sourceKey: string, saving: boolean) => {
      setSavingSchedules((current) => {
        if (saving) {
          return current[sourceKey] ? current : { ...current, [sourceKey]: true };
        }
        if (!current[sourceKey]) return current;
        const next = { ...current };
        delete next[sourceKey];
        return next;
      });
    },
    [],
  );
  const confirmScheduleAction = async () => {
    if (!scheduleConfirmation) return;
    const { schedule, action } = scheduleConfirmation;
    if (action === "enable") {
      await updateSchedule.mutateAsync({
        sourceKey: schedule.source_id,
        changes: { enabled: true },
        successMessage: "Automatic scheduling enabled.",
      });
      return;
    }
    await toggleSchedule.mutateAsync({
      sourceKey: schedule.source_id,
      paused: action === "resume",
    });
  };
  const workerError = status.isError || schedules.isError;
  const overview = status.data;

  return (
    <>
      <PageHeader
        title="Agent Control Center"
        description="Monitor the independent worker, review explainable decisions, and manage approved collection schedules."
        refreshedAt={overview?.checked_at}
        action={
          <Button
            variant="secondary"
            onClick={() => void refreshAgent()}
            aria-label="Refresh agent status"
          >
            <RefreshCw size={15} />
            Refresh
          </Button>
        }
      />

      {workerError && (
        <ErrorState
          message={
            status.isError
              ? "Agent status is unavailable."
              : "Agent schedules are unavailable."
          }
          retry={() => {
            void status.refetch();
            void schedules.refetch();
          }}
        />
      )}

      <div className="metric-grid operations-metrics">
        <MetricCard
          label="Worker"
          value={overview ? (overview.worker_online ? "Online" : "Offline") : "—"}
          supporting={
            overview?.workers[0]
              ? `${overview.workers[0].worker_id} · heartbeat ${formatDateTime(overview.workers[0].last_heartbeat_at)}`
              : "No fresh worker heartbeat"
          }
          icon={overview?.worker_online ? Wifi : WifiOff}
          tone={overview?.worker_online ? "green" : "red"}
        />
        <MetricCard
          label="Active jobs"
          value={overview?.active_jobs ?? "—"}
          supporting={`${overview?.scheduled_jobs ?? "—"} scheduled or queued`}
          icon={Activity}
          tone="blue"
        />
        <MetricCard
          label="Source health"
          value={
            overview
              ? `${overview.healthy_sources} healthy · ${overview.degraded_sources} degraded`
              : "—"
          }
          supporting="Based on persisted quality and execution results"
          icon={ShieldCheck}
          tone={overview?.degraded_sources ? "red" : "green"}
        />
        <MetricCard
          label="Next collection"
          value={
            overview?.next_execution_at
              ? formatDateTime(overview.next_execution_at)
              : "Not scheduled"
          }
          supporting={`${overview?.successful_jobs ?? 0} completed · ${overview?.failed_jobs ?? 0} failed`}
          icon={Clock3}
        />
      </div>

      <div className="agent-overview-grid">
        <Panel title="Worker status" className="agent-worker-panel">
          {status.isError ? (
            <ErrorState
              message="Worker status could not be loaded."
              retry={() => void status.refetch()}
            />
          ) : status.isLoading ? (
            <LoadingState />
          ) : overview?.workers.length ? (
            <div className="worker-list">
              {overview.workers.map((worker) => (
                <div className="worker-row" key={worker.worker_id}>
                  <div className="worker-icon">
                    {worker.status === "offline" ? (
                      <WifiOff size={17} />
                    ) : (
                      <Wifi size={17} />
                    )}
                  </div>
                  <div className="worker-details">
                    <strong>{worker.worker_id}</strong>
                    <span>
                      Started {formatDateTime(worker.started_at)} · heartbeat{" "}
                      {formatDateTime(worker.last_heartbeat_at)}
                    </span>
                    {worker.active_job_id && (
                      <span className="mono">Active job {worker.active_job_id}</span>
                    )}
                    {worker.last_error && (
                      <span className="agent-error-text">{worker.last_error}</span>
                    )}
                  </div>
                  <StatusBadge status={worker.status} />
                </div>
              ))}
              <div className="worker-footnote">
                Offline when no heartbeat has been seen for{" "}
                {overview.worker_offline_after_seconds} seconds.
              </div>
            </div>
          ) : (
            <EmptyState
              title="Worker is offline"
              description="Start the autonomous worker in a separate terminal to begin scheduled collection."
            />
          )}
        </Panel>

        <Panel title="Recent execution summary">
          <div className="agent-run-summary">
            <RunSummary title="Latest successful run" run={overview?.latest_success} />
            <RunSummary title="Latest failed run" run={overview?.latest_failure} />
            <div className="agent-summary-stat">
              <Timer size={16} />
              <span>
                30-day average duration:{" "}
                {overview?.average_duration_seconds == null
                  ? "Not available"
                  : formatDuration(overview.average_duration_seconds)}
              </span>
            </div>
            <div className="agent-summary-stat">
              <AlertTriangle size={16} />
              <span>{overview?.retry_count ?? 0} jobs have been retried</span>
            </div>
          </div>
        </Panel>
      </div>

      <Panel title="Run an approved collection" className="run-control-panel">
        <div className="run-control">
          <div>
            <strong>Manual collection</strong>
            <span>Manual runs use the same persistent job and lease protections.</span>
          </div>
          <label className="run-source-select">
            Source
            <select
              className="control"
              value={manualSourceId}
              onChange={(event) => setManualSourceId(event.target.value)}
              aria-label="Select source for manual collection"
              disabled={start.isPending}
              required
            >
              <option value="">Select a source</option>
              {eligible.map((source) => (
                <option key={source.id} value={source.source_key}>
                  {source.name}
                </option>
              ))}
            </select>
          </label>
          <Button
            disabled={!selectedSource || start.isPending}
            onClick={() => setRunConfirmationOpen(true)}
          >
            <Play size={15} />
            {start.isPending ? "Starting…" : "Run collection"}
          </Button>
        </div>
        {sources.isError ? (
          <ErrorState
            message="Approved source list could not be loaded."
            retry={() => void sources.refetch()}
          />
        ) : !eligible.length ? (
          <div className="notice" style={{ marginTop: 13 }}>
            No enabled, approved collector is currently available.
          </div>
        ) : null}
      </Panel>

      <Panel title="Scheduled collections" className="agent-panel">
        {schedules.isLoading ? (
          <LoadingState />
        ) : schedules.isError ? (
          <ErrorState
            message="Scheduled collection policies could not be loaded."
            retry={() => void schedules.refetch()}
          />
        ) : !schedules.data?.items.length ? (
          <EmptyState
            title="No schedules registered"
            description="Start the autonomous worker once to register the approved source policies."
          />
        ) : (
          <div className="table-wrap">
            <table className="data-table agent-schedule-table">
              <thead>
                <tr>
                  <th>Source</th>
                  <th>Mode</th>
                  <th>Interval</th>
                  <th>Last execution</th>
                  <th>Next execution</th>
                  <th>Priority</th>
                  <th>Health</th>
                  <th>Schedule</th>
                </tr>
              </thead>
              <tbody>
                {schedules.data.items.map((schedule) => (
                  <ScheduleRow
                    key={schedule.source_id}
                    schedule={schedule}
                    disabled={
                      updateSchedule.isPending || toggleSchedule.isPending
                    }
                    onSave={(changes) =>
                      updateSchedule.mutateAsync({
                        sourceKey: schedule.source_id,
                        changes,
                      })
                    }
                    onAction={(action) =>
                      setScheduleConfirmation({ schedule, action })
                    }
                    onDirtyChange={updateScheduleDirtyState}
                    onSavingChange={updateScheduleSavingState}
                  />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      <Panel
        title="Agent decisions"
        className="agent-panel"
        action={
          <select
            className="control agent-filter"
            value={filterSourceId}
            onChange={(event) => {
              setFilterSourceId(event.target.value);
              setDecisionPage(1);
            }}
            aria-label="Filter decisions by source"
          >
            <option value="">All sources</option>
            {schedules.data?.items.map((source) => (
              <option key={source.source_id} value={source.source_id}>
                {source.source_name}
              </option>
            ))}
          </select>
        }
      >
        {decisions.isLoading ? (
          <LoadingState />
        ) : decisions.isError || !decisions.data ? (
          <ErrorState
            message="Decision history is unavailable."
            retry={() => void decisions.refetch()}
          />
        ) : decisions.data.items.length ? (
          <>
            <div className="agent-decision-list">
              {decisions.data.items.map((decision) => (
                <article className="agent-decision" key={decision.decision_id}>
                  <span className="decision-mark" aria-hidden="true" />
                  <div className="decision-body">
                    <div className="decision-heading">
                      <strong>{decision.source_name}</strong>
                      <StatusBadge status={decision.decision_type} />
                      <time>{formatDateTime(decision.created_at)}</time>
                    </div>
                    <p>{decision.explanation}</p>
                    <div className="decision-meta">
                      <span>{decision.reason_code.replaceAll("_", " ")}</span>
                      {decision.next_action_at && (
                        <span>Next action {formatDateTime(decision.next_action_at)}</span>
                      )}
                      {decision.job_id && (
                        <span className="mono">Job {decision.job_id}</span>
                      )}
                    </div>
                  </div>
                </article>
              ))}
            </div>
            <Pagination
              page={decisions.data.pagination.page}
              pages={decisions.data.pagination.pages}
              total={decisions.data.pagination.total}
              onChange={setDecisionPage}
            />
          </>
        ) : (
          <EmptyState
            title="No agent decisions recorded"
            description="The worker records explainable decisions when it evaluates schedules and job outcomes."
          />
        )}
      </Panel>

      <Panel
        title="Recent jobs and activity"
        className="agent-panel"
        action={
          <div className="agent-filter-group">
            <select
              className="control agent-filter"
              value={filterSourceId}
              onChange={(event) => setFilterSourceId(event.target.value)}
              aria-label="Filter jobs by source"
            >
              <option value="">All sources</option>
              {schedules.data?.items.map((source) => (
                <option key={source.source_id} value={source.source_id}>
                  {source.source_name}
                </option>
              ))}
            </select>
            <select
              className="control agent-filter"
              value={jobState}
              onChange={(event) => setJobState(event.target.value)}
              aria-label="Filter jobs by status"
            >
              <option value="">All outcomes</option>
              <option value="running">Running</option>
              <option value="queued">Queued</option>
              <option value="retry_wait">Retry waiting</option>
              <option value="failed">Failed</option>
              <option value="completed">Completed</option>
            </select>
          </div>
        }
      >
        {jobs.isLoading ? (
          <LoadingState />
        ) : jobs.isError || !jobs.data ? (
          <ErrorState
            message="Agent job history is unavailable."
            retry={() => void jobs.refetch()}
          />
        ) : jobs.data.items.length ? (
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Source</th>
                  <th>Trigger</th>
                  <th>Created</th>
                  <th>Attempts</th>
                  <th>Quality</th>
                  <th>Status</th>
                  <th>Details</th>
                </tr>
              </thead>
              <tbody>
                {jobs.data.items.map((job) => (
                  <tr key={job.job_id}>
                    <td className="table-primary">{job.source_name}</td>
                    <td>{job.trigger_type}</td>
                    <td>{formatDateTime(job.created_at)}</td>
                    <td className="mono">{job.attempt_count}</td>
                    <td>
                      <StatusBadge status={job.quality_status} />
                    </td>
                    <td>
                      <StatusBadge status={job.status} />
                    </td>
                    <td>
                      {job.error_summary ? (
                        <span className="agent-error-text">{job.error_summary}</span>
                      ) : job.collection_run_id ? (
                        <button
                          className="text-link"
                          onClick={() => setParams({ run: job.collection_run_id! })}
                        >
                          View collection
                        </button>
                      ) : (
                        <span className="subtle-text">No details</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState
            title="No jobs recorded"
            description="Scheduled and administrator-requested collections appear here."
          />
        )}
      </Panel>

      {selectedRunId && (
        <Panel
          title="Selected collection run"
          className="agent-panel"
          action={
            <button className="text-link" onClick={() => setParams({})}>
              Close
            </button>
          }
        >
          {selectedRun.isLoading ? (
            <LoadingState />
          ) : selectedRun.isError || !selectedRun.data ? (
            <ErrorState
              message="Collection run details are unavailable."
              retry={() => void selectedRun.refetch()}
            />
          ) : (
            <RunDetails run={selectedRun.data} />
          )}
        </Panel>
      )}

      <Panel title="Collection history" className="agent-panel">
        {runs.isLoading ? (
          <LoadingState />
        ) : runs.isError || !runs.data ? (
          <ErrorState
            message="Collection history is unavailable."
            retry={() => void runs.refetch()}
          />
        ) : runs.data.items.length ? (
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Source</th>
                  <th>Started</th>
                  <th>Fetched</th>
                  <th>New</th>
                  <th>Changed</th>
                  <th>Invalid</th>
                  <th>Quality</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {runs.data.items.map((run) => (
                  <tr key={run.id}>
                    <td className="table-primary">{run.source_name}</td>
                    <td>{formatDateTime(run.started_at)}</td>
                    <td className="mono">{run.records_fetched}</td>
                    <td className="mono">{run.records_new}</td>
                    <td className="mono">{run.records_changed}</td>
                    <td className="mono">{run.records_invalid}</td>
                    <td>
                      <StatusBadge status={run.quality_status} />
                    </td>
                    <td>
                      <StatusBadge status={run.status} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState
            title="No runs recorded"
            description="Start a registered collector or enable autonomous scheduling."
          />
        )}
      </Panel>
      <ConfirmationDialog
        open={runConfirmationOpen}
        onOpenChange={setRunConfirmationOpen}
        title="Start data collection?"
        description={`Start a new collection for ${selectedSource?.name ?? "this source"}? Orbit will retrieve source data, validate it, and update stored records when changes are detected.`}
        confirmLabel="Start collection"
        pendingLabel="Starting…"
        errorFallback="Collection could not be started. Please try again."
        onConfirm={async () => {
          if (!selectedSource?.enabled || !selectedSource.supported) {
            throw new Error("Select an enabled source with an approved collector.");
          }
          await start.mutateAsync(selectedSource.source_key);
        }}
      />
      {scheduleConfirmation && (
        <ConfirmationDialog
          open
          onOpenChange={(open) => {
            if (!open) setScheduleConfirmation(null);
          }}
          title={
            scheduleConfirmation.action === "pause"
              ? "Pause automatic collection?"
              : scheduleConfirmation.action === "resume"
                ? "Resume automatic collection?"
                : "Enable automatic scheduling?"
          }
          description={
            scheduleConfirmation.action === "pause"
              ? `Automatic scheduling for ${scheduleConfirmation.schedule.source_name} will be paused. This does not cancel a collection that is already running.`
              : scheduleConfirmation.action === "resume"
                ? `Orbit will resume scheduling collection jobs for ${scheduleConfirmation.schedule.source_name} according to its configured policy.`
                : scheduleConfirmation.schedule.mode === "paused"
                  ? `Orbit will enable scheduling for ${scheduleConfirmation.schedule.source_name}. Its existing pause will remain in effect until you resume it.`
                  : `Orbit will begin applying the configured collection schedule for ${scheduleConfirmation.schedule.source_name}.`
          }
          confirmLabel={
            scheduleConfirmation.action === "pause"
              ? "Pause scheduling"
              : scheduleConfirmation.action === "resume"
                ? "Resume scheduling"
                : "Enable scheduling"
          }
          pendingLabel="Updating schedule…"
          errorFallback="Unable to update the schedule. Please try again."
          onConfirm={confirmScheduleAction}
        />
      )}
      <ConfirmationDialog
        open={blocker.state === "blocked"}
        onOpenChange={(open) => {
          if (!open && blocker.state === "blocked") blocker.reset();
        }}
        title="Discard unsaved changes?"
        confirmLabel="Discard changes"
        cancelLabel="Keep editing"
        pendingLabel="Leaving…"
        confirmDisabled={hasPendingScheduleSave}
        description={
          hasPendingScheduleSave
            ? "A schedule change is being saved. Keep editing until the save finishes."
            : "You have changes that haven't been saved. Leaving this page will discard them."
        }
        onConfirm={() => {
          if (blocker.state === "blocked") blocker.proceed();
        }}
      />
    </>
  );
}

function ScheduleRow({
  schedule,
  disabled,
  onSave,
  onAction,
  onDirtyChange,
  onSavingChange,
}: {
  schedule: AgentSchedule;
  disabled: boolean;
  onSave: (changes: ScheduleChanges) => Promise<ScheduleUpdateResult>;
  onAction: (action: ScheduleAction) => void;
  onDirtyChange: (sourceKey: string, dirty: boolean) => void;
  onSavingChange: (sourceKey: string, saving: boolean) => void;
}) {
  const savedMode = schedule.mode === "fixed" ? "fixed" : "adaptive";
  const savedIntervalHours = String(
    Math.max(1, Math.round(schedule.base_interval_seconds / 3600)),
  );
  const savedPriority = String(schedule.priority);
  const [mode, setMode] = useState<"fixed" | "adaptive">(savedMode);
  const [intervalHours, setIntervalHours] = useState(savedIntervalHours);
  const [priority, setPriority] = useState(savedPriority);
  const [baseline, setBaseline] = useState({
    mode: savedMode,
    intervalHours: savedIntervalHours,
    priority: savedPriority,
  });
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const intervalRef = useRef<HTMLInputElement>(null);
  const priorityRef = useRef<HTMLInputElement>(null);
  const id = useId();
  const isDirty =
    mode !== baseline.mode ||
    intervalHours !== baseline.intervalHours ||
    priority !== baseline.priority;
  const minimumHours = Math.max(
    1,
    Math.ceil(schedule.minimum_interval_seconds / 3600),
  );
  const maximumHours = Math.floor(
    Math.min(schedule.maximum_interval_seconds, 7_776_000) / 3600,
  );
  const intervalValue = Number(intervalHours);
  const intervalError =
    intervalHours.trim() === ""
      ? "Interval is required."
      : !Number.isInteger(intervalValue)
        ? "Enter a whole number of hours."
        : intervalValue < minimumHours
          ? `Minimum interval is ${minimumHours} hours.`
          : intervalValue > maximumHours
            ? `Maximum interval is ${maximumHours} hours.`
            : null;
  const priorityValue = Number(priority);
  const priorityError =
    priority.trim() === ""
      ? "Priority is required."
      : !Number.isInteger(priorityValue)
        ? "Enter a whole-number priority."
        : priorityValue < 1 || priorityValue > 10
          ? "Priority must be between 1 and 10."
          : null;

  useEffect(() => {
    if (isDirty || saving) return;
    setMode(savedMode);
    setIntervalHours(savedIntervalHours);
    setPriority(savedPriority);
    setBaseline({
      mode: savedMode,
      intervalHours: savedIntervalHours,
      priority: savedPriority,
    });
  }, [
    isDirty,
    savedIntervalHours,
    savedMode,
    savedPriority,
    saving,
  ]);

  useEffect(() => {
    onDirtyChange(schedule.source_id, isDirty);
  }, [isDirty, onDirtyChange, schedule.source_id]);

  const save = async () => {
    setSaveError(null);
    if (intervalError) {
      intervalRef.current?.focus();
      return;
    }
    if (priorityError) {
      priorityRef.current?.focus();
      return;
    }
    if (!isDirty || saving) return;

    setSaving(true);
    onSavingChange(schedule.source_id, true);
    try {
      const result = await onSave({
        mode,
        base_interval_seconds: Math.round(intervalValue * 3600),
        priority: priorityValue,
      });
      const next: {
        mode: "fixed" | "adaptive";
        intervalHours: string;
        priority: string;
      } = {
        mode: result.mode === "fixed" ? "fixed" : "adaptive",
        intervalHours: String(
          Math.max(1, Math.round(result.base_interval_seconds / 3600)),
        ),
        priority: String(result.priority),
      };
      setMode(next.mode);
      setIntervalHours(next.intervalHours);
      setPriority(next.priority);
      setBaseline(next);
      onDirtyChange(schedule.source_id, false);
    } catch (reason) {
      setSaveError(
        userFacingError(reason, "Unable to save the schedule. Please try again."),
      );
    } finally {
      setSaving(false);
      onSavingChange(schedule.source_id, false);
    }
  };

  const scheduleAction: ScheduleAction = !schedule.enabled
    ? "enable"
    : schedule.mode === "paused"
      ? "resume"
      : "pause";
  const canEdit =
    schedule.approved &&
    schedule.source_enabled &&
    schedule.enabled &&
    schedule.mode !== "paused";

  return (
    <tr>
      <td>
        <strong className="table-primary">{schedule.source_name}</strong>
        <span className="schedule-source-key">{schedule.source_id}</span>
      </td>
      <td>
        <select
          className="control schedule-select"
          value={mode}
          onChange={(event) => {
            if (event.target.value === "fixed" || event.target.value === "adaptive") {
              setMode(event.target.value);
            }
          }}
          aria-label={`Scheduling mode for ${schedule.source_name}`}
          disabled={!canEdit || disabled || saving}
        >
          <option value="adaptive">Adaptive</option>
          <option value="fixed">Fixed</option>
        </select>
      </td>
      <td>
        <label className="schedule-inline-input">
          <input
            type="number"
            className="agent-number"
            ref={intervalRef}
            id={`${id}-interval`}
            min={minimumHours}
            max={maximumHours}
            step="1"
            value={intervalHours}
            required
            aria-invalid={Boolean(intervalError)}
            aria-describedby={intervalError ? `${id}-interval-error` : undefined}
            onChange={(event) => setIntervalHours(event.target.value)}
            aria-label={`Base interval hours for ${schedule.source_name}`}
            disabled={!canEdit || disabled || saving}
          />
          <span>hours</span>
        </label>
        {intervalError && (
          <span className="schedule-field-error" id={`${id}-interval-error`} role="alert">
            {intervalError}
          </span>
        )}
      </td>
      <td>
        {schedule.last_successful_at
          ? formatDateTime(schedule.last_successful_at)
          : "Never"}
        {schedule.consecutive_failures > 0 && (
          <span className="schedule-source-key">
            {schedule.consecutive_failures} consecutive failures
          </span>
        )}
      </td>
      <td>
        {schedule.next_due_at ? formatDateTime(schedule.next_due_at) : "Not scheduled"}
      </td>
      <td>
        <input
          type="number"
          className="agent-number agent-priority"
          ref={priorityRef}
          id={`${id}-priority`}
          min="1"
          max="10"
          step="1"
          value={priority}
          required
          aria-invalid={Boolean(priorityError)}
          aria-describedby={priorityError ? `${id}-priority-error` : undefined}
          onChange={(event) => setPriority(event.target.value)}
          aria-label={`Priority for ${schedule.source_name}`}
          disabled={!canEdit || disabled || saving}
        />
        {priorityError && (
          <span className="schedule-field-error" id={`${id}-priority-error`} role="alert">
            {priorityError}
          </span>
        )}
      </td>
      <td>
        <StatusBadge status={schedule.health_status} />
        {schedule.health_reason && (
          <span className="schedule-source-key">{schedule.health_reason}</span>
        )}
        {schedule.quality_ratio !== null && (
          <span className="schedule-source-key">
            {Math.round(schedule.quality_ratio * 100)}% valid
          </span>
        )}
      </td>
      <td>
        <div className="schedule-actions">
          <Button
            variant="secondary"
            disabled={
              disabled ||
              saving ||
              !canEdit ||
              !isDirty
            }
            onClick={() => void save()}
          >
            {saving ? "Saving…" : "Save"}
          </Button>
          <Button
            variant={schedule.mode === "paused" || !schedule.enabled ? "primary" : "quiet"}
            disabled={
              disabled ||
              saving ||
              isDirty ||
              !schedule.approved ||
              !schedule.source_enabled
            }
            title={
              isDirty
                ? "Save or discard policy changes before changing the schedule."
                : undefined
            }
            onClick={() => onAction(scheduleAction)}
            aria-label={`${!schedule.enabled ? "Enable" : schedule.mode === "paused" ? "Resume" : "Pause"} ${schedule.source_name}`}
          >
            {!schedule.enabled ? (
              <>
                <Play size={14} /> Enable
              </>
            ) : schedule.mode === "paused" ? (
              <>
                <Play size={14} /> Resume
              </>
            ) : (
              <>
                <Pause size={14} /> Pause
              </>
            )}
          </Button>
        </div>
        {saveError && (
          <span className="schedule-save-error" role="alert">
            {saveError}
          </span>
        )}
      </td>
    </tr>
  );
}

function RunSummary({
  title,
  run,
}: {
  title: string;
  run: AgentStatus["latest_success"] | undefined;
}) {
  return (
    <div className="agent-run-summary-item">
      <span>{title}</span>
      {run ? (
        <>
          <strong>{run.source_name}</strong>
          <span>
            {formatDateTime(run.completed_at ?? run.started_at)} ·{" "}
            <StatusBadge status={run.quality_status} />
          </span>
          {run.error_summary && <span className="agent-error-text">{run.error_summary}</span>}
        </>
      ) : (
        <span>No matching run recorded</span>
      )}
    </div>
  );
}

function RunDetails({ run }: { run: CollectionRun }) {
  return (
    <div className="detail-grid">
      <Detail label="Source">{run.source_name}</Detail>
      <Detail label="Started">{formatDateTime(run.started_at)}</Detail>
      <Detail label="Completed">{formatDateTime(run.completed_at)}</Detail>
      <Detail label="Duration">{formatDuration(run.duration_seconds)}</Detail>
      <Detail label="Fetched">{run.records_fetched}</Detail>
      <Detail label="New">{run.records_new}</Detail>
      <Detail label="Changed">{run.records_changed}</Detail>
      <Detail label="Unchanged">{run.records_unchanged}</Detail>
      <Detail label="Invalid">{run.records_invalid}</Detail>
      <Detail label="Quality">{run.quality_status}</Detail>
      {run.error_summary && <Detail label="Sanitized error">{run.error_summary}</Detail>}
    </div>
  );
}

function Detail({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="detail-cell">
      <span>{label}</span>
      <strong>{children}</strong>
    </div>
  );
}
