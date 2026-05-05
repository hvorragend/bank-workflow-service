import { createBrowserRouter } from "react-router-dom";

import { ProtectedRoute } from "@/auth/ProtectedRoute";
import { RequireAdmin } from "@/auth/RequireAdmin";
import { Layout } from "@/components/Layout";
import { ArchivePage } from "@/pages/ArchivePage";
import { DashboardPage } from "@/pages/DashboardPage";
import { DefinitionsPage } from "@/pages/DefinitionsPage";
import { InstanceDetailPage } from "@/pages/InstanceDetailPage";
import { InstancesPage } from "@/pages/InstancesPage";
import { LoginPage } from "@/pages/LoginPage";
import { NewInstancePage } from "@/pages/NewInstancePage";
import { AdminDefinitionsPage } from "@/pages/admin/AdminDefinitionsPage";
import { AuditLogPage } from "@/pages/admin/AuditLogPage";
import { DesignerPage } from "@/pages/admin/DesignerPage";
import { DiffPage } from "@/pages/admin/DiffPage";
import { UploadDefinitionPage } from "@/pages/admin/UploadDefinitionPage";

export const router = createBrowserRouter([
  { path: "/login", element: <LoginPage /> },
  {
    path: "/",
    element: (
      <ProtectedRoute>
        <Layout />
      </ProtectedRoute>
    ),
    children: [
      { index: true,               element: <DashboardPage /> },
      { path: "antraege",          element: <InstancesPage /> },
      { path: "antraege/:id",      element: <InstanceDetailPage /> },
      { path: "archiv",            element: <ArchivePage /> },
      { path: "definitionen",      element: <DefinitionsPage /> },
      { path: "neu",               element: <NewInstancePage /> },
      // Admin-Bereich (Rolle Admin erforderlich)
      { path: "admin",
        element: <RequireAdmin><AdminDefinitionsPage /></RequireAdmin> },
      { path: "admin/upload",
        element: <RequireAdmin><UploadDefinitionPage /></RequireAdmin> },
      { path: "admin/designer",
        element: <RequireAdmin><DesignerPage /></RequireAdmin> },
      { path: "admin/diff/:aId/:bId",
        element: <RequireAdmin><DiffPage /></RequireAdmin> },
      { path: "admin/audit",
        element: <RequireAdmin><AuditLogPage /></RequireAdmin> },
    ],
  },
]);
