import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ChevronRight, Search } from "lucide-react";
import { Link, useSearchParams } from "react-router-dom";

import { listInstances, type ListInstancesParams } from "@/api/endpoints";
import { StatusBadge } from "@/components/StatusBadge";
import { formatDate, humanize, instanceTitle } from "@/lib/utils";
import type { FormInstance } from "@/types/api";

const OFFENE_STATUS = ["entwurf", "in_pruefung"];

function stageLabel(i: FormInstance): string {
  if (i.status === "entwurf") return "Entwurf";
  if (!i.active_stages || i.active_stages.length === 0) return humanize(i.status);
  if (i.active_stages.length === 1) {
    const a = i.active_stages[0];
    const node = i.workflow_graph?.nodes.find((n) => n.id === a.node_id);
    return humanize(node?.label || a.node_id);
  }
  return `${i.active_stages.length} Tasks parallel`;
}

export function InstancesPage() {
  const [params] = useSearchParams();
  const mein = params.get("mein") === "true";
  const wartet = params.get("wartet_auf_mich") === "true";

  const queryParams: ListInstancesParams = {
    status: OFFENE_STATUS,
    mein: mein || undefined,
    wartet_auf_mich: wartet || undefined,
    sort: "updated_desc",
    limit: 200,
  };

  const { data, isLoading, error } = useQuery({
    queryKey: ["instances", "open", queryParams],
    queryFn: () => listInstances(queryParams),
  });

  // U-005: client-seitige Such-/Statusfilter auf der geladenen Liste.
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<"" | "entwurf" | "in_pruefung">("");

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return (data ?? []).filter((i) => {
      if (statusFilter && i.status !== statusFilter) return false;
      if (!q) return true;
      return (
        instanceTitle(i).toLowerCase().includes(q) ||
        i.antragsteller.toLowerCase().includes(q) ||
        i.id.toLowerCase().includes(q)
      );
    });
  }, [data, search, statusFilter]);

  let titel = "Offene Anträge";
  let beschreibung =
    "Alle laufenden Anträge — Entwürfe und in Prüfung befindliche. Abgeschlossene Anträge finden Sie im Archiv.";
  if (mein) {
    titel = "Eigene offene Anträge";
    beschreibung = "Anträge, die Sie selbst angelegt haben und die noch offen sind.";
  } else if (wartet) {
    titel = "Wartet auf Ihre Entscheidung";
    beschreibung = "Anträge, deren aktuelle Stage zu einer Ihrer Rollen passt.";
  }

  return (
    <section>
      <header className="page-header">
        <p className="eyebrow mb-3">Anträge</p>
        <h2 className="page-title">{titel}</h2>
        <p className="page-lead">{beschreibung}</p>
      </header>

      {/* Filter/Suche */}
      <div className="mb-5 sm:mb-6 flex flex-col sm:flex-row gap-3">
        <div className="relative flex-1">
          <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-quiet" aria-hidden />
          <label htmlFor="instance-search" className="sr-only">Anträge durchsuchen</label>
          <input
            id="instance-search"
            className="input pl-9"
            placeholder="Suche nach Titel, Antragsteller oder ID …"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <div className="sm:w-56">
          <label htmlFor="instance-status" className="sr-only">Status filtern</label>
          <select
            id="instance-status"
            className="input"
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value as typeof statusFilter)}
          >
            <option value="">Alle offenen</option>
            <option value="entwurf">Entwurf</option>
            <option value="in_pruefung">In Prüfung</option>
          </select>
        </div>
      </div>

      {isLoading && (
        <div className="rounded-lg border border-dashed border-rule py-16 sm:py-20 text-center text-muted italic">
          Lade Anträge …
        </div>
      )}
      {error && (
        <div className="hint hint-bad">{(error as Error).message}</div>
      )}
      {data && filtered.length === 0 && (
        <div className="rounded-lg border border-dashed border-rule py-16 sm:py-20 text-center text-muted italic">
          {data.length === 0 ? "Keine offenen Anträge." : "Keine Treffer für diese Filter."}
        </div>
      )}
      {filtered.length > 0 && (
        <div className="list-card">
          {filtered.map((i) => (
            <Link
              key={i.id}
              to={`/antraege/${i.id}`}
              className="grid grid-cols-[1fr_auto] sm:grid-cols-[1fr_auto_auto_auto] items-center gap-x-4 sm:gap-x-6 gap-y-2 px-4 sm:px-6 py-4 sm:py-5 bg-paper hover:bg-bg transition-colors cursor-pointer"
            >
              <div className="min-w-0">
                <h4 className="font-display font-semibold text-[15px] sm:text-[17px] tracking-tightish m-0 truncate">
                  {instanceTitle(i)}
                </h4>
                <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-0.5 font-mono text-[11px] text-quiet">
                  <span className="text-accent">{i.schema_version}</span>
                  <span>·</span>
                  <span>{i.id.slice(0, 8)}</span>
                  <span>·</span>
                  <span className="truncate max-w-[160px]">von {i.antragsteller}</span>
                  <span>·</span>
                  <span>{formatDate(i.erstellt_am)}</span>
                </div>
              </div>
              <ChevronRight size={16} className="text-quiet sm:hidden justify-self-end" />
              <div className="hidden sm:block font-mono text-[11px] uppercase tracking-wider text-muted whitespace-nowrap">
                {stageLabel(i)}
              </div>
              <StatusBadge value={i.status} className="col-start-1 sm:col-auto justify-self-start sm:justify-self-auto" />
              <ChevronRight size={16} className="text-quiet hidden sm:block" />
            </Link>
          ))}
        </div>
      )}
    </section>
  );
}
