import { useQuery } from "@tanstack/react-query";

import { listDefinitions } from "@/api/endpoints";
import { countFields } from "@/lib/schema-rules";
import { cn } from "@/lib/utils";

export function DefinitionsPage() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["definitions"],
    queryFn: () => listDefinitions(),
  });

  return (
    <section>
      <header className="page-header">
        <p className="eyebrow mb-3">01 · Maskendefinitionen</p>
        <h2 className="page-title">Versionierte Formularvorlagen</h2>
        <p className="page-lead">
          Jede Definition ist unveraenderlich, sobald sie aktiv ist. Ein Antrag,
          der gegen eine bestimmte Version erstellt wurde, bleibt fuer immer an
          genau diese Version gebunden — auch dann noch, wenn die Maske spaeter
          Felder gewinnt oder verliert.
        </p>
      </header>

      <div className="paper p-0 sm:p-0">
        {isLoading && <div className="py-10 text-center text-quiet italic">Lade Definitionen …</div>}
        {error && <div className="py-10 text-center text-bad">{(error as Error).message}</div>}

        {/* Mobile: Karten-Liste */}
        {data && (
          <ul className="md:hidden divide-y divide-rule-soft">
            {data.map((d) => (
              <li key={d.id} className="px-4 py-4">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="font-mono text-[13px] font-semibold text-ink">{d.typ}</div>
                    <div className="mt-0.5 text-[13px] text-muted">{d.titel}</div>
                  </div>
                  <span className={`badge badge-${d.status} shrink-0`}>{d.status}</span>
                </div>
                <div className="mt-3 grid grid-cols-2 gap-3 text-[12px]">
                  <div>
                    <div className="label-mono mb-0.5">Version</div>
                    <span className="font-mono">{d.version}</span>
                  </div>
                  <div>
                    <div className="label-mono mb-0.5">Felder</div>
                    <span className="font-mono">{countFields(d.json_schema)}</span>
                  </div>
                  <div className="col-span-2">
                    <div className="label-mono mb-0.5">Genehmigungsweg</div>
                    <div className="text-[12px] text-muted leading-snug">
                      {d.workflow_stages.map((s, i) => (
                        <span key={i}>
                          {s.rolle}
                          {i < d.workflow_stages.length - 1 && " → "}
                        </span>
                      ))}
                    </div>
                  </div>
                </div>
              </li>
            ))}
            {data.length === 0 && (
              <li className="py-10 text-center text-quiet italic">
                Keine Definitionen vorhanden.
              </li>
            )}
          </ul>
        )}

        {/* Desktop: Tabelle */}
        {data && (
          <div className="hidden md:block overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-rule">
                  <Th width="38%">Typ &amp; Titel</Th>
                  <Th width="14%">Version</Th>
                  <Th width="14%">Status</Th>
                  <Th width="22%">Genehmigungsweg</Th>
                  <Th width="12%" align="right">Felder</Th>
                </tr>
              </thead>
              <tbody>
                {data.map((d) => (
                  <tr key={d.id} className="border-b border-rule-soft last:border-0 hover:bg-bg transition-colors">
                    <Td>
                      <div className="font-mono font-semibold text-[13px]">{d.typ}</div>
                      <div className="mt-0.5 text-[13px] text-muted">{d.titel}</div>
                    </Td>
                    <Td><span className="font-mono text-[13px]">{d.version}</span></Td>
                    <Td><span className={`badge badge-${d.status}`}>{d.status}</span></Td>
                    <Td>
                      <div className="text-xs text-muted">
                        {d.workflow_stages.map((s, i) => (
                          <span key={i}>
                            {s.rolle}
                            {i < d.workflow_stages.length - 1 && " → "}
                          </span>
                        ))}
                      </div>
                    </Td>
                    <Td align="right">
                      <span className="font-mono text-[13px]">{countFields(d.json_schema)}</span>
                    </Td>
                  </tr>
                ))}
                {data.length === 0 && (
                  <tr>
                    <td colSpan={5} className="py-10 text-center text-quiet italic">
                      Keine Definitionen vorhanden.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="hint hint-info mt-4">
        <strong>Hinweis zum Versionsmodell:</strong> Beim erstmaligen Start des
        Backends werden zwei Beispiel-Versionen geseeded — <span className="font-mono text-xs bg-paper px-1.5 py-0.5 border border-rule-soft rounded">v1.0.0</span>{" "}
        (retired) und <span className="font-mono text-xs bg-paper px-1.5 py-0.5 border border-rule-soft rounded">v2.0.0</span>{" "}
        (active). Wechsle zur Antraege-Liste, um zu sehen, dass v1-Antraege das v2-Feld nicht zeigen.
      </div>
    </section>
  );
}

function Th({ children, width, align = "left" }: { children: React.ReactNode; width?: string; align?: "left" | "right" }) {
  return (
    <th
      style={{ width }}
      className={cn(
        "label-mono pb-3 pt-5 px-4 sm:px-6",
        align === "right" ? "text-right" : "text-left",
      )}
    >
      {children}
    </th>
  );
}

function Td({ children, align = "left" }: { children: React.ReactNode; align?: "left" | "right" }) {
  return (
    <td className={cn("py-4 px-4 sm:px-6 align-top", align === "right" && "text-right")}>
      {children}
    </td>
  );
}
