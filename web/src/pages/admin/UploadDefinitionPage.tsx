import { useState, type FormEvent } from "react";
import { useMutation } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

import { uploadDefinition } from "@/api/endpoints";
import { useToast } from "@/components/Toaster";

export function UploadDefinitionPage() {
  const { show } = useToast();
  const navigate = useNavigate();

  const [typ, setTyp] = useState("");
  const [version, setVersion] = useState("");
  const [titel, setTitel] = useState("");
  const [stagesText, setStagesText] = useState(
    JSON.stringify([
      { name: "fachbereich", rolle: "Fachbereichsleiter" },
      { name: "vorstand",    rolle: "Vorstand" },
    ], null, 2),
  );
  const [jsonSchemaFile, setJsonSchemaFile] = useState<File | null>(null);
  const [uiSchemaFile, setUiSchemaFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);

  const upload = useMutation({
    mutationFn: uploadDefinition,
    onSuccess: (def) => {
      show(`Definition ${def.typ} ${def.version} hochgeladen (Status: ${def.status}).`);
      navigate("/admin");
    },
    onError: (e) => setError((e as Error).message),
  });

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (!jsonSchemaFile || !uiSchemaFile) {
      setError("Bitte beide Schema-Dateien auswaehlen.");
      return;
    }
    let stages;
    try {
      stages = JSON.parse(stagesText);
    } catch {
      setError("Workflow-Stages sind kein gueltiges JSON.");
      return;
    }
    upload.mutate({ typ, version, titel, workflow_stages: stages,
                    json_schema: jsonSchemaFile, ui_schema: uiSchemaFile });
  }

  return (
    <section>
      <header className="mb-10 max-w-[720px]">
        <p className="eyebrow mb-3">Admin · Upload</p>
        <h2 className="font-display font-display font-normal text-[40px] leading-[1.1] tracking-tightish">
          Neue Maskenversion hochladen
        </h2>
        <p className="mt-4 text-[15.5px] text-muted">
          Hochgeladene Definitionen starten als <em>draft</em>. Erst nach
          Pruefung kannst du sie aktivieren — die jeweils vorhandene aktive
          Version desselben Typs wird bei Aktivierung automatisch retired.
        </p>
      </header>

      <form onSubmit={onSubmit} className="paper space-y-6 max-w-[820px]">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-5">
          <div>
            <label className="label-mono mb-1.5 block">Typ</label>
            <input
              className="input"
              placeholder="z. B. AT_8_2_Analyse"
              value={typ}
              onChange={(e) => setTyp(e.target.value)}
              required
            />
          </div>
          <div>
            <label className="label-mono mb-1.5 block">Version (SemVer)</label>
            <input
              className="input"
              placeholder="z. B. 3.0.0"
              value={version}
              onChange={(e) => setVersion(e.target.value)}
              required
            />
          </div>
          <div className="sm:col-span-2">
            <label className="label-mono mb-1.5 block">Titel</label>
            <input
              className="input"
              placeholder="z. B. AT 8.2 Wesentlichkeitsanalyse v3.0.0"
              value={titel}
              onChange={(e) => setTitel(e.target.value)}
              required
            />
          </div>
        </div>

        <div>
          <label className="label-mono mb-1.5 block">Workflow-Stages (JSON-Array)</label>
          <textarea
            className="input font-mono text-xs"
            rows={6}
            value={stagesText}
            onChange={(e) => setStagesText(e.target.value)}
          />
          <div className="mt-1 text-[12px] text-quiet">
            Jede Stage benoetigt die Felder <code className="font-mono">name</code> und{" "}
            <code className="font-mono">rolle</code>. Die Reihenfolge bestimmt den Genehmigungsweg.
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-5">
          <div>
            <label className="label-mono mb-1.5 block">JSON-Schema-Datei</label>
            <input
              type="file"
              accept="application/json,.json"
              className="input p-1.5"
              onChange={(e) => setJsonSchemaFile(e.target.files?.[0] ?? null)}
              required
            />
          </div>
          <div>
            <label className="label-mono mb-1.5 block">UI-Schema-Datei</label>
            <input
              type="file"
              accept="application/json,.json"
              className="input p-1.5"
              onChange={(e) => setUiSchemaFile(e.target.files?.[0] ?? null)}
              required
            />
          </div>
        </div>

        {error && (
          <div className="border-l-2 border-bad bg-bad-soft px-4 py-3 text-sm text-bad">
            {error}
          </div>
        )}

        <div className="pt-4 border-t border-rule-soft flex gap-3">
          <button
            type="submit"
            className="btn"
            disabled={upload.isPending}
          >
            {upload.isPending ? "Lade hoch …" : "Als Entwurf hochladen"}
          </button>
          <button type="button" className="btn btn-ghost" onClick={() => navigate("/admin")}>
            Abbrechen
          </button>
        </div>
      </form>
    </section>
  );
}
