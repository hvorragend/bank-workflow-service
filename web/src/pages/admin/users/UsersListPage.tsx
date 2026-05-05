import { useQuery } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { Link } from "react-router-dom";

import { listRoles, listUsers } from "@/api/admin";
import { formatDate } from "@/lib/utils";

export function UsersListPage() {
  const { data: users, isLoading } = useQuery({
    queryKey: ["admin", "users"],
    queryFn: () => listUsers(),
  });
  const { data: roles } = useQuery({
    queryKey: ["admin", "roles"],
    queryFn: listRoles,
  });

  return (
    <section>
      <header className="page-header flex flex-col sm:flex-row sm:items-end sm:justify-between gap-4">
        <div>
          <p className="eyebrow mb-3">Admin · User & Rollen</p>
          <h2 className="page-title">Benutzer</h2>
          <p className="page-lead">
            Lokale User leben in der DB; LDAP-User werden bei Login oder
            ueber den LDAP-Sync angelegt. „Deaktivieren" verhindert weitere
            Logins, Audit-Bezuege bleiben erhalten.
          </p>
        </div>
        <Link to="/admin/users/new" className="btn btn-primary whitespace-nowrap self-start">
          <Plus size={14} /> Neuer User
        </Link>
      </header>

      <div className="paper p-0">
        {isLoading ? (
          <div className="py-10 text-center text-quiet italic">Lade …</div>
        ) : (
          <table className="w-full text-[13px]">
            <thead>
              <tr className="text-left text-quiet">
                <th className="px-4 py-2 font-mono text-[11px] uppercase tracking-wider">Username</th>
                <th className="px-4 py-2 font-mono text-[11px] uppercase tracking-wider">Anzeigename</th>
                <th className="px-4 py-2 font-mono text-[11px] uppercase tracking-wider">Quelle</th>
                <th className="px-4 py-2 font-mono text-[11px] uppercase tracking-wider">Rollen</th>
                <th className="px-4 py-2 font-mono text-[11px] uppercase tracking-wider">Letzter Login</th>
                <th className="px-4 py-2 font-mono text-[11px] uppercase tracking-wider">Aktiv</th>
                <th />
              </tr>
            </thead>
            <tbody className="divide-y divide-rule-soft">
              {users?.map((u) => (
                <tr key={u.id} className="hover:bg-bg/50">
                  <td className="px-4 py-3 font-mono text-[12px]">{u.username}</td>
                  <td className="px-4 py-3">{u.display_name}</td>
                  <td className="px-4 py-3"><span className={`badge badge-${u.auth_source}`}>{u.auth_source}</span></td>
                  <td className="px-4 py-3 text-[12px] text-muted">{u.roles.join(", ") || "—"}</td>
                  <td className="px-4 py-3 text-[12px] text-quiet">{formatDate(u.last_login_at) || "nie"}</td>
                  <td className="px-4 py-3">{u.is_active ? "ja" : "nein"}</td>
                  <td className="px-4 py-3 text-right">
                    <Link to={`/admin/users/${u.id}`} className="btn btn-ghost text-[12px] px-2 py-1">
                      Bearbeiten
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {roles && (
        <p className="hint mt-4">
          Verfuegbare Rollen ({roles.length}): {roles.map((r) => r.name).join(", ")}
        </p>
      )}
    </section>
  );
}
