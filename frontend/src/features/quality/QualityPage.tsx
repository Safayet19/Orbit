import { AlertTriangle, CheckCheck, CircleHelp, Database, ShieldAlert } from "lucide-react";
import { MetricCard, EmptyState, ErrorState, formatDateTime, LoadingState, PageHeader, Panel, StatusBadge } from "../../components/ui/Primitives";
import { useQuality, useQualityIssues } from "../../services/queries";

export default function QualityPage() {
  const quality = useQuality();
  const issues = useQualityIssues(1);
  return (
    <>
      <PageHeader title="Data quality" description="Review validation outcomes and operational signals recorded by the collection engine." />
      {quality.isLoading ? <LoadingState /> : quality.isError || !quality.data ? (
        <ErrorState message="Quality summary is unavailable." retry={() => void quality.refetch()} />
      ) : (
        <>
          <div className="quality-status-line"><span>Overall status</span><StatusBadge status={quality.data.status} /><span className="quality-explainer">Based on recorded validation and collection outcomes.</span></div>
          <div className="metric-grid">
            <MetricCard label="Valid records" value={quality.data.valid_records} supporting="Persisted validated observations" icon={Database} tone="green" />
            <MetricCard label="Invalid observations" value={quality.data.invalid_records} supporting="Quarantined validation outcomes" icon={AlertTriangle} tone="red" />
            <MetricCard label="Failed collections" value={quality.data.failed_runs} supporting="Recorded failed execution runs" icon={ShieldAlert} tone="red" />
            <MetricCard label="Stale sources" value={quality.data.stale_sources} supporting="No successful run in 7 days" icon={CircleHelp} tone="blue" />
          </div>
          <Panel title="Measurement notes" className="quality-notes">
            <div className="quality-note"><CheckCheck size={17} /><span>Duplicate current observations are prevented by a database uniqueness constraint.</span></div>
            <div className="quality-note"><CircleHelp size={17} /><span>{quality.data.potential_duplicates_measurable ? `${quality.data.potential_duplicates} potential duplicates measured.` : "Potential duplicate scoring is not measured; no zero value is inferred."}</span></div>
            <div className="quality-note"><AlertTriangle size={17} /><span>{quality.data.sources_with_recent_errors} source(s) with errors in the last seven days.</span></div>
          </Panel>
        </>
      )}
      <Panel title="Validation and collection issues">
        {issues.isLoading ? <LoadingState /> : issues.isError || !issues.data ? (
          <ErrorState message="Issue history is unavailable." retry={() => void issues.refetch()} />
        ) : issues.data.items.length ? (
          <div className="table-wrap"><table className="data-table">
            <thead><tr><th>Severity</th><th>Source</th><th>Issue type</th><th>Record</th><th>Run</th><th>Timestamp</th></tr></thead>
            <tbody>{issues.data.items.map((issue) => (
              <tr key={issue.id}>
                <td><StatusBadge status={issue.severity} /></td>
                <td>{issue.source_name}</td>
                <td>{issue.error_details.map((detail) => `${detail.field ? `${detail.field}: ` : ""}${detail.type}`).join(", ")}</td>
                <td className="mono">{issue.external_record_id ?? "—"}</td>
                <td className="mono">{issue.run_id.slice(0, 8)}</td>
                <td>{formatDateTime(issue.created_at)}</td>
              </tr>
            ))}</tbody>
          </table></div>
        ) : <EmptyState title="No issues recorded" description="Validation failures and collection errors will be listed here when observed." />}
      </Panel>
    </>
  );
}
