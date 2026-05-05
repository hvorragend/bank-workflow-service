import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Download } from "lucide-react";
import { Link } from "react-router-dom";

import { exportInstancesCsv, listDefinitions, listInstances, type ListInstancesParams } from "@/api/endpoints";
import { useToast } from "@/components/Toaster";
import { formatDate, humanize } from "@/lib/utils";
import type { FormInstance } from "@/types/api";

const ABGESCHLOSSEN_STATUS = ["genehmigt", "abgelehnt", "zurueckgewiesen"];

function instanceTitle(i: FormInstance): string {
  return i.daten?.vorhaben?.titel || i.daten?.beschluss?.titel || "(ohne Titel)";
}

export function ArchivePage() {
  const { show } = useToast();
  const [typ, setTyp] = useState<string>("");
  const [version, setVersion] = useState<string>("");
  const [status, setStatus] = useState<string>(""); // "" = alle abgeschlossenen
  const [createdFrom, setCreatedFrom] = useState<string>("");
  const [createdTo, setCreatedTo] = useState<string>("");
  const [sort, setSort] = useState<"created_desc" | "created_asc" | "updated_desc">("created_desc");

  const { data: defs } = useQuery({
    queryKey: ["definitions"],
    queryFn: () => listDefinitions(),
  });
  const typen = useMemo(
    () => Array.from(new Set((defs ?? []).map((d) => d.typ))).sort(),
    [defs],
  );
  const versionen = useMemo(
    () => Array.from(new Set((defs ?? []).filter((d) => !typ || d.typ === typ).map((d) => d.version))).sort(),
    [defs, typ],
  );

  const params: ListInstancesParams = useMemo(() => {
    const p: ListInstancesParams = {
      status: status ? [status] : ABGESCHLOSSEN_STATUS,
      sort,
      limit: 200,
    };
    if (typ) p.typ = typ;
    if (version) p.version = version;
    if (createdFrom) p.created_from = `${createdFrom}T00:00:00Z`;
    if (createdTo) p.created_to = `${createdTo}T23:59:59Z`;
    return p;
  }, [typ, version, status, createdFrom, createdTo, sort]);

  const { data: instances, isLoading } = useQuery({
    queryKey: ["instances", "archive", params],
    queryFn: () => listInstances(params),
  });

  async function onExport() {
    try {
      const blob = await exportInstancesCsv(params);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `archiv-${new Date().toISOString().slice(0, 10)}.csv`;
      a.click();
      URL.revokeObjectURL(url);
      show("CSV-Export gestartet.");
    } catch (e) {
      show(`Export fehlgeschlagen: ${(e as Error).message}`, "error");
    }
  }

  return (
    <section>
      <header className="mb-10 max-w-[720px]">
        <p className="eyebrow mb-3">Archiv</p>
        <h2 className="font-display font-display font-normal text-[40px] leading-[1.1] tracking-tightish">
          Abgeschlossene Antraege
        </h2>
        <p className="mt-4 text-[15.5px] text-muted">
          Hier finden Sie alle genehmigten, abgelehnten und zurueckgewiesenen
          Antraege. Filter nach Typ, Version, Datum oder Status — Export als
          CSV fuer die Revision.
        </p>
      </header>

      <div className="grid grid-cols-1 lg:grid-cols-[280px_1fr] gap-8">
        {/* Filter-Sidebar */}
        <aside className="paper p-6 lg:sticky lg:top-32 lg:self-start">
          <p className="eyebrow mb-4">Filter</p>
          <div className="space-y-4">
            <div>
              <label className="label-mono mb-1.5 block">Typ</label>
              <select className="input" value={typ} onChange={(e) => { setTyp(e.target.value); setVersion(""); }}>
                <option value="">Alle</option>
                {typen.map((t) => <option key={t} value={t}>{t}</option>)}
              </select>
            </div>
            <div>
              <label className="label-mono mb-1.5 block">Version</label>
              <select className="input" value={version} onChange={(e) => setVersion(e.target.value)} disabled={!typ}>
                <option value="">Alle</option>
                {versionen.map((v) => <option key={v} value={v}>{v}</option>)}
              </select>
            </div>
            <div>
              <label className="label-mono mb-1.5 block">Status</label>
              <select className="input" value={status} onChange={(e) => setStatus(e.target.value)}>
                <option value="">Alle abgeschlossenen</option>
                <option value="genehmigt">genehmigt</option>
                <option value="abgelehnt">abgelehnt</option>
                <option value="zurueckgewiesen">zurueckgewiesen</option>
              </select>
            </div>
            <div>
              <label className="label-mono mb-1.5 block">Erstellt von</label>
              <input type="date" className="input" value={createdFrom} onChange={(e) => setCreatedFrom(e.target.value)} />
            </div>
            <div>
              <label className="label-mono mb-1.5 block">Erstellt bis</label>
              <input type="date" className="input" value={createdTo} onChange={(e) => setCreatedTo(e.target.value)} />
            </div>
            <div>
              <label className="label-mono mb-1.5 block">Sortierung</label>
              <select className="input" value={sort} onChange={(e) => setSort(e.target.value as any)}>
                <option value="created_desc">Erstellt (neueste zuerst)</option>
                <option value="created_asc">Erstellt (aelteste zuerst)</option>
                <option value="updated_desc">Zuletzt bewegt</option>
              </select>
            </div>
          </div>
          <button onClick={onExport} className="btn btn-ghost mt-6 w-full inline-flex items-center justify-center gap-2">
            <Download size={14} /> Als CSV exportieren
          </button>
        </aside>

        {/* Liste */}
        <div>
          <p className="text-[12px] text-quiet mb-3">
            {isLoading ? "Lade …" : `${instances?.length ?? 0} Eintraege`}
          </p>
          {isLoading && (
            <div className="border border-dashed border-rule py-20 text-center text-muted italic">
              Lade Archiv …
            </div>
          )}
          {instances && instances.length === 0 && (
            <div className="border border-dashed border-rule py-20 text-center text-muted italic">
              Keine Eintraege fuer diese Filter.
            </div>
          )}
          {instances && instances.length > 0 && (
            <div className="flex flex-col">
              {instances.map((i) => (
                <Link
                  key={i.id}
                  to={`/antraege/${i.id}`}
                  className="grid grid-cols-[1fr_auto_auto] gap-8 items-center px-6 py-5 border border-rule -mb-px last:mb-0 bg-paper hover:bg-[#fdfaf3] transition cursor-pointer"
                >
                  <div>
                    <h4 className="font-display font-display font-medium text-[16px] tracking-tightish m-0">
                      {instanceTitle(i)}
                    </h4>
                    <div className="mt-1 font-mono text-[11px] text-quiet">
                      <span className="text-accent">{i.schema_version}</span>{" "}
                      ·  ID {i.id.slice(0, 8)} ·  von {i.antragsteller}
                      {i.abgeschlossen_am && ` ·  abgeschlossen ${formatDate(i.abgeschlossen_am)}`}
                    </div>
                  </div>
                  <div className="font-mono text-[11px] uppercase tracking-wider text-muted">
                    {humanize(i.aktuelle_stage)}
                  </div>
                  <span className={`badge badge-${i.status}`}>{i.status}</span>
                </Link>
              ))}
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
