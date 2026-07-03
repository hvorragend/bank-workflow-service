import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { createApiToken, listApiTokens, revokeApiToken } from "@/api/admin";
import { QueryError } from "@/components/QueryStates";
import { useToast } from "@/components/Toaster";
import { formatDate } from "@/lib/utils";

export function ApiTokensPage() {
  const qc = useQueryClient();
  const { show } = useToast();
  const { data, isLoading, error } = useQuery({
    queryKey: ["admin", "api-tokens"], queryFn: listApiTokens,
  });
  const [name, setName] = useState("");
  const [expires, setExpires] = useState("");
  const [createdToken, setCreatedToken] = useState<string | null>(null);

  const createMut = useMutation({
    mutationFn: () => createApiToken({
      name, expires_at: expires ? new Date(expires).toISOString() : null,
    }),
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: ["admin", "api-tokens"] });
      setCreatedToken(r.token);
      setName(""); setExpires("");
      show(`Token ${r.name} angelegt — bitte sofort kopieren.`);
    },
    onError: (e) => show((e as Error).message, "error"),
  });

  const revokeMut = useMutation({
    mutationFn: revokeApiToken,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin", "api-tokens"] });
      show("Token widerrufen.");
    },
    onError: (e) => show((e as Error).message, "error"),
  });

  return (
    <section>
      <header className="page-header">
        <p className="eyebrow mb-3">Admin · System</p>
        <h2 className="page-title">Reporting-API-Tokens</h2>
        <p className="page-lead">
          Tokens für den schreibgeschützten <code>/reporting</code>-Endpunkt.
          Klartext nur einmalig sichtbar.
        </p>
      </header>

      <div className="paper mb-6 grid gap-3 md:grid-cols-[2fr_1fr_auto]">
        <label className="flex flex-col gap-1">
          <span className="label-mono">Name</span>
          <input id="token-name" className="input" placeholder="Name (z. B. Aufsicht 2026)"
                 value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        <label className="flex flex-col gap-1">
          <span className="label-mono">Läuft ab</span>
          <input id="token-expires" className="input" type="date" value={expires}
                 onChange={(e) => setExpires(e.target.value)} />
        </label>
        <button className="btn btn-primary self-end" disabled={!name || createMut.isPending}
                onClick={() => createMut.mutate()}>Anlegen</button>
      </div>

      {createdToken && (
        <div className="paper border-warn mb-6 bg-warn-soft">
          <p className="label-mono mb-2 text-warn">Klartext-Token (nur einmal sichtbar)</p>
          <code className="font-mono text-[12px] break-all">{createdToken}</code>
          <div className="flex gap-2 mt-3">
            <button className="btn btn-primary self-start" onClick={() => {
              navigator.clipboard.writeText(createdToken)
                .then(() => show("Token in die Zwischenablage kopiert."))
                .catch(() => show("Kopieren fehlgeschlagen.", "error"));
            }}>
              Kopieren
            </button>
            <button className="btn btn-ghost self-start" onClick={() => setCreatedToken(null)}>
              Schließen
            </button>
          </div>
        </div>
      )}

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
                  <th scope="col" className="px-4 py-2 font-mono text-[11px] uppercase tracking-wider">Name</th>
                  <th scope="col" className="px-4 py-2 font-mono text-[11px] uppercase tracking-wider">Erstellt</th>
                  <th scope="col" className="px-4 py-2 font-mono text-[11px] uppercase tracking-wider">Läuft ab</th>
                  <th scope="col" className="px-4 py-2 font-mono text-[11px] uppercase tracking-wider">Letzte Nutzung</th>
                  <th scope="col" className="px-4 py-2 font-mono text-[11px] uppercase tracking-wider">Status</th>
                  <th />
                </tr>
              </thead>
              <tbody className="divide-y divide-rule-soft">
                {data?.map((t) => (
                  <tr key={t.id}>
                    <td className="px-4 py-3 font-medium">{t.name}</td>
                    <td className="px-4 py-3 text-quiet">{formatDate(t.created_at)} · {t.created_by}</td>
                    <td className="px-4 py-3 text-quiet">{formatDate(t.expires_at) || "—"}</td>
                    <td className="px-4 py-3 text-quiet">{formatDate(t.last_used_at) || "nie"}</td>
                    <td className="px-4 py-3">{t.revoked_at ? "widerrufen" : "aktiv"}</td>
                    <td className="px-4 py-3 text-right">
                      {!t.revoked_at && (
                        <button className="btn btn-ghost text-bad text-[12px] px-2 py-1"
                                onClick={() => { if (confirm(`Token ${t.name} widerrufen?`)) revokeMut.mutate(t.id); }}>
                          Widerrufen
                        </button>
                      )}
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
