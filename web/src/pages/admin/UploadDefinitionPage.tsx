import { useState, type FormEvent } from "react";
import { useMutation } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";

import { uploadDefinition, uploadDefinitionBpmn } from "@/api/endpoints";
import { useToast } from "@/components/Toaster";

const DEFAULT_GRAPH = JSON.stringify(
  {
    nodes: [
      { id: "start", type: "start" },
      { id: "fb", type: "user_task", label: "Fachbereich", rolle: "Fachbereichsleiter" },
      { id: "vorstand", type: "user_task", label: "Vorstand", rolle: "Vorstand" },
      { id: "end", type: "end" },
    ],
    edges: [
      { from: "start", to: "fb" },
      { from: "fb", to: "vorstand" },
      { from: "vorstand", to: "end" },
    ],
  },
  null,
  2,
);

export function UploadDefinitionPage() {
  const { show } = useToast();
  const navigate = useNavigate();
  const [tab, setTab] = useState<"json" | "bpmn">("json");

  const [typ, setTyp] = useState("");
  const [version, setVersion] = useState("");
  const [titel, setTitel] = useState("");
  const [graphText, setGraphText] = useState(DEFAULT_GRAPH);
  const [jsonSchemaFile, setJsonSchemaFile] = useState<File | null>(null);
  const [uiSchemaFile, setUiSchemaFile] = useState<File | null>(null);
  const [bpmnFile, setBpmnFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);

  const upload = useMutation({
    mutationFn: uploadDefinition,
    onSuccess: (def) => {
      show(`Definition ${def.typ} ${def.version} hochgeladen (Status: ${def.status}).`);
      navigate("/admin/definitionen");
    },
    onError: (e) => setError((e as Error).message),
  });

  const uploadBpmn = useMutation({
    mutationFn: uploadDefinitionBpmn,
    onSuccess: (def) => {
      show(`Definition ${def.typ} ${def.version} aus BPMN importiert (Status: ${def.status}).`);
      navigate("/admin/definitionen");
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
    if (tab === "json") {
      let graph;
      try {
        graph = JSON.parse(graphText);
      } catch {
        setError("Workflow-Graph ist kein gueltiges JSON.");
        return;
      }
      upload.mutate({
        typ, version, titel, workflow_graph: graph,
        json_schema: jsonSchemaFile, ui_schema: uiSchemaFile,
      });
    } else {
      if (!bpmnFile) {
        setError("Bitte eine .bpmn-Datei auswaehlen.");
        return;
      }
      uploadBpmn.mutate({
        typ, version, titel, bpmn_xml: bpmnFile,
        json_schema: jsonSchemaFile, ui_schema: uiSchemaFile,
      });
    }
  }

  const busy = upload.isPending || uploadBpmn.isPending;

  return (
    <section>
      <header className="page-header">
        <p className="eyebrow mb-3">Admin · Upload</p>
        <h2 className="page-title">Neue Maskenversion hochladen</h2>
        <p className="page-lead">
          Hochgeladene Definitionen starten als <em>draft</em>. Erst nach
          Pruefung kannst du sie aktivieren — die jeweils vorhandene aktive
          Version desselben Typs wird bei Aktivierung automatisch retired.
        </p>
        <p className="mt-3 text-[13px] text-muted">
          Tipp: Statt den Workflow-Graph hier von Hand zu schreiben, kannst du den{" "}
          <Link to="/admin/definitionen/designer" className="text-accent underline">grafischen Designer</Link>{" "}
          nutzen oder eine .bpmn-Datei aus Camunda Modeler / demo.bpmn.io importieren.
        </p>
      </header>

      <div className="paper max-w-[820px]">
        <div className="flex gap-2 mb-5 border-b border-rule">
          <button
            type="button"
            onClick={() => setTab("json")}
            className={`px-4 py-2 font-mono text-[12px] uppercase tracking-wider ${
              tab === "json" ? "text-accent border-b-2 border-accent -mb-px" : "text-muted hover:text-ink"
            }`}
          >
            JSON-Graph
          </button>
          <button
            type="button"
            onClick={() => setTab("bpmn")}
            className={`px-4 py-2 font-mono text-[12px] uppercase tracking-wider ${
              tab === "bpmn" ? "text-accent border-b-2 border-accent -mb-px" : "text-muted hover:text-ink"
            }`}
          >
            BPMN-Datei
          </button>
        </div>

        <form onSubmit={onSubmit} className="space-y-6">
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

          {tab === "json" && (
            <div>
              <label className="label-mono mb-1.5 block">Workflow-Graph (JSON)</label>
              <textarea
                className="input font-mono text-xs"
                rows={14}
                value={graphText}
                onChange={(e) => setGraphText(e.target.value)}
              />
              <div className="mt-1 text-[12px] text-quiet">
                Knoten-Typen: <code>start</code>, <code>end</code>, <code>user_task</code>{" "}
                (mit <code>rolle</code>), <code>parallel_split</code>, <code>parallel_join</code>.
                Kanten sind <code>{"{from, to}"}</code>-Paare.
              </div>
            </div>
          )}

          {tab === "bpmn" && (
            <div>
              <label className="label-mono mb-1.5 block">BPMN-2.0-Datei (.bpmn)</label>
              <input
                type="file"
                accept=".bpmn,application/xml,text/xml"
                className="input p-1.5 file:mr-3 file:rounded file:border-0 file:bg-accent-soft file:px-3 file:py-1.5 file:text-accent file:font-medium"
                onChange={(e) => setBpmnFile(e.target.files?.[0] ?? null)}
              />
              <div className="mt-1 text-[12px] text-quiet">
                Akzeptiertes Subset: Start-/End-Event, User-Task (mit{" "}
                <code>camunda:assignee</code> oder{" "}
                <code>{"<documentation>rolle: <Name></documentation>"}</code>),
                Parallel-Gateway, Sequence-Flow.
              </div>
            </div>
          )}

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-5">
            <div>
              <label className="label-mono mb-1.5 block">JSON-Schema-Datei</label>
              <input
                type="file"
                accept="application/json,.json"
                className="input p-1.5 file:mr-3 file:rounded file:border-0 file:bg-accent-soft file:px-3 file:py-1.5 file:text-accent file:font-medium"
                onChange={(e) => setJsonSchemaFile(e.target.files?.[0] ?? null)}
                required
              />
            </div>
            <div>
              <label className="label-mono mb-1.5 block">UI-Schema-Datei</label>
              <input
                type="file"
                accept="application/json,.json"
                className="input p-1.5 file:mr-3 file:rounded file:border-0 file:bg-accent-soft file:px-3 file:py-1.5 file:text-accent file:font-medium"
                onChange={(e) => setUiSchemaFile(e.target.files?.[0] ?? null)}
                required
              />
            </div>
          </div>

          {error && (
            <div className="hint hint-bad">{error}</div>
          )}

          <div className="pt-4 border-t border-rule-soft flex flex-col sm:flex-row gap-3">
            <button
              type="submit"
              className="btn"
              disabled={busy}
            >
              {busy ? "Lade hoch …" : "Als Entwurf hochladen"}
            </button>
            <button type="button" className="btn btn-ghost" onClick={() => navigate("/admin/definitionen")}>
              Abbrechen
            </button>
          </div>
        </form>
      </div>
    </section>
  );
}
