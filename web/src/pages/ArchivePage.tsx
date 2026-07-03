import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Download, SlidersHorizontal } from "lucide-react";
import { Link } from "react-router-dom";

import { exportInstancesCsv, listDefinitions, listInstances, type ListInstancesParams } from "@/api/endpoints";
import { StatusBadge } from "@/components/StatusBadge";
import { useToast } from "@/components/Toaster";
import { formatDate, instanceTitle } from "@/lib/utils";

const ABGESCHLOSSEN_STATUS = ["genehmigt", "abgelehnt", "zurueckgewiesen"];

/**
 * Wandelt ein <input type=date>-Datum (lokal) in einen ISO-Zeitpunkt um.
 * Frueher wurde `${d}T00:00:00Z` (UTC) angehaengt — das verschiebt den Filter
 * je nach Zeitzone um Stunden. Jetzt bauen wir den lokalen Tagesrand und
 * lassen toISOString() korrekt nach UTC umrechnen (F-037).
 */
function localDateStart(d: string): string {
  return new Date(`${d}T00:00:00`).toISOString();
}
function localDateEnd(d: string): string {
  return new Date(`${d}T23:59:59.999`).toISOString();
}

export function ArchivePage() {
  const { show } = useToast();
  const [typ, setTyp] = useState<string>("");
  const [version, setVersion] = useState<string>("");
  const [status, setStatus] = useState<string>("");
  const [createdFrom, setCreatedFrom] = useState<string>("");
  const [createdTo, setCreatedTo] = useState<string>("");
  const [sort, setSort] = useState<"created_desc" | "created_asc" | "updated_desc">("created_desc");
  const [filterOpen, setFilterOpen] = useState(false);
  const [exporting, setExporting] = useState(false);

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
    if (createdFrom) p.created_from = localDateStart(createdFrom);
    if (createdTo) p.created_to = localDateEnd(createdTo);
    return p;
  }, [typ, version, status, createdFrom, createdTo, sort]);

  const { data: instances, isLoading } = useQuery({
    queryKey: ["instances", "archive", params],
    queryFn: () => listInstances(params),
  });

  async function onExport() {
    setExporting(true);
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
    } finally {
      setExporting(false);
    }
  }

  const filterPanel = (
    <>
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
            <option value="genehmigt">Genehmigt</option>
            <option value="abgelehnt">Abgelehnt</option>
            <option value="zurueckgewiesen">Zurückgewiesen</option>
          </select>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="label-mono mb-1.5 block">Von</label>
            <input type="date" className="input" value={createdFrom} onChange={(e) => setCreatedFrom(e.target.value)} />
          </div>
          <div>
            <label className="label-mono mb-1.5 block">Bis</label>
            <input type="date" className="input" value={createdTo} onChange={(e) => setCreatedTo(e.target.value)} />
          </div>
        </div>
        <div>
          <label className="label-mono mb-1.5 block">Sortierung</label>
          <select className="input" value={sort} onChange={(e) => setSort(e.target.value as any)}>
            <option value="created_desc">Erstellt (neueste zuerst)</option>
            <option value="created_asc">Erstellt (älteste zuerst)</option>
            <option value="updated_desc">Zuletzt bewegt</option>
          </select>
        </div>
      </div>
      <button onClick={onExport} disabled={exporting} className="btn btn-ghost mt-6 w-full">
        <Download size={14} /> {exporting ? "Exportiere …" : "Als CSV exportieren"}
      </button>
    </>
  );

  return (
    <section>
      <header className="page-header">
        <p className="eyebrow mb-3">Archiv</p>
        <h2 className="page-title">Abgeschlossene Anträge</h2>
        <p className="page-lead">
          Hier finden Sie alle genehmigten, abgelehnten und zurückgewiesenen
          Anträge. Filter nach Typ, Version, Datum oder Status — Export als
          CSV für die Revision.
        </p>
      </header>

      {/* Mobile-Filter-Toggle */}
      <div className="lg:hidden mb-4 flex items-center justify-between gap-3">
        <button
          onClick={() => setFilterOpen((v) => !v)}
          className="btn btn-ghost"
          aria-expanded={filterOpen}
        >
          <SlidersHorizontal size={14} />
          {filterOpen ? "Filter ausblenden" : "Filter anzeigen"}
        </button>
        <span className="text-[12px] text-quiet">
          {isLoading ? "Lade …" : `${instances?.length ?? 0} Einträge`}
        </span>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[280px_1fr] gap-6 lg:gap-8">
        {/* Filter-Sidebar (Desktop) */}
        <aside className="hidden lg:block paper lg:sticky lg:top-32 lg:self-start">
          {filterPanel}
        </aside>
        {/* Filter-Panel (Mobile, ein-/ausklappbar) */}
        {filterOpen && (
          <aside className="lg:hidden paper">
            {filterPanel}
          </aside>
        )}

        {/* Liste */}
        <div>
          <p className="hidden lg:block text-[12px] text-quiet mb-3">
            {isLoading ? "Lade …" : `${instances?.length ?? 0} Einträge`}
          </p>
          {isLoading && (
            <div className="rounded-lg border border-dashed border-rule py-16 sm:py-20 text-center text-muted italic">
              Lade Archiv …
            </div>
          )}
          {instances && instances.length === 0 && (
            <div className="rounded-lg border border-dashed border-rule py-16 sm:py-20 text-center text-muted italic">
              Keine Einträge für diese Filter.
            </div>
          )}
          {instances && instances.length > 0 && (
            <div className="list-card">
              {instances.map((i) => (
                <Link
                  key={i.id}
                  to={`/antraege/${i.id}`}
                  className="grid grid-cols-[1fr_auto] sm:grid-cols-[1fr_auto_auto] items-center gap-x-4 sm:gap-x-6 gap-y-2 px-4 sm:px-6 py-4 sm:py-5 bg-paper hover:bg-bg transition-colors cursor-pointer"
                >
                  <div className="min-w-0">
                    <h4 className="font-display font-semibold text-[15px] sm:text-[16px] tracking-tightish m-0 truncate">
                      {instanceTitle(i)}
                    </h4>
                    <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-0.5 font-mono text-[11px] text-quiet">
                      <span className="text-accent">{i.schema_version}</span>
                      <span>·</span>
                      <span>{i.id.slice(0, 8)}</span>
                      <span>·</span>
                      <span className="truncate max-w-[160px]">von {i.antragsteller}</span>
                      {i.abgeschlossen_am && (
                        <>
                          <span>·</span>
                          <span>abgeschlossen {formatDate(i.abgeschlossen_am)}</span>
                        </>
                      )}
                    </div>
                  </div>
                  <StatusBadge value={i.status} className="sm:hidden justify-self-end" />
                  <div className="hidden sm:block" />
                  <StatusBadge value={i.status} className="hidden sm:inline-flex" />
                </Link>
              ))}
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
