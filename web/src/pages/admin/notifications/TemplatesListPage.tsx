import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { listTemplates } from "@/api/admin";
import { QueryError } from "@/components/QueryStates";
import { formatDate } from "@/lib/utils";

export function TemplatesListPage() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["admin", "templates"], queryFn: listTemplates,
  });
  return (
    <section>
      <header className="page-header">
        <p className="eyebrow mb-3">Admin · Notifications</p>
        <h2 className="page-title">E-Mail-Templates</h2>
        <p className="page-lead">
          Variablen-Syntax: <code>$varname</code> (string.Template). Unbekannte
          Variablen bleiben als Platzhalter stehen — kein Crash.
        </p>
      </header>
      <div className="paper p-0">
        {error ? (
          <QueryError error={error} />
        ) : isLoading ? (
          <div className="py-10 text-center text-quiet italic">Lade …</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-[13px]">
              <thead>
                <tr className="text-left text-quiet">
                  <th scope="col" className="px-4 py-2 font-mono text-[11px] uppercase tracking-wider">Key</th>
                  <th scope="col" className="px-4 py-2 font-mono text-[11px] uppercase tracking-wider">Subject</th>
                  <th scope="col" className="px-4 py-2 font-mono text-[11px] uppercase tracking-wider">Geändert</th>
                  <th />
                </tr>
              </thead>
              <tbody className="divide-y divide-rule-soft">
                {data?.map((t) => (
                  <tr key={t.key}>
                    <td className="px-4 py-3 font-mono text-[12px]">{t.key}</td>
                    <td className="px-4 py-3">{t.subject}</td>
                    <td className="px-4 py-3 text-quiet text-[12px]">
                      {formatDate(t.updated_at)} · {t.updated_by}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <Link to={`/admin/notifications/templates/${t.key}`}
                            className="btn btn-ghost text-[12px] px-2 py-1">
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
    </section>
  );
}
