import { lazy, Suspense, useEffect, useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Activity, AlertTriangle, Boxes, CircleCheck, Database, Play, Timer, type LucideIcon } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { api } from "../../services/api";
import { useOverview, useSources } from "../../services/queries";
import { Button, EmptyState, ErrorState, formatDateTime, formatDuration, LoadingState, MetricCard, PageHeader, Panel, StatusBadge } from "../../components/ui/Primitives";
import { useToast } from "../../components/ui/Toast";
import { ConfirmationDialog } from "../../components/ui/ConfirmationDialog";
import type { Source } from "../../types/api";

const ActivityChart = lazy(() =>
  import("../../components/charts/ActivityChart").then((module) => ({
    default: module.ActivityChart,
  })),
);

export default function OverviewPage() {
  const mounted = useRef(false);
  const [period, setPeriod] = useState(30);
  const [pendingSource, setPendingSource] = useState<Source | null>(null);
  const { data, isLoading, isError, error, refetch } = useOverview(period);
  const sources = useSources();
  const navigate = useNavigate();
  const notify = useToast();
  const queryClient = useQueryClient();
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const startCollection = useMutation({
    mutationFn: (sourceId: string) =>
      api<{ run_id: string }>("/api/admin/collections", {
        method: "POST",
        body: JSON.stringify({ source_id: sourceId }),
      }),
    onSuccess: async (result) => {
      notify("success", `Collection started · ${result.run_id}`);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["overview"] }),
        queryClient.invalidateQueries({ queryKey: ["runs"] }),
        queryClient.invalidateQueries({ queryKey: ["agent-status"] }),
      ]);
      if (mounted.current) navigate(`/operations?run=${result.run_id}`);
    },
  });

  if (isLoading) return <LoadingState />;
  if (isError || !data) {
    return <ErrorState message={error instanceof Error ? error.message : "Overview is unavailable."} retry={() => void refetch()} />;
  }

  return (
    <>
      <PageHeader
        title="Overview"
        description="Monitor your collection network, data growth, and operational health."
        refreshedAt={data.refreshed_at}
        action={<Button variant="secondary" onClick={() => navigate("/operations")}><Activity size={16} /> Operations</Button>}
      />
      <div className="metric-grid">
        <MetricCard label="Total records" value={data.total_records} supporting="Current validated observations" icon={Database} tone="copper" />
        <MetricCard label="Registered sources" value={data.registered_sources} supporting={`${data.enabled_sources} enabled`} icon={Boxes} tone="blue" />
        <MetricCard label="Successful runs" value={data.successful_runs} supporting="All-time completed collections" icon={CircleCheck} tone="green" />
        <MetricCard label="Failed runs" value={data.failed_runs} supporting="Review operational issues" icon={AlertTriangle} tone="red" />
      </div>

      <div className="overview-grid">
        <Panel
          title="Collection activity"
          action={
            <div className="chart-toolbar" aria-label="Chart time period">
              {[7, 30, 90].map((days) => (
                <button
                  type="button"
                  className={`range-button ${period === days ? "active" : ""}`}
                  aria-pressed={period === days}
                  key={days}
                  onClick={() => setPeriod(days)}
                >
                  {days}D
                </button>
              ))}
            </div>
          }
          className="chart-panel"
        >
          <Suspense fallback={<LoadingState label="Loading chart" />}>
            <ActivityChart data={data.chart} />
          </Suspense>
        </Panel>
        <Panel title="Agent health">
          <div className="health-list">
            <HealthRow label="Jobs running" value={data.running_runs} tone="amber" icon={Timer} />
            <HealthRow label="Completed jobs" value={data.successful_runs} tone="green" icon={CircleCheck} />
            <HealthRow label="Failed jobs" value={data.failed_runs} tone="red" icon={AlertTriangle} />
            <HealthRow label="Enabled sources" value={data.enabled_sources} tone="blue" icon={Boxes} />
            <HealthRow label="Stale sources · 7 days" value={data.stale_sources ?? "Unknown"} tone="amber" icon={Timer} />
          </div>
          <div className="source-quick-action">
            <span>Approved collectors</span>
            {sources.data?.items.filter((source) => source.enabled && source.supported).map((source) => (
              <Button
                key={source.source_key}
                variant="secondary"
                disabled={data.running_runs > 0 || startCollection.isPending}
                onClick={() => setPendingSource(source)}
              >
                <Play size={14} /> Run {source.name}
              </Button>
            ))}
            {(!sources.data || !sources.data.items.some((source) => source.enabled && source.supported)) && (
              <span className="table-secondary">No enabled collector is available.</span>
            )}
          </div>
        </Panel>
      </div>

      <div className="overview-lower">
        <Panel title="Recent collection runs" action={<button className="text-link" onClick={() => navigate("/operations")}>View all</button>}>
          {data.recent_runs.length ? (
            <div className="table-wrap">
              <table className="data-table">
                <thead><tr><th>Source</th><th>Started</th><th>Duration</th><th>New</th><th>Changed</th><th>Status</th></tr></thead>
                <tbody>
                  {data.recent_runs.slice(0, 6).map((run) => (
                    <tr key={run.id}>
                      <td><span className="table-primary">{run.source_name}</span></td>
                      <td>{formatDateTime(run.started_at)}</td>
                      <td>{formatDuration(run.duration_seconds)}</td>
                      <td className="mono">{run.records_new}</td>
                      <td className="mono">{run.records_changed}</td>
                      <td>
                        <div className="table-action-cell">
                          <StatusBadge status={run.status} />
                          <button className="text-link" onClick={() => navigate(`/operations?run=${run.id}`)}>Details</button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : <EmptyState title="No collection runs yet" description="Start a registered collector to see its execution history here." />}
        </Panel>
        <Panel title="Recent record changes" action={<button className="text-link" onClick={() => navigate("/history")}>View history</button>}>
          {data.recent_changes.length ? (
            <div className="activity-list">
              {data.recent_changes.map((change) => (
                <button className="activity-item" key={change.version_id} onClick={() => navigate(`/records/${change.record_id}`)}>
                  <span className="activity-marker" />
                  <span className="activity-copy">
                    <strong>{change.external_record_id}</strong>
                    <span>{change.source_name} · version {change.version_number}</span>
                    <time>{formatDateTime(change.observed_at)}</time>
                  </span>
                </button>
              ))}
            </div>
          ) : <EmptyState title="No changes detected" description="Meaningful record updates will appear after a source returns changed values." />}
        </Panel>
      </div>
      <ConfirmationDialog
        open={pendingSource !== null}
        onOpenChange={(open) => {
          if (!open) setPendingSource(null);
        }}
        title="Start data collection?"
        description={`Start a new collection for ${pendingSource?.name ?? "this source"}? Orbit will retrieve source data, validate it, and update stored records when changes are detected.`}
        confirmLabel="Start collection"
        pendingLabel="Starting…"
        errorFallback="Collection could not be started. Please try again."
        onConfirm={async () => {
          if (!pendingSource?.enabled || !pendingSource.supported) {
            throw new Error("This source is not enabled for approved collection.");
          }
          await startCollection.mutateAsync(pendingSource.source_key);
        }}
      />
    </>
  );
}

function HealthRow({
  label,
  value,
  tone,
  icon: Icon,
}: {
  label: string;
  value: number | string;
  tone: string;
  icon: LucideIcon;
}) {
  return (
    <div className="health-row">
      <span className={`health-label health-${tone}`}><Icon size={16} /> {label}</span>
      <strong className="health-value">{typeof value === "number" ? value.toLocaleString() : value}</strong>
    </div>
  );
}
