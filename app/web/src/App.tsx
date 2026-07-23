import { useEffect } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { QueryClientProvider } from "@tanstack/react-query";
import { useAuth } from "./stores/useAuthStore";
import { AppShell } from "./components/shell/AppShell";
import { RequireAdmin } from "./components/shell/RequireAdmin";
import { AuthPage } from "./routes/auth/AuthPage";
import { UsersPage } from "./routes/settings/UsersPage";
import { RolesPage } from "./routes/settings/RolesPage";
import { AssignRolesPage } from "./routes/settings/AssignRolesPage";
import { PermissionsPage } from "./routes/settings/PermissionsPage";
import { ConnectorsPage } from "./routes/connectors/ConnectorsPage";
import { DataSourcesPage } from "./routes/data-sources/DataSourcesPage";
import { ChatPage } from "./routes/chat/ChatPage";
import { ChatHistoryPage } from "./routes/chat/ChatHistoryPage";
// import { ForecastsPage } from "./routes/forecasts/ForecastsPage";
import { InsightsPage } from "./routes/insights/InsightsPage";
import { ThemesPage } from "./routes/themes/ThemesPage";
import { queryClient } from "./lib/queryClient";
import { useAuthStore } from "./stores/useAuthStore";
import { useThemeStore } from "./stores/useThemeStore";

import { ErrorBoundary } from "./components/common/ErrorBoundary";

function RequireAuth({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, isLoading } = useAuth();
  if (isLoading) return null;
  if (!isAuthenticated) return <Navigate to="/" replace />;
  return <>{children}</>;
}

function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<AuthPage />} />
      <Route
        element={
          <RequireAuth>
            <AppShell />
          </RequireAuth>
        }
      >
        <Route path="/chat" element={<ErrorBoundary><ChatPage /></ErrorBoundary>} />
        <Route path="/chat/history" element={<ErrorBoundary><ChatHistoryPage /></ErrorBoundary>} />
        <Route path="/insights" element={<ErrorBoundary><InsightsPage /></ErrorBoundary>} />
        <Route path="/connectors" element={<ErrorBoundary><ConnectorsPage /></ErrorBoundary>} />
        <Route path="/data-sources" element={<ErrorBoundary><DataSourcesPage /></ErrorBoundary>} />
        {/* <Route path="/forecasts" element={<ForecastsPage />} /> */}
        <Route path="/themes" element={<ErrorBoundary><ThemesPage /></ErrorBoundary>} />
        <Route
          path="/settings/users"
          element={
            <RequireAdmin>
              <ErrorBoundary><UsersPage /></ErrorBoundary>
            </RequireAdmin>
          }
        />
        <Route
          path="/settings/roles"
          element={
            <RequireAdmin>
              <ErrorBoundary><RolesPage /></ErrorBoundary>
            </RequireAdmin>
          }
        />
        <Route
          path="/settings/assign"
          element={
            <RequireAdmin>
              <ErrorBoundary><AssignRolesPage /></ErrorBoundary>
            </RequireAdmin>
          }
        />
        <Route
          path="/settings/permissions"
          element={
            <RequireAdmin>
              <ErrorBoundary><PermissionsPage /></ErrorBoundary>
            </RequireAdmin>
          }
        />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export default function App() {
  useEffect(() => {
    useAuthStore.getState().fetchUser();
    useThemeStore.getState().initialize();
  }, []);

  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <ErrorBoundary>
          <AppRoutes />
        </ErrorBoundary>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
