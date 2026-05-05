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
      <header className="mb-10 max-w-[720px]">
        <p className="eyebrow mb-3">Antraege</p>
        <h2 className="font-display font-display font-normal text-[40px] leading-[1.1] tracking-tightish">
          {titel}
        </h2>
        <p className="mt-4 text-[15.5px] text-muted">{beschreibung}</p>
      </header>

      {isLoading && (
        <div className="border border-dashed border-rule py-20 text-center text-muted italic">
          Lade Antraege …
        </div>
      )}
      {error && (
        <div className="border border-bad-soft border-l-2 border-l-bad bg-bad-soft px-5 py-4 text-bad">
          {(error as Error).message}
        </div>
      )}
      {data && data.length === 0 && (
        <div className="border border-dashed border-rule py-20 text-center text-muted italic">
          Keine offenen Antraege.
        </div>
      )}
      {data && data.length > 0 && (
        <div className="flex flex-col">
          {data.map((i) => (
            <Link
              key={i.id}
              to={`/antraege/${i.id}`}
              className="grid grid-cols-[1fr_auto_auto_auto] gap-8 items-center px-6 py-5 border border-rule -mb-px last:mb-0 bg-paper hover:bg-[#fdfaf3] transition cursor-pointer"
            >
              <div>
                <h4 className="font-display font-display font-medium text-[17px] tracking-tightish m-0">
                  {instanceTitle(i)}
                </h4>
                <div className="mt-1 font-mono text-[11px] text-quiet">
                  <span className="text-accent">{i.schema_version}</span>{" "}
                  ·  ID {i.id.slice(0, 8)} ·  von {i.antragsteller} ·  {formatDate(i.erstellt_am)}
                </div>
              </div>
              <div className="font-mono text-[11px] uppercase tracking-wider text-muted">
                {stageLabel(i)}
              </div>
              <span className={`badge badge-${i.status}`}>{i.status}</span>
              <ChevronRight size={16} className="text-quiet" />
            </Link>
          ))}
        </div>
      )}
    </section>
  );
}
