import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, Upload } from "lucide-react";
import { Link } from "react-router-dom";

import {
  activateDefinition,
  listDefinitions,
  retireDefinition,
} from "@/api/endpoints";
import { useToast } from "@/components/Toaster";
import { cn } from "@/lib/utils";
import type { FormDefinition } from "@/types/api";

export function AdminDefinitionsPage() {
  const qc = useQueryClient();
  const { show } = useToast();
  const { data: defs, isLoading } = useQuery({
    queryKey: ["definitions", "admin"],
    queryFn: () => listDefinitions(),
  });

  const activateMut = useMutation({
    mutationFn: activateDefinition,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["definitions"] });
      show("Definition aktiviert. Vorgaengerversion wurde retired.");
    },
    onError: (e) => show(`Aktivierung fehlgeschlagen: ${(e as Error).message}`, "error"),
  });

  const retireMut = useMutation({
    mutationFn: retireDefinition,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["definitions"] });
      show("Definition retired.");
    },
    onError: (e) => show(`Retire fehlgeschlagen: ${(e as Error).message}`, "error"),
  });

  return (
    <section>
      <header className="mb-10 flex items-end justify-between gap-6 max-w-[920px]">
        <div>
          <p className="eyebrow mb-3">Admin · Definitionen</p>
          <h2 className="font-display font-display font-normal text-[40px] leading-[1.1] tracking-tightish">
            Maskenverwaltung
          </h2>
          <p className="mt-4 text-[15.5px] text-muted">
            Lade neue Maskenversionen hoch, aktiviere Entwuerfe oder retire
            aktive Versionen. Aktivieren retired automatisch die jeweils aktive
            Version desselben Typs — die Versions-Garantie bleibt erhalten.
          </p>
        </div>
        <Link to="/admin/upload" className="btn inline-flex items-center gap-2 whitespace-nowrap">
          <Upload size={14} /> Neue Version hochladen
        </Link>
      </header>

      <div className="paper">
        {isLoading ? (
          <div className="py-10 text-center text-quiet italic">Lade …</div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-rule">
                <Th>Typ</Th>
                <Th>Version</Th>
                <Th>Titel</Th>
                <Th>Status</Th>
                <Th>Aktionen</Th>
              </tr>
            </thead>
            <tbody>
              {defs?.map((d: FormDefinition) => (
                <tr key={d.id} className="border-b border-rule-soft last:border-0">
                  <Td><span className="font-mono text-[13px]">{d.typ}</span></Td>
                  <Td><span className="font-mono text-[13px]">{d.version}</span></Td>
                  <Td><span className="text-[13px] text-muted">{d.titel}</span></Td>
                  <Td><span className={`badge badge-${d.status}`}>{d.status}</span></Td>
                  <Td>
                    <div className="flex gap-2">
                      {d.status === "draft" && (
                        <button
                          className="btn btn-ok text-[12px] px-3 py-1.5"
                          disabled={activateMut.isPending}
                          onClick={() => activateMut.mutate(d.id)}
                        >
                          Aktivieren
                        </button>
                      )}
                      {d.status === "active" && (
                        <button
                          className="btn btn-warn text-[12px] px-3 py-1.5"
                          disabled={retireMut.isPending}
                          onClick={() => {
                            if (confirm(`Wirklich retire? Neue Antraege gegen ${d.typ} ${d.version} sind danach nicht mehr moeglich.`)) {
                              retireMut.mutate(d.id);
                            }
                          }}
                        >
                          Retire
                        </button>
                      )}
                      {/* Diff-Link nur sichtbar, wenn es eine andere Version desselben Typs gibt */}
                      <DiffLink current={d} all={defs ?? []} />
                    </div>
                  </Td>
                </tr>
              ))}
              {defs?.length === 0 && (
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
    </section>
  );
}

function DiffLink({ current, all }: { current: FormDefinition; all: FormDefinition[] }) {
  // Vorgaenger des Typs finden — naechst kleinere Version, sortiert lexikographisch
  const peers = all
    .filter((d) => d.typ === current.typ && d.id !== current.id)
    .sort((a, b) => a.version.localeCompare(b.version));
  const previous = peers.filter((p) => p.version < current.version).pop();
  if (!previous) return null;
  return (
    <Link
      to={`/admin/diff/${previous.id}/${current.id}`}
      className="btn btn-ghost text-[12px] px-3 py-1.5 inline-flex items-center gap-1.5"
    >
      Diff zu {previous.version} <ArrowRight size={12} />
    </Link>
  );
}

function Th({ children }: { children: React.ReactNode }) {
  return <th className={cn("label-mono pb-3 px-4 text-left")}>{children}</th>;
}
function Td({ children }: { children: React.ReactNode }) {
  return <td className="py-4 px-4 align-middle">{children}</td>;
}
