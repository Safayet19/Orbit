import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, ExternalLink, Globe2, Play, Search, ShieldCheck, ToggleLeft, ToggleRight } from "lucide-react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ConfirmationDialog } from "../../components/ui/ConfirmationDialog";
import { Button, EmptyState, ErrorState, formatDateTime, formatDuration, LoadingState, PageHeader, Panel, StatusBadge } from "../../components/ui/Primitives";
import { useToast } from "../../components/ui/Toast";
import { api } from "../../services/api";
import { useSource, useSources } from "../../services/queries";
import type { CollectionRun, Source } from "../../types/api";

export default function SourcesPage() {
  const { sourceKey } = useParams();
  return sourceKey ? <SourceDetail sourceKey={sourceKey} /> : <SourceList />;
}

function SourceList() {
  const { data, isLoading, isError, error, refetch } = useSources();
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("all");
  const [state, setState] = useState("all");
  const [pendingToggle, setPendingToggle] = useState<{
    source: Source;
    enabled: boolean;
  } | null>(null);
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const notify = useToast();
  const mutation = useMutation({
    mutationFn: ({ source, enabled }: { source: Source; enabled: boolean }) =>
      api(`/api/admin/sources/${encodeURIComponent(source.source_key)}/enabled`, {
        method: "PATCH",
        body: JSON.stringify({ enabled }),
      }),
    onSuccess: async (_result, { source, enabled }) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["sources"] }),
        queryClient.invalidateQueries({
          queryKey: ["source", source.source_key],
        }),
        queryClient.invalidateQueries({ queryKey: ["agent-schedules"] }),
        queryClient.invalidateQueries({ queryKey: ["agent-status"] }),
      ]);
      notify("success", enabled ? "Source enabled." : "Source disabled.");
    },
  });
  const categories = useMemo(
    () => [...new Set(data?.items.map((source) => source.category) ?? [])],
    [data?.items],
  );
  const rows = (data?.items ?? []).filter((source) => {
    const matchesText =
      !search ||
      source.name.toLowerCase().includes(search.toLowerCase()) ||
      source.source_key.toLowerCase().includes(search.toLowerCase());
    const matchesCategory = category === "all" || source.category === category;
    const matchesState =
      state === "all" ||
      (state === "enabled" ? source.enabled : !source.enabled);
    return matchesText && matchesCategory && matchesState;
  });

  if (isLoading) return <LoadingState />;
  if (isError || !data) return <ErrorState message={error instanceof Error ? error.message : "Sources are unavailable."} retry={() => void refetch()} />;

  return (
    <>
      <PageHeader title="Data sources" description="Manage approved collection sources and review their latest outcomes." />
      <Panel>
        <div className="toolbar">
          <div className="input-wrap"><Search size={16} /><input className="control" aria-label="Search data sources" placeholder="Search sources" value={search} onChange={(event) => setSearch(event.target.value)} /></div>
          <select className="control filter-select" aria-label="Filter by category" value={category} onChange={(event) => setCategory(event.target.value)}>
            <option value="all">All categories</option>
            {categories.map((item) => <option value={item} key={item}>{item.replaceAll("_", " ")}</option>)}
          </select>
          <select className="control filter-select" aria-label="Filter by source status" value={state} onChange={(event) => setState(event.target.value)}>
            <option value="all">All states</option><option value="enabled">Enabled</option><option value="disabled">Disabled</option>
          </select>
        </div>
        {rows.length ? (
          <div className="table-wrap">
            <table className="data-table">
              <thead><tr><th>Source</th><th>Category</th><th>Type</th><th>State</th><th>Last collection</th><th>Latest result</th><th>Records</th><th>Actions</th></tr></thead>
              <tbody>
                {rows.map((source) => (
                  <tr key={source.id}>
                    <td><Link className="source-title" to={`/sources/${encodeURIComponent(source.source_key)}`}><span className="source-icon"><Globe2 size={16} /></span><span><strong>{source.name}</strong><span>{source.source_key}</span></span></Link></td>
                    <td>{source.category.replaceAll("_", " ")}</td>
                    <td>{source.source_type}</td>
                    <td><StatusBadge status={source.enabled ? "enabled" : "disabled"} /></td>
                    <td>{formatDateTime(source.last_collection_at)}</td>
                    <td><StatusBadge status={source.last_result} /></td>
                    <td className="mono">{source.latest_record_count.toLocaleString()}</td>
                    <td><div className="table-action-cell">
                      <button className="icon-button" title={!source.supported && !source.enabled ? "No approved collector is registered for this source" : source.enabled ? "Disable source" : "Enable source"} aria-label={`${source.enabled ? "Disable" : "Enable"} ${source.name}`} disabled={mutation.isPending || (!source.supported && !source.enabled)} onClick={() => {
                        const next = !source.enabled;
                        if (next && !source.supported) {
                          notify("error", "No approved collector is registered for this source.");
                          return;
                        }
                        setPendingToggle({ source, enabled: next });
                      }}>{source.enabled ? <ToggleRight size={19} /> : <ToggleLeft size={19} />}</button>
                      <button className="text-link" onClick={() => navigate(`/sources/${encodeURIComponent(source.source_key)}`)}>Details</button>
                    </div></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : <EmptyState title="No matching sources" description="Adjust the search or filters to see registered sources." />}
        <div className="table-footnote"><ShieldCheck size={14} /> Only registered, approved collectors can be run.</div>
      </Panel>
      {pendingToggle && (
        <ConfirmationDialog
          open
          onOpenChange={(open) => {
            if (!open) setPendingToggle(null);
          }}
          title={
            pendingToggle.enabled
              ? "Enable this data source?"
              : "Disable this data source?"
          }
          description={
            pendingToggle.enabled
              ? `This will make ${pendingToggle.source.name} available for approved collection operations. Any existing scheduling rules will follow their current configuration.`
              : `Collection will be disabled for ${pendingToggle.source.name}. Existing collected records and history will remain available.`
          }
          confirmLabel={pendingToggle.enabled ? "Enable source" : "Disable source"}
          pendingLabel="Updating source…"
          errorFallback="Unable to update the source. Please try again."
          onConfirm={async () => {
            if (pendingToggle.enabled && !pendingToggle.source.supported) {
              throw new Error("No approved collector is registered for this source.");
            }
            await mutation.mutateAsync(pendingToggle);
          }}
        />
      )}
    </>
  );
}

function SourceDetail({ sourceKey }: { sourceKey: string }) {
  const mounted = useRef(false);
  const { data, isLoading, isError, error, refetch } = useSource(sourceKey);
  const navigate = useNavigate();
  const notify = useToast();
  const queryClient = useQueryClient();
  const [runConfirmationOpen, setRunConfirmationOpen] = useState(false);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  const start = useMutation({
    mutationFn: (sourceId: string) =>
      api<{ run_id: string }>("/api/admin/collections", {
        method: "POST",
        body: JSON.stringify({ source_id: sourceId }),
      }),
    onSuccess: async (response) => {
      notify("success", `Collection started · ${response.run_id}`);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["runs"] }),
        queryClient.invalidateQueries({ queryKey: ["overview"] }),
        queryClient.invalidateQueries({ queryKey: ["agent-status"] }),
      ]);
      if (mounted.current) navigate(`/operations?run=${response.run_id}`);
    },
  });

  if (isLoading) return <LoadingState />;
  if (isError || !data) return <ErrorState message={error instanceof Error ? error.message : "Source details are unavailable."} retry={() => void refetch()} />;
  const recentRuns = data.recent_runs as CollectionRun[];

  return (
    <>
      <button className="back-link" onClick={() => navigate("/sources")}><ArrowLeft size={15} /> All sources</button>
      <PageHeader
        title={String(data.name)}
        description="Source configuration, access details, and execution history."
        action={<Button onClick={() => setRunConfirmationOpen(true)} disabled={!data.enabled || !data.supported || start.isPending}><Play size={15} /> {start.isPending ? "Starting…" : "Run collection"}</Button>}
      />
      <ConfirmationDialog
        open={runConfirmationOpen}
        onOpenChange={setRunConfirmationOpen}
        title="Start data collection?"
        description={`Start a new collection for ${String(data.name)}? Orbit will retrieve source data, validate it, and update stored records when changes are detected.`}
        confirmLabel="Start collection"
        pendingLabel="Starting…"
        errorFallback="Collection could not be started. Please try again."
        onConfirm={async () => {
          if (!data.enabled || !data.supported) {
            throw new Error("This source is not enabled for approved collection.");
          }
          await start.mutateAsync(sourceKey);
        }}
      />
      <div className="detail-grid source-detail-grid">
        <DetailCell label="State"><StatusBadge status={data.enabled ? "enabled" : "disabled"} /></DetailCell>
        <DetailCell label="Collection adapter">{data.supported ? "World Bank API · approved" : "No approved adapter"}</DetailCell>
        <DetailCell label="Category">{String(data.category).replaceAll("_", " ")}</DetailCell>
        <DetailCell label="Official source"><a className="text-link" href={String(data.official_url)} target="_blank" rel="noreferrer">Open source <ExternalLink size={13} /></a></DetailCell>
        <DetailCell label="Current records">{Number(data.latest_record_count).toLocaleString()}</DetailCell>
        <DetailCell label="Last result"><StatusBadge status={(data.latest_result as CollectionRun | null)?.status ?? "unknown"} /></DetailCell>
      </div>
      <div className="overview-lower detail-sections">
        <Panel title="Collection configuration"><pre className="json-view">{JSON.stringify(data.collection_config, null, 2)}</pre></Panel>
        <Panel title="Permission & licensing metadata"><pre className="json-view">{JSON.stringify(data.licensing_metadata, null, 2)}</pre></Panel>
      </div>
      <Panel title="Recent execution history" className="source-runs-panel">
        {recentRuns.length ? <div className="table-wrap"><table className="data-table">
          <thead><tr><th>Started</th><th>Duration</th><th>Fetched</th><th>New</th><th>Changed</th><th>Invalid</th><th>Status</th></tr></thead>
          <tbody>{recentRuns.map((run) => <tr key={run.id}><td>{formatDateTime(run.started_at)}</td><td>{formatDuration(run.duration_seconds)}</td><td className="mono">{run.records_fetched}</td><td className="mono">{run.records_new}</td><td className="mono">{run.records_changed}</td><td className="mono">{run.records_invalid}</td><td><StatusBadge status={run.status} /></td></tr>)}</tbody>
        </table></div> : <EmptyState title="No execution history" description="Collection runs for this source will be listed here." />}
      </Panel>
    </>
  );
}

function DetailCell({ label, children }: { label: string; children: React.ReactNode }) {
  return <div className="detail-cell"><span>{label}</span><strong>{children}</strong></div>;
}
