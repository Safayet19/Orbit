import { useMemo, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, ExternalLink, Globe2, Play, Search, ShieldCheck, ToggleLeft, ToggleRight } from "lucide-react";
import { Link, useNavigate, useParams } from "react-router-dom";
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
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const notify = useToast();
  const mutation = useMutation({
    mutationFn: ({ source, enabled }: { source: Source; enabled: boolean }) =>
      api(`/api/admin/sources/${encodeURIComponent(source.source_key)}/enabled`, {
        method: "PATCH",
        body: JSON.stringify({ enabled }),
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["sources"] });
      notify("success", "Source setting updated.");
    },
    onError: (reason) => notify("error", reason instanceof Error ? reason.message : "Source update failed."),
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
                    <td><StatusBadge status={source.enabled ? "healthy" : "unknown"} /></td>
                    <td>{formatDateTime(source.last_collection_at)}</td>
                    <td><StatusBadge status={source.last_result} /></td>
                    <td className="mono">{source.latest_record_count.toLocaleString()}</td>
                    <td><div className="table-action-cell">
                      <button className="icon-button" title={source.enabled ? "Disable source" : "Enable source"} aria-label={`${source.enabled ? "Disable" : "Enable"} ${source.name}`} disabled={mutation.isPending || (!source.supported && !source.enabled)} onClick={() => {
                        const next = !source.enabled;
                        if (next && !source.supported) {
                          notify("error", "No approved collector is registered for this source.");
                          return;
                        }
                        if (!window.confirm(`${next ? "Enable" : "Disable"} ${source.name}?`)) return;
                        mutation.mutate({ source, enabled: next });
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
    </>
  );
}

function SourceDetail({ sourceKey }: { sourceKey: string }) {
  const { data, isLoading, isError, error, refetch } = useSource(sourceKey);
  const navigate = useNavigate();
  const notify = useToast();
  const [running, setRunning] = useState(false);

  async function startCollection() {
    if (!window.confirm(`Start a collection for ${String(data?.name)}?`)) return;
    setRunning(true);
    try {
      const response = await api<{ run_id: string }>("/api/admin/collections", {
        method: "POST",
        body: JSON.stringify({ source_id: sourceKey }),
      });
      notify("success", `Collection queued · ${response.run_id}`);
      navigate(`/operations?run=${response.run_id}`);
    } catch (reason) {
      notify("error", reason instanceof Error ? reason.message : "Could not start collection.");
    } finally {
      setRunning(false);
    }
  }

  if (isLoading) return <LoadingState />;
  if (isError || !data) return <ErrorState message={error instanceof Error ? error.message : "Source details are unavailable."} retry={() => void refetch()} />;
  const recentRuns = data.recent_runs as CollectionRun[];

  return (
    <>
      <button className="back-link" onClick={() => navigate("/sources")}><ArrowLeft size={15} /> All sources</button>
      <PageHeader
        title={String(data.name)}
        description="Source configuration, access details, and execution history."
        action={<Button onClick={() => void startCollection()} disabled={!data.enabled || !data.supported || running}><Play size={15} /> {running ? "Queueing…" : "Run collection"}</Button>}
      />
      <div className="detail-grid source-detail-grid">
        <DetailCell label="State"><StatusBadge status={data.enabled ? "healthy" : "unknown"} /></DetailCell>
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
