import { lazy, Suspense } from "react";
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
    <Suspense fallback={<LoadingState label="Loading workspace" />}>
      <Routes>
        <Route element={<ProtectedLayout />}>
          <Route path="/" element={<OverviewPage />} />
          <Route path="/sources" element={<SourcesPage />} />
          <Route path="/sources/:sourceKey" element={<SourcesPage />} />
          <Route path="/operations" element={<OperationsPage />} />
          <Route path="/records" element={<RecordsPage />} />
          <Route path="/records/:recordId" element={<RecordDetailPage />} />
          <Route path="/history" element={<HistoryPage />} />
          <Route path="/quality" element={<QualityPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/login" element={<Navigate to="/" replace />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
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
