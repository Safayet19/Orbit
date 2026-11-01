import { useMemo, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Activity, CircleCheck, Play, Timer } from "lucide-react";
import { useSearchParams } from "react-router-dom";
import { Button, EmptyState, ErrorState, formatDateTime, formatDuration, LoadingState, PageHeader, Panel, StatusBadge } from "../../components/ui/Primitives";
import { useToast } from "../../components/ui/Toast";
import { api } from "../../services/api";
import { useRun, useRuns, useSources } from "../../services/queries";

export default function OperationsPage() {
  const [params, setParams] = useSearchParams();
  const selectedRunId = params.get("run") ?? undefined;
  const [sourceId, setSourceId] = useState("");
  const runs = useRuns(1);
  const sources = useSources();
  const selectedRun = useRun(selectedRunId);
  const notify = useToast();
  const client = useQueryClient();
  const start = useMutation({
    mutationFn: (id: string) =>
      api<{ run_id: string; status: string }>("/api/admin/collections", {
        method: "POST",
        body: JSON.stringify({ source_id: id }),
      }),
    onSuccess: async (result) => {
      setParams({ run: result.run_id });
      notify("success", `Collection run started · ${result.run_id}`);
      await client.invalidateQueries({ queryKey: ["runs"] });
    },
    onError: (reason) => notify("error", reason instanceof Error ? reason.message : "Collection could not start."),
  });
  const eligible = sources.data?.items.filter((source) => source.enabled && source.supported) ?? [];
  const activeRuns = useMemo(
    () => runs.data?.items.filter((run) => run.status === "running").length ?? 0,
    [runs.data],
  );
  const detail = selectedRun.data;

  return (
    <>
      <PageHeader title="Agent operations" description="Start approved collectors and monitor their persisted execution state." />
      <div className="metric-grid operations-metrics">
        <Metric label="Running now" value={activeRuns} icon={Activity} />
        <Metric label="Latest runs" value={runs.data?.pagination.total ?? "—"} icon={Timer} />
        <Metric label="Available collectors" value={eligible.length} icon={CircleCheck} />
      </div>
      <Panel title="Run a collector" className="run-control-panel">
        <div className="run-control">
          <div>
            <strong>Approved source</strong>
            <span>Runs execute in-process and are recorded in collection history.</span>
          </div>
          <select className="control" value={sourceId} onChange={(event) => setSourceId(event.target.value)} aria-label="Select approved source">
            <option value="">Select a source</option>
            {eligible.map((source) => <option key={source.id} value={source.source_key}>{source.name}</option>)}
          </select>
          <Button disabled={!sourceId || start.isPending} onClick={() => start.mutate(sourceId)}><Play size={15} /> {start.isPending ? "Starting…" : "Run collection"}</Button>
        </div>
        {!eligible.length && <div className="notice" style={{ marginTop: 13 }}>No enabled, approved collector is currently available.</div>}
      </Panel>
      {detail && (
        <Panel title="Selected run status" className="selected-run-panel">
          <div className="run-detail-heading"><div><strong>{detail.source_name}</strong><span className="mono">{detail.id}</span></div><StatusBadge status={detail.status} /></div>
          <div className="detail-grid">
            <Detail label="Started">{formatDateTime(detail.started_at)}</Detail>
            <Detail label="Completed">{formatDateTime(detail.completed_at)}</Detail>
            <Detail label="Duration">{formatDuration(detail.duration_seconds)}</Detail>
            <Detail label="Fetched">{detail.records_fetched}</Detail>
            <Detail label="New">{detail.records_new}</Detail>
            <Detail label="Changed">{detail.records_changed}</Detail>
            <Detail label="Unchanged">{detail.records_unchanged}</Detail>
            <Detail label="Invalid">{detail.records_invalid}</Detail>
            {detail.error_summary && <Detail label="Sanitized error">{detail.error_summary}</Detail>}
          </div>
        </Panel>
      )}
      <Panel title="Execution history">
        {runs.isLoading ? <LoadingState /> : runs.isError || !runs.data ? (
          <ErrorState message="Collection history is unavailable." retry={() => void runs.refetch()} />
        ) : runs.data.items.length ? (
          <div className="table-wrap"><table className="data-table">
            <thead><tr><th>Source</th><th>Started</th><th>Duration</th><th>Fetched</th><th>New</th><th>Changed</th><th>Invalid</th><th>Status</th><th>Details</th></tr></thead>
            <tbody>{runs.data.items.map((run) => (
              <tr key={run.id}>
                <td className="table-primary">{run.source_name}</td><td>{formatDateTime(run.started_at)}</td><td>{formatDuration(run.duration_seconds)}</td>
                <td className="mono">{run.records_fetched}</td><td className="mono">{run.records_new}</td><td className="mono">{run.records_changed}</td><td className="mono">{run.records_invalid}</td><td><StatusBadge status={run.status} /></td>
                <td><button className="text-link" onClick={() => setParams({ run: run.id })}>View details</button></td>
              </tr>
            ))}</tbody>
          </table></div>
        ) : <EmptyState title="No runs recorded" description="Start a registered collector to create the first execution record." />}
      </Panel>
    </>
  );
}

function Metric({ label, value, icon: Icon }: { label: string; value: number | string; icon: typeof Activity }) {
  return <div className="metric-card compact-metric"><div className="metric-top"><span className="metric-label">{label}</span><span className="metric-icon tone-blue"><Icon size={17} /></span></div><strong className="metric-value">{value}</strong></div>;
}

function Detail({ label, children }: { label: string; children: React.ReactNode }) {
  return <div className="detail-cell"><span>{label}</span><strong>{children}</strong></div>;
}
