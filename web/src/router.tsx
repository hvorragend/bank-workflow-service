import { createBrowserRouter } from "react-router-dom";

import { ProtectedRoute } from "@/auth/ProtectedRoute";
import { Layout } from "@/components/Layout";
import { ArchivePage } from "@/pages/ArchivePage";
import { DashboardPage } from "@/pages/DashboardPage";
import { DefinitionsPage } from "@/pages/DefinitionsPage";
import { InstanceDetailPage } from "@/pages/InstanceDetailPage";
import { InstancesPage } from "@/pages/InstancesPage";
import { LoginPage } from "@/pages/LoginPage";
import { NewInstancePage } from "@/pages/NewInstancePage";

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
    ],
  },
]);
