import { useQuery } from "@tanstack/react-query";
import { ChevronRight } from "lucide-react";
import { Link, useSearchParams } from "react-router-dom";

import { listInstances, type ListInstancesParams } from "@/api/endpoints";
import { formatDate, humanize } from "@/lib/utils";
import type { FormInstance } from "@/types/api";

const OFFENE_STATUS = ["entwurf", "in_pruefung"];

function instanceTitle(i: FormInstance): string {
  return i.daten?.vorhaben?.titel || i.daten?.beschluss?.titel || "(ohne Titel)";
}

function stageLabel(i: FormInstance): string {
  if (i.status === "entwurf") return "Entwurf";
  return humanize(i.aktuelle_stage);
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

  let titel = "Offene Antraege";
  let beschreibung =
    "Alle laufenden Antraege — Entwuerfe und in Pruefung befindliche. Abgeschlossene Antraege findest du im Archiv.";
  if (mein) {
    titel = "Eigene offene Antraege";
    beschreibung = "Antraege, die du selbst angelegt hast und die noch offen sind.";
  } else if (wartet) {
    titel = "Wartet auf deine Entscheidung";
    beschreibung = "Antraege, deren aktuelle Stage zu einer deiner Rollen passt.";
  }

  return (
    <section>
      <header className="page-header">
        <p className="eyebrow mb-3">Antraege</p>
        <h2 className="page-title">{titel}</h2>
        <p className="page-lead">{beschreibung}</p>
      </header>

      {isLoading && (
        <div className="rounded-lg border border-dashed border-rule py-16 sm:py-20 text-center text-muted italic">
          Lade Antraege …
        </div>
      )}
      {error && (
        <div className="hint hint-bad">{(error as Error).message}</div>
      )}
      {data && data.length === 0 && (
        <div className="rounded-lg border border-dashed border-rule py-16 sm:py-20 text-center text-muted italic">
          Keine offenen Antraege.
        </div>
      )}
      {data && data.length > 0 && (
        <div className="list-card">
          {data.map((i) => (
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
              <span className={`badge badge-${i.status} col-start-1 sm:col-auto justify-self-start sm:justify-self-auto`}>
                {i.status}
              </span>
              <ChevronRight size={16} className="text-quiet hidden sm:block" />
            </Link>
          ))}
        </div>
      )}
    </section>
  );
}
