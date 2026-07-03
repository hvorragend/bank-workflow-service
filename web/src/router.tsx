import { createBrowserRouter } from "react-router-dom";

import { ProtectedRoute } from "@/auth/ProtectedRoute";
import { RequireAdmin } from "@/auth/RequireAdmin";
import { RequirePermission } from "@/auth/RequirePermission";
import { Layout } from "@/components/Layout";
import { NotFoundPage, RouteErrorPage } from "@/pages/ErrorPages";
import { ArchivePage } from "@/pages/ArchivePage";
import { DashboardPage } from "@/pages/DashboardPage";
import { DefinitionsPage } from "@/pages/DefinitionsPage";
import { InstanceDetailPage } from "@/pages/InstanceDetailPage";
import { InstancesPage } from "@/pages/InstancesPage";
import { LoginPage } from "@/pages/LoginPage";
import { NewInstancePage } from "@/pages/NewInstancePage";
import { AdminDefinitionsPage } from "@/pages/admin/AdminDefinitionsPage";
import { AdminLayout } from "@/pages/admin/AdminLayout";
import { AdminOverviewPage } from "@/pages/admin/AdminOverviewPage";
import { AuditLogPage } from "@/pages/admin/AuditLogPage";
import { DesignerPage } from "@/pages/admin/DesignerPage";
import { DiffPage } from "@/pages/admin/DiffPage";
import { UploadDefinitionPage } from "@/pages/admin/UploadDefinitionPage";
import { AuthModePage } from "@/pages/admin/auth/AuthModePage";
import { LdapConfigPage } from "@/pages/admin/auth/LdapConfigPage";
import { LdapRoleMappingPage } from "@/pages/admin/auth/LdapRoleMappingPage";
import { LdapSyncPage } from "@/pages/admin/auth/LdapSyncPage";
import { RoleEmailsPage } from "@/pages/admin/notifications/RoleEmailsPage";
import { SmtpConfigPage } from "@/pages/admin/notifications/SmtpConfigPage";
import { TemplateEditPage } from "@/pages/admin/notifications/TemplateEditPage";
import { TemplatesListPage } from "@/pages/admin/notifications/TemplatesListPage";
import { PermissionsCatalogPage } from "@/pages/admin/roles/PermissionsCatalogPage";
import { RoleCreatePage } from "@/pages/admin/roles/RoleCreatePage";
import { RoleEditPage } from "@/pages/admin/roles/RoleEditPage";
import { RolesListPage } from "@/pages/admin/roles/RolesListPage";
import { ApiTokensPage } from "@/pages/admin/system/ApiTokensPage";
import { EscalationConfigPage } from "@/pages/admin/system/EscalationConfigPage";
import { RekeyPage } from "@/pages/admin/system/RekeyPage";
import { SystemStatusPage } from "@/pages/admin/system/SystemStatusPage";
import { UserCreatePage } from "@/pages/admin/users/UserCreatePage";
import { UserEditPage } from "@/pages/admin/users/UserEditPage";
import { UsersListPage } from "@/pages/admin/users/UsersListPage";

export const router = createBrowserRouter([
  { path: "/login", element: <LoginPage />, errorElement: <RouteErrorPage /> },
  {
    path: "/",
    element: (
      <ProtectedRoute>
        <Layout />
      </ProtectedRoute>
    ),
    errorElement: <RouteErrorPage />,
    children: [
      { index: true,               element: <DashboardPage /> },
      { path: "antraege",          element: <InstancesPage /> },
      { path: "antraege/:id",      element: <InstanceDetailPage /> },
      { path: "archiv",            element: <ArchivePage /> },
      { path: "definitionen",      element: <DefinitionsPage /> },
      { path: "neu",               element: <NewInstancePage /> },

      // Admin-Bereich (Permission-basiert; Sidebar in AdminLayout)
      {
        path: "admin",
        element: <RequireAdmin><AdminLayout /></RequireAdmin>,
        children: [
          { index: true, element: <AdminOverviewPage /> },

          // Workflow
          { path: "definitionen", element:
            <RequirePermission permission={["definitions.upload","definitions.activate","definitions.retire"]}>
              <AdminDefinitionsPage />
            </RequirePermission> },
          { path: "definitionen/upload", element:
            <RequirePermission permission="definitions.upload"><UploadDefinitionPage /></RequirePermission> },
          { path: "definitionen/designer", element:
            <RequirePermission permission="definitions.upload"><DesignerPage /></RequirePermission> },
          { path: "definitionen/diff/:aId/:bId", element:
            <RequirePermission permission="definitions.diff"><DiffPage /></RequirePermission> },
          { path: "audit", element:
            <RequirePermission permission="admin.audit.read"><AuditLogPage /></RequirePermission> },

          // User & Rollen
          { path: "users", element:
            <RequirePermission permission="admin.users.read"><UsersListPage /></RequirePermission> },
          { path: "users/new", element:
            <RequirePermission permission="admin.users.write"><UserCreatePage /></RequirePermission> },
          { path: "users/:id", element:
            <RequirePermission permission="admin.users.read"><UserEditPage /></RequirePermission> },
          { path: "roles", element:
            <RequirePermission permission="admin.roles.read"><RolesListPage /></RequirePermission> },
          { path: "roles/new", element:
            <RequirePermission permission="admin.roles.write"><RoleCreatePage /></RequirePermission> },
          { path: "roles/:id", element:
            <RequirePermission permission="admin.roles.read"><RoleEditPage /></RequirePermission> },
          { path: "permissions", element:
            <RequirePermission permission="admin.permissions.read"><PermissionsCatalogPage /></RequirePermission> },

          // Auth
          { path: "auth-mode", element:
            <RequirePermission permission="admin.auth_mode.read"><AuthModePage /></RequirePermission> },
          { path: "ldap", element:
            <RequirePermission permission="admin.ldap.read"><LdapConfigPage /></RequirePermission> },
          { path: "ldap/role-mapping", element:
            <RequirePermission permission="admin.ldap.read"><LdapRoleMappingPage /></RequirePermission> },
          { path: "ldap/sync", element:
            <RequirePermission permission="admin.ldap.sync"><LdapSyncPage /></RequirePermission> },

          // Notifications
          { path: "smtp", element:
            <RequirePermission permission="admin.smtp.read"><SmtpConfigPage /></RequirePermission> },
          { path: "notifications/templates", element:
            <RequirePermission permission="admin.notifications.templates.read">
              <TemplatesListPage />
            </RequirePermission> },
          { path: "notifications/templates/:key", element:
            <RequirePermission permission="admin.notifications.templates.read">
              <TemplateEditPage />
            </RequirePermission> },
          { path: "notifications/role-emails", element:
            <RequirePermission permission="admin.notifications.role_emails.read">
              <RoleEmailsPage />
            </RequirePermission> },

          // System
          { path: "escalation", element:
            <RequirePermission permission="admin.escalation.read"><EscalationConfigPage /></RequirePermission> },
          { path: "api-tokens", element:
            <RequirePermission permission="admin.api_tokens.read"><ApiTokensPage /></RequirePermission> },
          { path: "system", element:
            <RequirePermission permission="admin.system.read"><SystemStatusPage /></RequirePermission> },
          { path: "system/rekey", element:
            <RequirePermission permission="admin.system.rekey"><RekeyPage /></RequirePermission> },
        ],
      },

      // Catch-all: unbekannte Pfade innerhalb des Layouts -> 404.
      { path: "*", element: <NotFoundPage /> },
    ],
  },
]);
