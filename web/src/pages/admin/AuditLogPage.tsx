import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { listAudit, type AuditEvent } from "@/api/endpoints";
import { formatDate } from "@/lib/utils";

const KATEGORIEN = [
  { value: "",           label: "Alle" },
  { value: "auth",       label: "Anmeldung" },
  { value: "definition", label: "Definitionen" },
  { value: "instance",   label: "Anträge" },
  { value: "admin",      label: "Admin" },
];

export function AuditLogPage() {
  const [kategorie, setKategorie] = useState("");
  const [akteur, setAkteur] = useState("");
  const [debouncedAkteur, setDebouncedAkteur] = useState("");

  useEffect(() => {
    const t = setTimeout(() => setDebouncedAkteur(akteur), 300);
    return () => clearTimeout(t);
  }, [akteur]);

  const { data, isLoading } = useQuery({
    queryKey: ["audit", kategorie, debouncedAkteur],
    queryFn: () => listAudit({
      kategorie: kategorie || undefined,
      akteur:    debouncedAkteur || undefined,
      limit: 200,
    }),
  });

  return (
    <section>
      <header className="page-header">
        <p className="eyebrow mb-3">Admin · Audit-Log</p>
        <h2 className="page-title">Audit-Einträge</h2>
        <p className="page-lead">
          Revisionssichere Historie aller sicherheitsrelevanten Ereignisse —
          Anmeldungen, Definitions-Änderungen, Admin-Aktionen.
        </p>
      </header>

      <div className="paper mb-4 sm:mb-6 grid grid-cols-1 sm:grid-cols-3 gap-4 items-end">
        <div>
          <label htmlFor="audit-kategorie" className="label-mono mb-1.5 block">Kategorie</label>
          <select id="audit-kategorie" className="input" value={kategorie} onChange={(e) => setKategorie(e.target.value)}>
            {KATEGORIEN.map((k) => <option key={k.value} value={k.value}>{k.label}</option>)}
          </select>
        </div>
        <div>
          <label htmlFor="audit-akteur" className="label-mono mb-1.5 block">Akteur (Username)</label>
          <input
            id="audit-akteur"
            className="input"
            placeholder="Beliebig"
            value={akteur}
            onChange={(e) => setAkteur(e.target.value)}
          />
        </div>
        <div className="text-left sm:text-right text-[12px] text-quiet">
          {isLoading ? "Lade …" : `${data?.length ?? 0} Einträge`}
        </div>
      </div>

      <div className="paper p-0">
        {/* Mobile: Karten */}
        <ul className="md:hidden divide-y divide-rule-soft">
          {data?.map((e: AuditEvent) => (
            <li key={e.id} className="px-4 py-4">
              <div className="flex items-start justify-between gap-3">
                <div className="font-mono text-[12px] text-quiet">{formatDate(e.zeitstempel)}</div>
                <span className="badge badge-neutral text-[10px]">{e.kategorie}</span>
              </div>
              <div className="mt-2 font-mono text-[12px]">{e.action}</div>
              <div className="mt-1 text-[12px] text-muted">
                {e.akteur ?? <span className="text-quiet italic">—</span>}
                {e.target_type && (
                  <>
                    {" · "}
                    <span className="font-mono">{e.target_type}</span>
                    {e.target_id && <span className="text-quiet"> · {e.target_id.slice(0, 8)}</span>}
                  </>
                )}
                {e.ip && <> · <span className="font-mono text-quiet">{e.ip}</span></>}
              </div>
            </li>
          ))}
          {data?.length === 0 && (
            <li className="py-10 text-center text-quiet italic">
              Keine Einträge für diese Filter.
            </li>
          )}
        </ul>

        {/* Desktop: Tabelle */}
        <div className="hidden md:block overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-rule">
                <th scope="col" className="label-mono pb-3 pt-5 px-4 sm:px-6 text-left w-[170px]">Zeit</th>
                <th scope="col" className="label-mono pb-3 pt-5 px-4 sm:px-6 text-left w-[110px]">Kategorie</th>
                <th scope="col" className="label-mono pb-3 pt-5 px-4 sm:px-6 text-left">Aktion</th>
                <th scope="col" className="label-mono pb-3 pt-5 px-4 sm:px-6 text-left">Akteur</th>
                <th scope="col" className="label-mono pb-3 pt-5 px-4 sm:px-6 text-left">Ziel</th>
                <th scope="col" className="label-mono pb-3 pt-5 px-4 sm:px-6 text-left">IP</th>
              </tr>
            </thead>
            <tbody>
              {data?.map((e: AuditEvent) => (
                <tr key={e.id} className="border-b border-rule-soft last:border-0 hover:bg-bg transition-colors">
                  <td className="py-3 px-4 sm:px-6 font-mono text-[12px] text-quiet">{formatDate(e.zeitstempel)}</td>
                  <td className="py-3 px-4 sm:px-6">
                    <span className="badge badge-neutral uppercase tracking-wider text-[10px]">{e.kategorie}</span>
                  </td>
                  <td className="py-3 px-4 sm:px-6 font-mono text-[12px]">{e.action}</td>
                  <td className="py-3 px-4 sm:px-6 text-[13px]">{e.akteur ?? <span className="text-quiet italic">—</span>}</td>
                  <td className="py-3 px-4 sm:px-6 text-[12px] text-muted">
                    {e.target_type ? (
                      <>
                        <span className="font-mono">{e.target_type}</span>
                        {e.target_id && <span className="text-quiet"> · {e.target_id.slice(0, 8)}</span>}
                      </>
                    ) : (
                      <span className="text-quiet italic">—</span>
                    )}
                  </td>
                  <td className="py-3 px-4 sm:px-6 font-mono text-[12px] text-quiet">{e.ip ?? "—"}</td>
                </tr>
              ))}
              {data?.length === 0 && (
                <tr>
                  <td colSpan={6} className="py-10 text-center text-quiet italic">
                    Keine Einträge für diese Filter.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
}
