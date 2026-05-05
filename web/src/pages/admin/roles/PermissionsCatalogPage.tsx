import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";

import { listPermissions } from "@/api/admin";

export function PermissionsCatalogPage() {
  const { data, isLoading } = useQuery({
    queryKey: ["admin", "permissions"], queryFn: listPermissions,
  });
  const grouped = useMemo(() => {
    const m: Record<string, typeof data> = {};
    for (const p of data ?? []) (m[p.area] ??= []).push(p);
    return m;
  }, [data]);

  return (
    <section>
      <header className="page-header">
        <p className="eyebrow mb-3">Admin · Permissions</p>
        <h2 className="page-title">Permission-Katalog</h2>
        <p className="page-lead">
          Read-only — Quelle der Wahrheit ist <code>backend/app/auth/permission_catalog.py</code>.
          Beim App-Start werden neue Permissions automatisch angelegt.
        </p>
      </header>
      {isLoading ? (
        <div className="paper py-10 text-center text-quiet italic">Lade …</div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {Object.entries(grouped).map(([area, perms]) => (
            <div key={area} className="paper">
              <p className="label-mono mb-2">{area}</p>
              <ul className="flex flex-col gap-2">
                {perms?.map((p) => (
                  <li key={p.code} className="text-[13px]">
                    <code className="text-ink">{p.code}</code>
                    <p className="text-quiet text-[12px]">{p.description}</p>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
