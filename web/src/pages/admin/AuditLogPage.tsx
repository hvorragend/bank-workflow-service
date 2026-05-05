import { useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { listAudit, type AuditEvent } from "@/api/endpoints";
import { formatDate } from "@/lib/utils";

const KATEGORIEN = [
  { value: "",           label: "Alle" },
  { value: "auth",       label: "Anmeldung" },
  { value: "definition", label: "Definitionen" },
  { value: "instance",   label: "Antraege" },
  { value: "admin",      label: "Admin" },
];

export function AuditLogPage() {
  const [kategorie, setKategorie] = useState("");
  const [akteur, setAkteur] = useState("");

  const { data, isLoading } = useQuery({
    queryKey: ["audit", kategorie, akteur],
    queryFn: () => listAudit({
      kategorie: kategorie || undefined,
      akteur:    akteur || undefined,
      limit: 200,
    }),
  });

  return (
    <section>
      <header className="mb-10 max-w-[720px]">
        <p className="eyebrow mb-3">Admin · Audit-Log</p>
        <h2 className="font-display font-display font-normal text-[40px] leading-[1.1] tracking-tightish">
          Audit-Eintraege
        </h2>
        <p className="mt-4 text-[15.5px] text-muted">
          Revisionssichere Historie aller sicherheitsrelevanten Ereignisse —
          Anmeldungen, Definitions-Aenderungen, Admin-Aktionen.
        </p>
      </header>

      <div className="paper mb-6 grid grid-cols-1 sm:grid-cols-3 gap-4 items-end">
        <div>
          <label className="label-mono mb-1.5 block">Kategorie</label>
          <select className="input" value={kategorie} onChange={(e) => setKategorie(e.target.value)}>
            {KATEGORIEN.map((k) => <option key={k.value} value={k.value}>{k.label}</option>)}
          </select>
        </div>
        <div>
          <label className="label-mono mb-1.5 block">Akteur (Username)</label>
          <input
            className="input"
            placeholder="Beliebig"
            value={akteur}
            onChange={(e) => setAkteur(e.target.value)}
          />
        </div>
        <div className="text-right text-[12px] text-quiet">
          {isLoading ? "Lade …" : `${data?.length ?? 0} Eintraege`}
        </div>
      </div>

      <div className="paper p-0">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-rule">
              <th className="label-mono pb-3 px-4 text-left w-[170px]">Zeit</th>
              <th className="label-mono pb-3 px-4 text-left w-[110px]">Kategorie</th>
              <th className="label-mono pb-3 px-4 text-left">Aktion</th>
              <th className="label-mono pb-3 px-4 text-left">Akteur</th>
              <th className="label-mono pb-3 px-4 text-left">Ziel</th>
              <th className="label-mono pb-3 px-4 text-left">IP</th>
            </tr>
          </thead>
          <tbody>
            {data?.map((e: AuditEvent) => (
              <tr key={e.id} className="border-b border-rule-soft last:border-0">
                <td className="py-3 px-4 font-mono text-[12px] text-quiet">{formatDate(e.zeitstempel)}</td>
                <td className="py-3 px-4">
                  <span className="badge badge-active uppercase tracking-wider text-[10px]">{e.kategorie}</span>
                </td>
                <td className="py-3 px-4 font-mono text-[12px]">{e.action}</td>
                <td className="py-3 px-4 text-[13px]">{e.akteur ?? <span className="text-quiet italic">—</span>}</td>
                <td className="py-3 px-4 text-[12px] text-muted">
                  {e.target_type ? (
                    <>
                      <span className="font-mono">{e.target_type}</span>
                      {e.target_id && <span className="text-quiet"> · {e.target_id.slice(0, 8)}</span>}
                    </>
                  ) : (
                    <span className="text-quiet italic">—</span>
                  )}
                </td>
                <td className="py-3 px-4 font-mono text-[12px] text-quiet">{e.ip ?? "—"}</td>
              </tr>
            ))}
            {data?.length === 0 && (
              <tr>
                <td colSpan={6} className="py-10 text-center text-quiet italic">
                  Keine Eintraege fuer diese Filter.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}
