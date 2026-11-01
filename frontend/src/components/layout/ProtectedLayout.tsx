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
import { Button } from "../ui/Primitives";
import { useToast } from "../ui/Toast";

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
  const { user, logout } = useAuth();
  const queryClient = useQueryClient();
  const notify = useToast();
  const navigate = useNavigate();
  const location = useLocation();

  const onLogout = async () => {
    try {
      await logout();
      queryClient.clear();
      navigate("/login", { replace: true });
    } catch (error) {
      notify("error", error instanceof Error ? error.message : "Sign out failed.");
    }
  };

  const title =
    titles[location.pathname] ??
    (location.pathname.startsWith("/sources/") ? "Source details" :
      location.pathname.startsWith("/records/") ? "Record details" : "Orbit");

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
              onClick={onLogout}
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
            <span className="api-indicator"><span /> API connected</span>
            <Button
              variant="quiet"
              className="refresh-button"
              onClick={() => void queryClient.invalidateQueries()}
            >
              <RefreshCw size={15} />
              <span>Refresh</span>
            </Button>
            <div className="topbar-avatar">{user?.username.slice(0, 1).toUpperCase()}</div>
          </div>
        </header>
        <main className="main-content"><Outlet /></main>
      </div>
    </div>
  );
}
