import { useEffect, useMemo, useState } from "react";
import { Download, ExternalLink, Search } from "lucide-react";
import { Link } from "react-router-dom";
import { Button, EmptyState, ErrorState, formatDateTime, LoadingState, PageHeader, Pagination, Panel, StatusBadge } from "../../components/ui/Primitives";
import { useToast } from "../../components/ui/Toast";
import { downloadCsv } from "../../services/api";
import { useRecords, useSources } from "../../services/queries";

export default function RecordsPage() {
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [sourceId, setSourceId] = useState("");
  const [category, setCategory] = useState("");
  const [after, setAfter] = useState("");
  const [before, setBefore] = useState("");
  const [sortOrder, setSortOrder] = useState<"asc" | "desc">("desc");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);
  const [exporting, setExporting] = useState(false);
  const sources = useSources();
  const notify = useToast();

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setDebouncedSearch(search.trim());
      setPage(1);
    }, 300);
    return () => window.clearTimeout(timer);
  }, [search]);

  const query = useMemo(() => {
    const params = new URLSearchParams({
      page: String(page),
      page_size: String(pageSize),
      sort_by: "last_observed_at",
      sort_order: sortOrder,
    });
    if (debouncedSearch) params.set("search", debouncedSearch);
    if (sourceId) params.set("source_id", sourceId);
    if (category) params.set("category", category);
    if (after) params.set("observed_after", new Date(after).toISOString());
    if (before) params.set("observed_before", new Date(`${before}T23:59:59`).toISOString());
    return params;
  }, [page, pageSize, sortOrder, debouncedSearch, sourceId, category, after, before]);
  const { data, isLoading, isError, error, refetch } = useRecords(query);

  async function exportData() {
    setExporting(true);
    try {
      const params = new URLSearchParams();
      if (debouncedSearch) params.set("search", debouncedSearch);
      if (sourceId) params.set("source_id", sourceId);
      if (category) params.set("category", category);
      if (after) params.set("observed_after", new Date(after).toISOString());
      if (before) params.set("observed_before", new Date(`${before}T23:59:59`).toISOString());
      await downloadCsv(`/api/admin/records/export.csv?${params}`);
      notify("success", "CSV export downloaded.");
    } catch (reason) {
      notify("error", reason instanceof Error ? reason.message : "Export failed.");
    } finally {
      setExporting(false);
    }
  }

  const categories = [...new Set(data?.items.map((record) => record.category) ?? [])];
  return (
    <>
      <PageHeader
        title="Data explorer"
        description="Search, filter, and inspect persisted collection records."
        action={<Button variant="secondary" disabled={exporting || !data?.pagination.total} onClick={() => void exportData()}><Download size={15} /> {exporting ? "Exporting…" : "Export CSV"}</Button>}
      />
      <Panel>
        <div className="toolbar">
          <div className="input-wrap"><Search size={16} /><input className="control" aria-label="Search records" placeholder="Search IDs, fields, sources" value={search} onChange={(event) => setSearch(event.target.value)} /></div>
          <select className="control filter-select" aria-label="Filter by source" value={sourceId} onChange={(event) => { setSourceId(event.target.value); setPage(1); }}>
            <option value="">All sources</option>{sources.data?.items.map((source) => <option value={source.source_key} key={source.id}>{source.name}</option>)}
          </select>
          <select className="control filter-select" aria-label="Filter by category" value={category} onChange={(event) => { setCategory(event.target.value); setPage(1); }}>
            <option value="">All categories</option>{categories.map((item) => <option key={item} value={item}>{item.replaceAll("_", " ")}</option>)}
          </select>
          <label className="date-filter">Observed after<input className="control" type="date" value={after} onChange={(event) => { setAfter(event.target.value); setPage(1); }} /></label>
          <label className="date-filter">Observed before<input className="control" type="date" value={before} onChange={(event) => { setBefore(event.target.value); setPage(1); }} /></label>
          <button className="button button-quiet" onClick={() => { setSortOrder(sortOrder === "desc" ? "asc" : "desc"); setPage(1); }}>Last observed {sortOrder === "desc" ? "↓" : "↑"}</button>
        </div>
        {isLoading ? <LoadingState /> : isError || !data ? (
          <ErrorState message={error instanceof Error ? error.message : "Records are unavailable."} retry={() => void refetch()} />
        ) : data.items.length ? (
          <>
            <div className="table-wrap">
              <table className="data-table record-table">
                <thead><tr><th>External identity</th><th>Source</th><th>Category</th><th>Observation</th><th>Last observed</th><th>Version</th><th>Status</th></tr></thead>
                <tbody>{data.items.map((record) => (
                  <tr key={record.id}>
                    <td><Link className="text-link mono record-id-link" title={record.external_record_id} to={`/records/${record.id}`}>{record.external_record_id}</Link><span className="table-secondary">Record {record.id.slice(0, 8)}</span></td>
                    <td>{record.source_name}</td>
                    <td>{record.category.replaceAll("_", " ")}</td>
                    <td>{Object.entries(record.data).slice(0, 3).map(([key, value]) => <span className="record-field" key={key}><b>{key}:</b> {String(value)}</span>)}</td>
                    <td>{formatDateTime(record.last_observed_at)}</td>
                    <td className="mono">v{record.version_number}</td>
                    <td><StatusBadge status={record.status} /></td>
                  </tr>
                ))}</tbody>
              </table>
            </div>
            <div className="table-controls">
              <label>Rows per page<select className="control" value={pageSize} onChange={(event) => { setPageSize(Number(event.target.value)); setPage(1); }}><option value={10}>10</option><option value={25}>25</option><option value={50}>50</option><option value={100}>100</option></select></label>
              <Pagination page={data.pagination.page} pages={data.pagination.pages} total={data.pagination.total} onChange={setPage} />
            </div>
          </>
        ) : <EmptyState title="No records match" description="Try a different search or clear one or more filters." />}
        <div className="table-footnote"><ExternalLink size={14} /> Data is loaded with server-side filtering and pagination.</div>
      </Panel>
    </>
  );
}
