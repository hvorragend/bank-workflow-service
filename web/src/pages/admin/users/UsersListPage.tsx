import { useQuery } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { listRoles, listUsers } from "@/api/admin";
import { QueryError } from "@/components/QueryStates";
import { StatusBadge } from "@/components/StatusBadge";
import { formatDate } from "@/lib/utils";

export function UsersListPage() {
  const [q, setQ] = useState("");
  const [debouncedQ, setDebouncedQ] = useState("");
  const [authSource, setAuthSource] = useState<"" | "local" | "ldap">("");
  const [activeFilter, setActiveFilter] = useState<"" | "true" | "false">("");
  const [roleFilter, setRoleFilter] = useState("");

  useEffect(() => {
    const t = setTimeout(() => setDebouncedQ(q), 300);
    return () => clearTimeout(t);
  }, [q]);

  const {
    data: users,
    isLoading,
    error,
  } = useQuery({
    queryKey: ["admin", "users", debouncedQ, authSource, activeFilter, roleFilter],
    queryFn: () =>
      listUsers({
        q: debouncedQ || undefined,
        auth_source: authSource || undefined,
        is_active: activeFilter === "" ? undefined : activeFilter === "true",
        role: roleFilter || undefined,
      }),
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
            über den LDAP-Sync angelegt. „Deaktivieren" verhindert weitere
            Logins, Audit-Bezüge bleiben erhalten.
          </p>
        </div>
        <Link to="/admin/users/new" className="btn btn-primary whitespace-nowrap self-start">
          <Plus size={14} /> Neuer User
        </Link>
      </header>

      <div className="paper mb-4 sm:mb-6 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 items-end">
        <div>
          <label htmlFor="user-search" className="label-mono mb-1.5 block">Suche</label>
          <input
            id="user-search"
            className="input"
            placeholder="Username oder Name"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
        </div>
        <div>
          <label htmlFor="user-auth-source" className="label-mono mb-1.5 block">Quelle</label>
          <select
            id="user-auth-source"
            className="input"
            value={authSource}
            onChange={(e) => setAuthSource(e.target.value as "" | "local" | "ldap")}
          >
            <option value="">Alle</option>
            <option value="local">Lokal</option>
            <option value="ldap">LDAP</option>
          </select>
        </div>
        <div>
          <label htmlFor="user-active" className="label-mono mb-1.5 block">Status</label>
          <select
            id="user-active"
            className="input"
            value={activeFilter}
            onChange={(e) => setActiveFilter(e.target.value as "" | "true" | "false")}
          >
            <option value="">Alle</option>
            <option value="true">aktiv</option>
            <option value="false">inaktiv</option>
          </select>
        </div>
        <div>
          <label htmlFor="user-role" className="label-mono mb-1.5 block">Rolle</label>
          <select
            id="user-role"
            className="input"
            value={roleFilter}
            onChange={(e) => setRoleFilter(e.target.value)}
          >
            <option value="">Alle</option>
            {roles?.map((r) => (
              <option key={r.id} value={r.name}>{r.name}</option>
            ))}
          </select>
        </div>
      </div>

      {error ? (
        <QueryError error={error} />
      ) : (
        <div className="paper p-0">
          {isLoading ? (
            <div className="py-10 text-center text-quiet italic">Lade …</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-[13px]">
                <thead>
                  <tr className="text-left text-quiet">
                    <th scope="col" className="px-4 py-2 font-mono text-[11px] uppercase tracking-wider">Username</th>
                    <th scope="col" className="px-4 py-2 font-mono text-[11px] uppercase tracking-wider">Anzeigename</th>
                    <th scope="col" className="px-4 py-2 font-mono text-[11px] uppercase tracking-wider">Quelle</th>
                    <th scope="col" className="px-4 py-2 font-mono text-[11px] uppercase tracking-wider">Rollen</th>
                    <th scope="col" className="px-4 py-2 font-mono text-[11px] uppercase tracking-wider">Letzter Login</th>
                    <th scope="col" className="px-4 py-2 font-mono text-[11px] uppercase tracking-wider">Aktiv</th>
                    <th scope="col" />
                  </tr>
                </thead>
                <tbody className="divide-y divide-rule-soft">
                  {users?.map((u) => (
                    <tr key={u.id} className="hover:bg-bg/50">
                      <td className="px-4 py-3 font-mono text-[12px]">{u.username}</td>
                      <td className="px-4 py-3">{u.display_name}</td>
                      <td className="px-4 py-3"><StatusBadge value={u.auth_source} /></td>
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
            </div>
          )}
        </div>
      )}

      {roles && (
        <p className="hint mt-4">
          Verfügbare Rollen ({roles.length}): {roles.map((r) => r.name).join(", ")}
        </p>
      )}
    </section>
  );
}
