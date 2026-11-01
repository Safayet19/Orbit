import { lazy, Suspense, type ReactNode } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider, useAuth } from "./AuthContext";
import { ProtectedLayout } from "../components/layout/ProtectedLayout";
import { LoadingState } from "../components/ui/Primitives";
import { ToastProvider } from "../components/ui/Toast";
import { LoginPage } from "../features/auth/LoginPage";

const OverviewPage = lazy(() => import("../features/overview/OverviewPage"));
const SourcesPage = lazy(() => import("../features/sources/SourcesPage"));
const OperationsPage = lazy(() => import("../features/operations/OperationsPage"));
const RecordsPage = lazy(() => import("../features/records/RecordsPage"));
const RecordDetailPage = lazy(() => import("../features/records/RecordDetailPage"));
const HistoryPage = lazy(() => import("../features/history/HistoryPage"));
const QualityPage = lazy(() => import("../features/quality/QualityPage"));
const SettingsPage = lazy(() => import("../features/settings/SettingsPage"));

function ApplicationRoutes() {
  const { user, loading, setupError } = useAuth();
  if (loading) return <LoadingState label="Checking administrator session" />;
  if (!user) {
    return <LoginPage configurationError={setupError} />;
  }
  return (
    <Routes>
      <Route element={<ProtectedLayout />}>
        <Route path="/" element={<RouteContent><OverviewPage /></RouteContent>} />
        <Route path="/sources" element={<RouteContent><SourcesPage /></RouteContent>} />
        <Route path="/sources/:sourceKey" element={<RouteContent><SourcesPage /></RouteContent>} />
        <Route path="/operations" element={<RouteContent><OperationsPage /></RouteContent>} />
        <Route path="/records" element={<RouteContent><RecordsPage /></RouteContent>} />
        <Route path="/records/:recordId" element={<RouteContent><RecordDetailPage /></RouteContent>} />
        <Route path="/history" element={<RouteContent><HistoryPage /></RouteContent>} />
        <Route path="/quality" element={<RouteContent><QualityPage /></RouteContent>} />
        <Route path="/settings" element={<RouteContent><SettingsPage /></RouteContent>} />
        <Route path="/login" element={<Navigate to="/" replace />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}

function RouteContent({ children }: { children: ReactNode }) {
  return (
    <Suspense fallback={<LoadingState label="Loading page" />}>
      {children}
    </Suspense>
  );
}

export function App() {
  return (
    <AuthProvider>
      <ToastProvider>
        <ApplicationRoutes />
      </ToastProvider>
    </AuthProvider>
  );
}
