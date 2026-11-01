import {
  AlertCircle,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  LoaderCircle,
  type LucideIcon,
} from "lucide-react";
import type { ReactNode } from "react";

export function Button({
  children,
  variant = "primary",
  className = "",
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "quiet" | "danger";
}) {
  return (
    <button className={`button button-${variant} ${className}`} {...props}>
      {children}
    </button>
  );
}

export function Panel({
  title,
  action,
  children,
  className = "",
}: {
  title?: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`panel ${className}`}>
      {(title || action) && (
        <div className="panel-heading">
          {title && <h2>{title}</h2>}
          {action}
        </div>
      )}
      {children}
    </section>
  );
}

export function PageHeader({
  title,
  description,
  refreshedAt,
  action,
}: {
  title: string;
  description: string;
  refreshedAt?: string;
  action?: ReactNode;
}) {
  return (
    <div className="page-header">
      <div>
        <h1>{title}</h1>
        <p>{description}</p>
        {refreshedAt && (
          <span className="refresh-label">
            Updated {formatDateTime(refreshedAt)}
          </span>
        )}
      </div>
      {action && <div className="page-actions">{action}</div>}
    </div>
  );
}

export function MetricCard({
  label,
  value,
  supporting,
  icon: Icon,
  tone = "copper",
}: {
  label: string;
  value: number | string;
  supporting: string;
  icon: LucideIcon;
  tone?: "copper" | "blue" | "green" | "red";
}) {
  return (
    <div className="metric-card">
      <div className="metric-top">
        <span className="metric-label">{label}</span>
        <span className={`metric-icon tone-${tone}`} aria-hidden="true">
          <Icon size={18} />
        </span>
      </div>
      <strong className="metric-value">{value.toLocaleString()}</strong>
      <span className="metric-support">{supporting}</span>
    </div>
  );
}

export function StatusBadge({ status }: { status: string | null | undefined }) {
  const normalized = (status ?? "unknown").toLowerCase();
  const label = normalized.replaceAll("_", " ");
  const Icon =
    normalized === "completed" || normalized === "healthy"
      ? CheckCircle2
      : normalized === "failed" || normalized === "error"
        ? AlertCircle
        : normalized === "running"
          ? LoaderCircle
          : null;
  return (
    <span className={`status-badge status-${normalized}`}>
      {Icon && <Icon size={14} aria-hidden="true" />}
      <span>{label}</span>
    </span>
  );
}

export function LoadingState({ label = "Loading data" }: { label?: string }) {
  return (
    <div className="state-box" role="status">
      <LoaderCircle className="spin" size={20} />
      <span>{label}</span>
    </div>
  );
}

export function ErrorState({
  message,
  retry,
}: {
  message: string;
  retry?: () => void;
}) {
  return (
    <div className="state-box state-error" role="alert">
      <AlertCircle size={20} />
      <span>{message}</span>
      {retry && (
        <Button variant="secondary" onClick={retry}>
          Retry
        </Button>
      )}
    </div>
  );
}

export function EmptyState({
  title,
  description,
}: {
  title: string;
  description: string;
}) {
  return (
    <div className="empty-state">
      <div className="empty-mark">O</div>
      <h3>{title}</h3>
      <p>{description}</p>
    </div>
  );
}

export function Pagination({
  page,
  pages,
  total,
  onChange,
}: {
  page: number;
  pages: number;
  total: number;
  onChange: (page: number) => void;
}) {
  return (
    <div className="pagination">
      <span>
        Page {page} of {Math.max(pages, 1)} · {total.toLocaleString()} total
      </span>
      <div>
        <Button
          variant="secondary"
          aria-label="Previous page"
          disabled={page <= 1}
          onClick={() => onChange(page - 1)}
        >
          <ChevronLeft size={16} />
          Previous
        </Button>
        <Button
          variant="secondary"
          aria-label="Next page"
          disabled={page >= pages}
          onClick={() => onChange(page + 1)}
        >
          Next
          <ChevronRight size={16} />
        </Button>
      </div>
    </div>
  );
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

export function formatDuration(seconds: number | null): string {
  if (seconds === null || !Number.isFinite(seconds)) return "In progress";
  if (seconds < 60) return `${seconds.toFixed(1)} sec`;
  return `${Math.floor(seconds / 60)} min ${Math.round(seconds % 60)} sec`;
}
