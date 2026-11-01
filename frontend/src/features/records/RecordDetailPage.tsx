import { useParams, useNavigate } from "react-router-dom";
import { ArrowLeft, ExternalLink } from "lucide-react";
import { Button, EmptyState, ErrorState, formatDateTime, LoadingState, PageHeader, Panel } from "../../components/ui/Primitives";
import { useRecord, useVersions } from "../../services/queries";

export default function RecordDetailPage() {
  const { recordId } = useParams();
  const navigate = useNavigate();
  const record = useRecord(recordId);
  const versions = useVersions(recordId);
  if (record.isLoading) return <LoadingState />;
  if (record.isError || !record.data) return <ErrorState message="Record details could not be loaded." retry={() => void record.refetch()} />;
  const item = record.data;

  return (
    <>
      <button className="back-link" onClick={() => navigate("/records")}><ArrowLeft size={15} /> Data explorer</button>
      <PageHeader title="Record details" description={item.external_record_id} action={<Button variant="secondary" onClick={() => navigate("/history")}><ExternalLink size={15} /> History</Button>} />
      <div className="detail-grid">
        <Cell label="Source">{item.source_name}</Cell>
        <Cell label="Category">{item.category.replaceAll("_", " ")}</Cell>
        <Cell label="Status">{item.status}</Cell>
        <Cell label="Record ID"><span className="mono">{item.id}</span></Cell>
        <Cell label="Record identifier"><span className="mono">{item.external_record_id}</span></Cell>
        <Cell label="First observed">{formatDateTime(item.first_observed_at)}</Cell>
        <Cell label="Last observed">{formatDateTime(item.last_observed_at)}</Cell>
        <Cell label="Current version">v{item.version_number}</Cell>
        <Cell label="Source provenance"><a className="text-link source-url" href={item.source_url} target="_blank" rel="noreferrer">{item.source_url} <ExternalLink size={13} /></a></Cell>
      </div>
      <Panel title="Normalized fields" className="record-data-panel">
        <div className="record-kv">{Object.entries(item.data).map(([key, value]) => <div className="record-kv-row" key={key}><span>{key.replaceAll("_", " ")}</span><strong>{String(value)}</strong></div>)}</div>
        <details className="technical-details"><summary>Technical JSON</summary><pre className="json-view">{JSON.stringify(item.data, null, 2)}</pre></details>
      </Panel>
      <Panel title="Version history">
        {versions.isLoading ? <LoadingState /> : versions.isError ? <ErrorState message="Version history is unavailable." retry={() => void versions.refetch()} /> : versions.data?.items.length ? (
          <div className="table-wrap"><table className="data-table">
            <thead><tr><th>Version</th><th>Observed</th><th>Fingerprint</th><th>Provenance</th></tr></thead>
            <tbody>{versions.data.items.map((version) => <tr key={version.id}><td className="mono">v{version.version_number}</td><td>{formatDateTime(version.observed_at)}</td><td><code className="mono fingerprint">{version.fingerprint}</code></td><td>{String(version.provenance.source_key ?? "Registered source")}</td></tr>)}</tbody>
          </table></div>
        ) : <EmptyState title="No historical versions" description="This record has not yet changed since its first observation." />}
      </Panel>
    </>
  );
}

function Cell({ label, children }: { label: string; children: React.ReactNode }) {
  return <div className="detail-cell"><span>{label}</span><strong>{children}</strong></div>;
}
