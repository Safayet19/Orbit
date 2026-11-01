import { useState } from "react";
import { GitCompareArrows } from "lucide-react";
import { Link } from "react-router-dom";
import { EmptyState, ErrorState, formatDateTime, LoadingState, PageHeader, Pagination, Panel } from "../../components/ui/Primitives";
import { useHistory } from "../../services/queries";
import type { HistoryItem } from "../../types/api";

export default function HistoryPage() {
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<HistoryItem | null>(null);
  const { data, isLoading, isError, refetch } = useHistory(page);
  const items = data?.items ?? [];
  return (
    <>
      <PageHeader title="History & changes" description="Review append-only versions and inspect meaningful changes between observations." />
      <Panel title="Observed record changes">
        {isLoading ? <LoadingState /> : isError || !data ? <ErrorState message="Change history is unavailable." retry={() => void refetch()} /> : items.length ? (
          <>
            <div className="table-wrap"><table className="data-table">
              <thead><tr><th>Source</th><th>Record identity</th><th>Change time</th><th>Version</th><th>Fields changed</th><th>Compare</th></tr></thead>
              <tbody>{items.map((item) => {
                const changed = changedKeys(item.previous_data, item.data);
                return <tr key={item.version_id}>
                  <td>{item.source_name}</td>
                  <td><Link className="text-link mono" to={`/records/${item.record_id}`}>{item.external_record_id}</Link></td>
                  <td>{formatDateTime(item.observed_at)}</td>
                  <td className="mono">v{item.version_number}</td>
                  <td>{changed.length ? changed.map((key) => <span className="field-chip" key={key}>{key}</span>) : "Values changed"}</td>
                  <td><button className="text-link" onClick={() => setSelected(item)}><GitCompareArrows size={14} /> Compare</button></td>
                </tr>;
              })}</tbody>
            </table></div>
            <Pagination page={data.pagination.page} pages={data.pagination.pages} total={data.pagination.total} onChange={setPage} />
          </>
        ) : <EmptyState title="No meaningful changes yet" description="Historical comparisons appear when a later collection observes different data. Existing observations are not changed for demonstration." />}
      </Panel>
      {selected && <Panel title={`Version comparison · ${selected.external_record_id}`} className="compare-panel">
        <div className="comparison-meta"><span>{selected.source_name}</span><span>Version {selected.version_number}</span><span>{formatDateTime(selected.observed_at)}</span><button className="text-link" onClick={() => setSelected(null)}>Close comparison</button></div>
        <div className="version-compare">
          <CompareColumn title={`Previous · v${selected.version_number - 1}`} oldData={selected.previous_data} newData={selected.data} previous />
          <CompareColumn title={`Current · v${selected.version_number}`} oldData={selected.previous_data} newData={selected.data} />
        </div>
      </Panel>}
    </>
  );
}

function CompareColumn({ title, oldData, newData, previous = false }: { title: string; oldData: Record<string, unknown>; newData: Record<string, unknown>; previous?: boolean }) {
  const keys = [...new Set([...Object.keys(oldData), ...Object.keys(newData)])].sort();
  return <div className="version-column"><h3>{title}</h3>{keys.map((key) => {
    const exists = Object.hasOwn(previous ? oldData : newData, key);
    const value = previous ? oldData[key] : newData[key];
    const changed = !Object.is(oldData[key], newData[key]) || Object.hasOwn(oldData, key) !== Object.hasOwn(newData, key);
    return <div className={`diff-row ${changed ? "diff-changed" : ""}`} key={key}><span className="diff-key">{key}</span><span className="diff-value">{exists ? String(value) : <em>Removed</em>}</span></div>;
  })}</div>;
}

function changedKeys(before: Record<string, unknown>, after: Record<string, unknown>): string[] {
  return [...new Set([...Object.keys(before), ...Object.keys(after)])].filter((key) => (
    !Object.hasOwn(before, key) ||
    !Object.hasOwn(after, key) ||
    JSON.stringify(before[key]) !== JSON.stringify(after[key])
  ));
}
