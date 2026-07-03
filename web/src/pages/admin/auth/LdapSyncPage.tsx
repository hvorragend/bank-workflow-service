import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { listLdapSyncJobs, startLdapSync } from "@/api/admin";
import { useToast } from "@/components/Toaster";
import { formatDate } from "@/lib/utils";

export function LdapSyncPage() {
  const qc = useQueryClient();
  const { show } = useToast();
  const { data: jobs } = useQuery({
    queryKey: ["admin", "ldap", "sync"], queryFn: listLdapSyncJobs,
    refetchInterval: (query) =>
      query.state.data?.some((j) => j.status === "queued" || j.status === "running")
        ? 4000
        : false,
  });
  const [dryRun, setDryRun] = useState(false);

  const startMut = useMutation({
    mutationFn: () => startLdapSync(dryRun),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin", "ldap", "sync"] });
      show("Sync gestartet — Status erscheint unten.");
    },
    onError: (e) => show((e as Error).message, "error"),
  });

  return (
    <section>
      <header className="page-header">
        <p className="eyebrow mb-3">Admin · Auth</p>
        <h2 className="page-title">LDAP-Sync</h2>
        <p className="page-lead">
          Zieht alle User aus dem konfigurierten <code>search_base</code> in die DB
          und mappt deren Gruppen auf Rollen. Lazy-Login bleibt parallel aktiv.
        </p>
      </header>

      <div className="paper mb-6 flex flex-col sm:flex-row sm:items-center gap-4">
        <label className="inline-flex items-center gap-2 text-[13px]">
          <input type="checkbox" checked={dryRun} onChange={(e) => setDryRun(e.target.checked)} />
          Dry-Run (zählen, nicht schreiben)
        </label>
        <button className="btn btn-primary self-start" disabled={startMut.isPending}
                onClick={() => startMut.mutate()}>
          {dryRun ? "Trockenlauf starten" : "Jetzt synchronisieren"}
        </button>
      </div>

      <div className="paper p-0 overflow-x-auto">
        <table className="w-full text-[13px]">
          <thead>
            <tr className="text-left text-quiet">
              <th scope="col" className="px-4 py-2 font-mono text-[11px] uppercase tracking-wider">Job-ID</th>
              <th scope="col" className="px-4 py-2 font-mono text-[11px] uppercase tracking-wider">Status</th>
              <th scope="col" className="px-4 py-2 font-mono text-[11px] uppercase tracking-wider">Gestartet</th>
              <th scope="col" className="px-4 py-2 font-mono text-[11px] uppercase tracking-wider">Fertig</th>
              <th scope="col" className="px-4 py-2 font-mono text-[11px] uppercase tracking-wider">Counts</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-rule-soft">
            {(jobs ?? []).map((j) => (
              <tr key={j.id}>
                <td className="px-4 py-3 font-mono text-[11px]">{j.id.slice(0, 8)} {j.dry_run && <span className="badge ml-2">dry</span>}</td>
                <td className="px-4 py-3">{j.status}{j.error && <span className="text-bad ml-2">— {j.error}</span>}</td>
                <td className="px-4 py-3 text-quiet">{formatDate(j.started_at)}</td>
                <td className="px-4 py-3 text-quiet">{formatDate(j.finished_at)}</td>
                <td className="px-4 py-3 font-mono text-[11px]">
                  {Object.entries(j.counts).map(([k, v]) => `${k}:${v}`).join("  ")}
                </td>
              </tr>
            ))}
            {!jobs?.length && (
              <tr>
                <td colSpan={5} className="px-4 py-8 text-center text-quiet italic">
                  Noch keine Sync-Jobs. Klicke oben „Jetzt synchronisieren".
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}
