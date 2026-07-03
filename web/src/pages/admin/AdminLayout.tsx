import { NavLink, Outlet } from "react-router-dom";

import { useAuth } from "@/auth/AuthContext";
import { hasPermission } from "@/auth/RequirePermission";
import { cn } from "@/lib/utils";

interface SidebarItem {
  to: string;
  label: string;
  end?: boolean;
  permission: string | string[];
}

interface SidebarSection {
  title: string;
  items: SidebarItem[];
}

const SECTIONS: SidebarSection[] = [
  {
    title: "Workflow",
    items: [
      { to: "/admin",                  label: "Übersicht", end: true,
        permission: ["admin.users.read", "admin.system.read"] },
      { to: "/admin/definitionen",     label: "Definitionen",
        permission: ["definitions.upload", "definitions.activate", "definitions.retire"] },
      { to: "/admin/audit",            label: "Audit-Log",
        permission: "admin.audit.read" },
    ],
  },
  {
    title: "User & Rollen",
    items: [
      { to: "/admin/users",            label: "Benutzer",
        permission: "admin.users.read" },
      { to: "/admin/roles",            label: "Rollen",
        permission: "admin.roles.read" },
      { to: "/admin/permissions",      label: "Permissions-Katalog",
        permission: "admin.permissions.read" },
    ],
  },
  {
    title: "Auth",
    items: [
      { to: "/admin/auth-mode",        label: "Auth-Modus",
        permission: "admin.auth_mode.read" },
      { to: "/admin/ldap",             label: "LDAP",
        permission: "admin.ldap.read" },
      { to: "/admin/ldap/role-mapping",label: "LDAP-Rollen-Mapping",
        permission: "admin.ldap.read" },
      { to: "/admin/ldap/sync",        label: "LDAP-Sync",
        permission: "admin.ldap.sync" },
    ],
  },
  {
    title: "Notifications",
    items: [
      { to: "/admin/smtp",             label: "SMTP",
        permission: "admin.smtp.read" },
      { to: "/admin/notifications/templates", label: "E-Mail-Templates",
        permission: "admin.notifications.templates.read" },
      { to: "/admin/notifications/role-emails", label: "Rollen-Empfänger",
        permission: "admin.notifications.role_emails.read" },
    ],
  },
  {
    title: "System",
    items: [
      { to: "/admin/escalation",       label: "SLA-Eskalation",
        permission: "admin.escalation.read" },
      { to: "/admin/api-tokens",       label: "Reporting-Tokens",
        permission: "admin.api_tokens.read" },
      { to: "/admin/system",           label: "System-Status",
        permission: "admin.system.read" },
      { to: "/admin/system/rekey",     label: "Schlüssel-Rotation",
        permission: "admin.system.rekey" },
    ],
  },
];

export function AdminLayout() {
  const { state } = useAuth();
  const perms = state.status === "authenticated" ? state.user.permissions : [];

  return (
    <div className="grid gap-6 lg:gap-10 lg:grid-cols-[220px_minmax(0,1fr)]">
      <aside className="lg:sticky lg:top-24 lg:self-start">
        <p className="eyebrow mb-4">Admin</p>
        <nav className="flex flex-col gap-6">
          {SECTIONS.map((section) => {
            const visible = section.items.filter((it) => hasPermission(perms, it.permission));
            if (!visible.length) return null;
            return (
              <div key={section.title}>
                <p className="label-mono mb-2">{section.title}</p>
                <div className="flex flex-col">
                  {visible.map((it) => (
                    <NavLink
                      key={it.to}
                      to={it.to}
                      end={it.end}
                      className={({ isActive }) =>
                        cn(
                          "rounded-md px-2 py-1.5 text-[13px] text-muted hover:text-accent hover:bg-accent-soft transition-colors",
                          isActive && "text-accent bg-accent-soft font-medium",
                        )
                      }
                    >
                      {it.label}
                    </NavLink>
                  ))}
                </div>
              </div>
            );
          })}
        </nav>
      </aside>
      <section className="min-w-0">
        <Outlet />
      </section>
    </div>
  );
}
