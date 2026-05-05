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
      <header className="mb-10 max-w-[720px]">
        <p className="eyebrow mb-3">01 · Maskendefinitionen</p>
        <h2 className="font-display font-display font-normal text-[40px] leading-[1.1] tracking-tightish">
          Versionierte Formularvorlagen
        </h2>
        <p className="mt-4 text-[15.5px] text-muted">
          Jede Definition ist unveraenderlich, sobald sie aktiv ist. Ein Antrag,
          der gegen eine bestimmte Version erstellt wurde, bleibt fuer immer an
          genau diese Version gebunden — auch dann noch, wenn die Maske spaeter
          Felder gewinnt oder verliert.
        </p>
      </header>

      <div className="paper">
        {isLoading && <div className="py-10 text-center text-quiet italic">Lade Definitionen …</div>}
        {error && <div className="py-10 text-center text-bad">{(error as Error).message}</div>}
        {data && (
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
                <tr key={d.id} className="border-b border-rule-soft last:border-0">
                  <Td>
                    <div className="font-mono font-medium text-[13px]">{d.typ}</div>
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
        )}
      </div>

      <div className="mt-4 border-l-2 border-rule bg-bg px-5 py-4 text-[13px] text-muted">
        <strong>Hinweis zum Versionsmodell:</strong> Beim erstmaligen Start des
        Backends werden zwei Beispiel-Versionen geseeded — <span className="font-mono text-xs bg-paper px-1.5 py-0.5 border border-rule-soft">v1.0.0</span>{" "}
        (retired) und <span className="font-mono text-xs bg-paper px-1.5 py-0.5 border border-rule-soft">v2.0.0</span>{" "}
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
        "label-mono pb-3 px-4",
        align === "right" ? "text-right" : "text-left",
      )}
    >
      {children}
    </th>
  );
}

function Td({ children, align = "left" }: { children: React.ReactNode; align?: "left" | "right" }) {
  return (
    <td className={cn("py-4 px-4 align-top", align === "right" && "text-right")}>
      {children}
    </td>
  );
}
