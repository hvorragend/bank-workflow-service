import { useQuery } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { Link } from "react-router-dom";

import { listRoles } from "@/api/admin";
import { QueryError } from "@/components/QueryStates";

export function RolesListPage() {
  const { data: roles, isLoading, error } = useQuery({
    queryKey: ["admin", "roles"],
    queryFn: listRoles,
  });

  return (
    <section>
      <header className="page-header flex flex-col sm:flex-row sm:items-end sm:justify-between gap-4">
        <div>
          <p className="eyebrow mb-3">Admin · Rollen</p>
          <h2 className="page-title">Rollen</h2>
          <p className="page-lead">
            Eine Rolle ist eine zuweisbare Sammlung von Permissions. Die Rolle „Admin"
            ist eine System-Rolle und nicht löschbar — sie hält automatisch alle
            Permissions aus dem Katalog.
          </p>
        </div>
        <Link to="/admin/roles/new" className="btn btn-primary self-start">
          <Plus size={14} /> Neue Rolle
        </Link>
      </header>

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
                    <th scope="col" className="px-4 py-2 font-mono text-[11px] uppercase tracking-wider">Name</th>
                    <th scope="col" className="px-4 py-2 font-mono text-[11px] uppercase tracking-wider">Beschreibung</th>
                    <th scope="col" className="px-4 py-2 font-mono text-[11px] uppercase tracking-wider">Permissions</th>
                    <th scope="col" className="px-4 py-2 font-mono text-[11px] uppercase tracking-wider">System</th>
                    <th scope="col" />
                  </tr>
                </thead>
                <tbody className="divide-y divide-rule-soft">
                  {roles?.map((r) => (
                    <tr key={r.id}>
                      <td className="px-4 py-3 font-medium">{r.name}</td>
                      <td className="px-4 py-3 text-muted">{r.description || "—"}</td>
                      <td className="px-4 py-3 text-quiet text-[12px]">{r.permission_codes.length}</td>
                      <td className="px-4 py-3">{r.is_system ? "ja" : "—"}</td>
                      <td className="px-4 py-3 text-right">
                        <Link to={`/admin/roles/${r.id}`} className="btn btn-ghost text-[12px] px-2 py-1">
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
    </section>
  );
}
