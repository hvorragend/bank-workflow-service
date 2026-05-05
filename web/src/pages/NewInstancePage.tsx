import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

import { ApiError } from "@/api/client";
import { createInstance, listDefinitions, submitInstance } from "@/api/endpoints";
import { DynamicForm, initDynamicData } from "@/components/DynamicForm";
import { useToast } from "@/components/Toaster";
import { humanizeBackendError, pruneEmpty, countFields } from "@/lib/schema-rules";
import type { FormDefinition } from "@/types/api";

function countRequired(schema: any): number {
  if (!schema?.properties) return 0;
  let n = 0;
  for (const [k, v] of Object.entries<any>(schema.properties)) {
    if (v?.type === "object") n += countRequired(v);
    else if ((schema.required || []).includes(k)) n++;
  }
  return n;
}

export function NewInstancePage() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { show } = useToast();
  const { data: defs } = useQuery({
    queryKey: ["definitions", { active: true }],
    queryFn: () => listDefinitions(undefined, true),
  });

  const [defId, setDefId] = useState<string | null>(null);
  const selected: FormDefinition | undefined = useMemo(
    () => defs?.find((d) => d.id === defId),
    [defs, defId],
  );
  const [data, setData] = useState<Record<string, any>>({});

  useEffect(() => {
    if (selected) setData(initDynamicData(selected.json_schema));
  }, [selected]);

  useEffect(() => {
    if (!defId && defs && defs.length > 0) setDefId(defs[0].id);
  }, [defId, defs]);

  const submitMut = useMutation({
    mutationFn: async (opts: { andSubmit: boolean }) => {
      const cleaned = pruneEmpty(data);
      const created = await createInstance({
        form_definition_id: defId!,
        daten: cleaned,
      });
      if (opts.andSubmit) await submitInstance(created.id);
      return created;
    },
    onSuccess: (created, vars) => {
      qc.invalidateQueries({ queryKey: ["instances"] });
      show(vars.andSubmit ? "Antrag erstellt und eingereicht." : "Entwurf gespeichert.");
      navigate(`/antraege/${created.id}`);
    },
    onError: (err) => {
      const detail = err instanceof ApiError ? err.detail : err.message;
      show(humanizeBackendError(detail), "error");
    },
  });

  return (
    <section>
      <header className="page-header">
        <p className="eyebrow mb-3">02 · Neuer Antrag</p>
        <h2 className="page-title">Antrag erstellen</h2>
        <p className="page-lead">
          Waehle eine aktive Maskendefinition. Der Antrag wird beim Speichern
          unveraenderlich an diese Version gebunden — spaetere Versionsaenderungen
          wirken sich nicht auf diesen Antrag aus.
        </p>
      </header>

      <div className="paper">
        <label className="label-mono mb-1.5 block">Maskendefinition</label>
        <select className="input" value={defId ?? ""} onChange={(e) => setDefId(e.target.value)}>
          <option value="" disabled>— bitte waehlen —</option>
          {defs?.map((d) => (
            <option key={d.id} value={d.id}>
              {d.typ} · {d.version} · {d.titel}
            </option>
          ))}
        </select>
      </div>

      {selected && (
        <div className="my-6 sm:my-10 grid grid-cols-1 sm:grid-cols-[auto_1fr_auto] gap-4 sm:gap-7 items-start sm:items-center rounded-lg border border-rule border-l-[3px] border-l-accent bg-paper shadow-card px-5 sm:px-8 py-5 sm:py-6">
          <div>
            <span className="label-mono block mb-1">Schema-Bindung</span>
            <div className="font-display font-semibold text-[18px] sm:text-[22px] text-accent tracking-tight">
              {selected.typ} · {selected.version}
            </div>
          </div>
          <div className="text-[13px] sm:text-[13.5px] text-muted leading-relaxed">
            Dieser Antrag wird hart an{" "}
            <strong className="text-ink font-semibold">
              {selected.typ} v{selected.version}
            </strong>{" "}
            gebunden. Auch wenn morgen eine neue Version aktiv wird, bleibt fuer
            diesen Antrag exakt die hier abgebildete Maske gueltig.
          </div>
          <div className="sm:text-right">
            <span className="label-mono block mb-1">Pflichtfelder</span>
            <div className="font-mono text-sm">{countRequired(selected.json_schema)}</div>
          </div>
        </div>
      )}

      {selected && (
        <div className="paper">
          <DynamicForm
            jsonSchema={selected.json_schema}
            uiSchema={selected.ui_schema}
            data={data}
            onChange={setData}
          />
          <div className="mt-6 sm:mt-8 pt-5 sm:pt-6 border-t border-rule-soft flex flex-col sm:flex-row flex-wrap gap-3">
            <button
              className="btn"
              onClick={() => submitMut.mutate({ andSubmit: true })}
              disabled={submitMut.isPending}
            >
              {submitMut.isPending ? "Speichern …" : "Antrag erstellen & einreichen"}
            </button>
            <button
              className="btn btn-ghost"
              onClick={() => submitMut.mutate({ andSubmit: false })}
              disabled={submitMut.isPending}
            >
              Nur als Entwurf speichern
            </button>
            <div className="sm:ml-auto text-[12px] text-quiet self-center">* Pflichtfeld</div>
          </div>
          <div className="mt-3 text-[12px] text-quiet">
            Schema umfasst {countFields(selected.json_schema)} Felder.
          </div>
        </div>
      )}
    </section>
  );
}
