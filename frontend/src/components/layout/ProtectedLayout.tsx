import {
  Activity,
  Boxes,
  ChevronDown,
  CircleHelp,
  Database,
  Gauge,
  History,
  LayoutDashboard,
  LogOut,
  Menu,
  RefreshCw,
  Settings,
  ShieldCheck,
  X,
} from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useState } from "react";
import { useAuth } from "../../app/AuthContext";
import { ApiError } from "../../services/api";
import { ConfirmationDialog } from "../ui/ConfirmationDialog";
import { Button } from "../ui/Primitives";
import { useToast } from "../ui/Toast";
import { useApiHealth } from "../../services/queries";

const navigation = [
  { title: "Workspace", items: [{ label: "Overview", path: "/", icon: LayoutDashboard }] },
  {
    title: "Collection",
    items: [
      { label: "Data sources", path: "/sources", icon: Boxes },
      { label: "Agent Control Center", path: "/operations", icon: Activity },
      { label: "Data explorer", path: "/records", icon: Database },
      { label: "History & changes", path: "/history", icon: History },
    ],
  },
  {
    title: "Administration",
    items: [
      { label: "Data quality", path: "/quality", icon: ShieldCheck },
      { label: "System settings", path: "/settings", icon: Settings },
    ],
  },
];

const titles: Record<string, string> = {
  "/": "Overview",
  "/sources": "Data sources",
  "/operations": "Agent Control Center",
  "/records": "Data explorer",
  "/history": "History & changes",
  "/quality": "Data quality",
  "/settings": "System settings",
};

export function ProtectedLayout() {
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [logoutOpen, setLogoutOpen] = useState(false);
  const { user, logout } = useAuth();
  const queryClient = useQueryClient();
  const notify = useToast();
  const navigate = useNavigate();
  const location = useLocation();
  const health = useApiHealth();

  const confirmLogout = async () => {
    try {
      await logout();
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        queryClient.clear();
        notify("error", "Your session has expired. Please sign in again.");
        navigate("/login", { replace: true });
        return;
      }
      throw error;
    }
    notify("success", "Signed out successfully.");
    queryClient.clear();
    navigate("/login", { replace: true });
  };

  const apiStatus =
    health.data?.status === "ok"
      ? "API connected"
      : health.isLoading
        ? "Checking API"
        : "API unavailable";

  const title =
    titles[location.pathname] ??
    (location.pathname.startsWith("/sources/") ? "Source details" :
      location.pathname.startsWith("/records/") ? "Record details" : "Orbit");

  const refreshCurrentPage = () => {
    const path = location.pathname;
    const queryKeys: readonly (readonly unknown[])[] =
      path === "/"
        ? [["overview"], ["sources"]]
        : path.startsWith("/sources/")
          ? [
              ["source", decodeURIComponent(path.slice("/sources/".length))],
              ["sources"],
              ["runs"],
            ]
          : path === "/sources"
            ? [["sources"]]
            : path === "/operations"
              ? [
                  ["agent-status"],
                  ["agent-schedules"],
                  ["agent-jobs"],
                  ["agent-decisions"],
                  ["runs"],
                ]
              : path === "/records"
                ? [["records"]]
                : path.startsWith("/records/")
                  ? [
                      ["record", decodeURIComponent(path.slice("/records/".length))],
                      [
                        "record-versions",
                        decodeURIComponent(path.slice("/records/".length)),
                      ],
                    ]
                  : path === "/history"
                    ? [["history"]]
                    : path === "/quality"
                      ? [["quality"], ["quality-issues"]]
                      : path === "/settings"
                        ? [["system"]]
                        : [];
    void Promise.all(
      queryKeys.map((queryKey) => queryClient.invalidateQueries({ queryKey })),
    );
  };

  return (
    <div className="app-shell">
      {drawerOpen && (
        <button
          className="drawer-scrim"
          aria-label="Close navigation"
          onClick={() => setDrawerOpen(false)}
        />
      )}
      <aside className={`sidebar ${drawerOpen ? "sidebar-open" : ""}`}>
        <div className="brand-row">
          <div className="brand-mark">O</div>
          <div className="brand-copy">
            <strong>ORBIT</strong>
            <span>DATA OPERATIONS</span>
          </div>
          <button
            className="icon-button mobile-close"
            aria-label="Close navigation"
            onClick={() => setDrawerOpen(false)}
          >
            <X size={18} />
          </button>
        </div>
        <div className="workspace-switch">
          <div className="workspace-icon"><Gauge size={16} /></div>
          <div><strong>Orbit workspace</strong><span>Administration</span></div>
          <ChevronDown size={15} />
        </div>
        <nav className="primary-nav" aria-label="Main navigation">
          {navigation.map((group) => (
            <div className="nav-group" key={group.title}>
              <span className="nav-heading">{group.title}</span>
              {group.items.map(({ label, path, icon: Icon }) => (
                <NavLink
                  to={path}
                  end={path === "/"}
                  key={path}
                  onClick={() => setDrawerOpen(false)}
                  className={({ isActive }) =>
                    `nav-link ${isActive ? "nav-link-active" : ""}`
                  }
                >
                  <Icon size={17} strokeWidth={1.8} />
                  <span>{label}</span>
                </NavLink>
              ))}
            </div>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="admin-identity">
            <div className="avatar">{user?.username.slice(0, 1).toUpperCase() ?? "A"}</div>
            <div className="admin-copy">
              <strong>{user?.username ?? "Administrator"}</strong>
              <span>Administrator</span>
            </div>
            <button
              className="icon-button"
              aria-label="Sign out"
              title="Sign out"
              onClick={() => setLogoutOpen(true)}
            >
              <LogOut size={16} />
            </button>
          </div>
          <div className="sidebar-footnote"><CircleHelp size={14} /> Orbit data platform</div>
        </div>
      </aside>
      <div className="main-column">
        <header className="topbar">
          <button
            className="icon-button mobile-menu"
            aria-label="Open navigation"
            onClick={() => setDrawerOpen(true)}
          >
            <Menu size={19} />
          </button>
          <div className="topbar-title">{title}</div>
          <div className="topbar-actions">
            <span
              className={`api-indicator ${
                health.data?.status === "ok"
                  ? "api-healthy"
                  : health.isLoading
                    ? "api-pending"
                    : "api-error"
              }`}
              role="status"
              aria-live="polite"
            >
              <span aria-hidden="true" />
              {apiStatus}
            </span>
            <Button
              variant="quiet"
              className="refresh-button"
              onClick={refreshCurrentPage}
            >
              <RefreshCw size={15} />
              <span>Refresh</span>
            </Button>
            <div className="topbar-avatar">{user?.username.slice(0, 1).toUpperCase()}</div>
          </div>
        </header>
        <main className="main-content"><Outlet /></main>
      </div>
      <ConfirmationDialog
        open={logoutOpen}
        onOpenChange={setLogoutOpen}
        title="Sign out of Orbit?"
        description="Are you sure you want to sign out of your administrator account?"
        confirmLabel="Sign out"
        pendingLabel="Signing out…"
        errorFallback="Unable to sign out. Please try again."
        onConfirm={confirmLogout}
      />
    </div>
  );
}
