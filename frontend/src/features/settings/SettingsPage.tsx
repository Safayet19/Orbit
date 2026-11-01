import { CircleCheck, CircleX, Clock3, Database, Fingerprint, Server } from "lucide-react";
import { useAuth } from "../../app/AuthContext";
import { ErrorState, formatDateTime, LoadingState, PageHeader, Panel, StatusBadge } from "../../components/ui/Primitives";
import { useSystemInfo } from "../../services/queries";

export default function SettingsPage() {
  const system = useSystemInfo();
  const { user } = useAuth();
  return (
    <>
      <PageHeader title="System settings" description="Runtime information, database health, and available collection capabilities." />
      {system.isLoading ? <LoadingState /> : system.isError || !system.data ? (
        <ErrorState message="System information is unavailable." retry={() => void system.refetch()} />
      ) : (
        <>
          <div className="overview-lower settings-grid">
            <Panel title="Application">
              <InfoRow icon={Server} label="Application" value={system.data.application} />
              <InfoRow icon={Fingerprint} label="Version" value={system.data.version} />
              <InfoRow icon={CircleCheck} label="Environment" value={system.data.environment} />
              <InfoRow icon={CircleCheck} label="API status" value={system.data.api_status} />
            </Panel>
            <Panel title="Database connectivity">
              <InfoRow icon={Database} label="Provider" value={system.data.database.provider} />
              <InfoRow icon={Database} label="Database" value={system.data.database.name} />
              <InfoRow icon={CircleCheck} label="Connection" value={system.data.database.status} />
              <InfoRow icon={system.data.database.tls_active ? CircleCheck : CircleX} label="Encrypted transport" value={system.data.database.tls_active ? "TLS active" : "TLS unavailable"} />
              <InfoRow icon={Clock3} label="Last checked" value={formatDateTime(system.data.database.checked_at)} />
            </Panel>
          </div>
          <Panel title="Collection capabilities">
            <div className="table-wrap"><table className="data-table">
              <thead><tr><th>Collector</th><th>Source identifier</th><th>Category</th><th>Available</th></tr></thead>
              <tbody>{system.data.collectors.map((collector) => <tr key={collector.source_id}><td className="table-primary">{collector.name}</td><td className="mono">{collector.source_id}</td><td>{collector.category.replaceAll("_", " ")}</td><td><StatusBadge status="available" /></td></tr>)}</tbody>
            </table></div>
            <div className="settings-note"><Clock3 size={16} /><span>Automatic scheduling: <strong>{system.data.scheduling.status}</strong>. Collection runs can be started manually from Agent operations.</span></div>
          </Panel>
          <Panel title="Administrator session">
            <div className="admin-session-info"><div className="settings-avatar">{user?.username.slice(0, 1).toUpperCase()}</div><div><strong>{user?.username}</strong><span>Single administrator · server-managed session</span></div><StatusBadge status="healthy" /></div>
            <p className="session-security-note">The session token is held in an HttpOnly cookie. Passwords and database connection details are never sent to the browser.</p>
          </Panel>
        </>
      )}
    </>
  );
}

function InfoRow({ icon: Icon, label, value }: { icon: typeof Database; label: string; value: string }) {
  return <div className="system-info-row"><span><Icon size={16} />{label}</span><strong>{value}</strong></div>;
}
