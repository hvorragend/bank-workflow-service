import { useQuery } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import { Link, useParams } from "react-router-dom";

import { diffDefinitions } from "@/api/endpoints";
import { cn } from "@/lib/utils";

const KIND_LABELS: Record<string, string> = {
  field_added:        "Feld hinzugekommen",
  field_removed:      "Feld entfernt",
  type_changed:       "Typ geändert",
  required_changed:   "Pflicht geändert",
  constraint_changed: "Constraint geändert",
  enum_changed:       "Enum geändert",
};

const KIND_CLASSES: Record<string, string> = {
  field_added:        "border-l-ok",
  field_removed:      "border-l-bad",
  type_changed:       "border-l-warn",
  required_changed:   "border-l-warn",
  constraint_changed: "border-l-neutral",
  enum_changed:       "border-l-neutral",
};

export function DiffPage() {
  const { aId = "", bId = "" } = useParams<{ aId: string; bId: string }>();
  const { data, isLoading, error } = useQuery({
    queryKey: ["diff", aId, bId],
    queryFn: () => diffDefinitions(aId, bId),
    enabled: !!aId && !!bId,
  });

  if (isLoading) return <div className="text-quiet italic">Lade Diff …</div>;
  if (error)     return <div className="text-bad">{(error as Error).message}</div>;
  if (!data)     return null;

  return (
    <section>
      <Link
        to="/admin/definitionen"
        className="inline-flex items-center gap-1.5 text-quiet hover:text-accent font-mono text-[11px] uppercase tracking-widest mb-6"
      >
        <ArrowLeft size={14} /> Zurück zur Maskenverwaltung
      </Link>

      <header className="page-header">
        <p className="eyebrow mb-3">Admin · Diff</p>
        <h2 className="font-display font-semibold text-[24px] sm:text-[28px] lg:text-[36px] leading-[1.1] tracking-tightish">
          {data.from.typ} {data.from.version} → {data.to.version}
        </h2>
        <p className="page-lead">
          Strukturelle Unterschiede zwischen den beiden Schema-Versionen.
          Wichtig für den Audit: bei jeder Änderung muss klar sein, welche
          Anträge auf welcher Maskenversion gestellt wurden — die Versions-
          Garantie schützt Altanträge auch bei diesen Wechseln.
        </p>
      </header>

      {/* Summary */}
      <div className="paper mb-4 sm:mb-6">
        <p className="eyebrow mb-3">Zusammenfassung</p>
        {Object.keys(data.summary).length === 0 ? (
          <div className="text-muted italic">Keine Unterschiede gefunden.</div>
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 sm:gap-4">
            {Object.entries(data.summary).map(([kind, count]) => (
              <div key={kind} className="rounded-md border border-rule px-4 py-3">
                <div className="label-mono">{KIND_LABELS[kind] ?? kind}</div>
                <div className="mt-1 font-mono text-xl sm:text-2xl tracking-tight">{count}</div>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="space-y-2">
        {data.diffs.map((d, idx) => (
          <div
            key={idx}
            className={cn(
              "rounded-lg border border-rule bg-paper shadow-card py-4 px-4 sm:px-6 border-l-[3px]",
              KIND_CLASSES[d.kind] ?? "border-l-neutral",
            )}
          >
            <div className="flex items-baseline gap-3 flex-wrap">
              <span className="badge badge-neutral text-[10px]">{KIND_LABELS[d.kind] ?? d.kind}</span>
              <code className="font-mono text-[12px] sm:text-[13px] text-ink break-all">{d.path}</code>
            </div>
            {(d.before !== null || d.after !== null) && (
              <div className="mt-2 grid grid-cols-1 sm:grid-cols-2 gap-3">
                <DiffSide label="Vorher" value={d.before} />
                <DiffSide label="Nachher" value={d.after} />
              </div>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}

function DiffSide({ label, value }: { label: string; value: any }) {
  return (
    <div>
      <div className="label-mono mb-1">{label}</div>
      {value === null || value === undefined ? (
        <div className="text-quiet italic text-[13px]">— kein Wert —</div>
      ) : typeof value === "object" ? (
        <pre className="font-mono text-[12px] bg-bg border border-rule rounded-md px-3 py-2 overflow-x-auto whitespace-pre-wrap">
          {JSON.stringify(value, null, 2)}
        </pre>
      ) : (
        <div className="font-mono text-[13px] break-all">{String(value)}</div>
      )}
    </div>
  );
}
