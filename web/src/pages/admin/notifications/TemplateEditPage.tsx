import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";

import { getTemplate, previewTemplate, updateTemplate } from "@/api/admin";
import { QueryError, LoadingCard } from "@/components/QueryStates";
import { useToast } from "@/components/Toaster";

const SAMPLE_CTX: Record<string, Record<string, string>> = {
  stage_review_pending: {
    rolle: "Vorstand", stage: "vorstand", titel: "Beispielantrag",
    schema_version: "AT_8_2_Analyse/2.0.0", antragsteller: "alice",
    erstellt_am: "01.05.2026 09:00", link: "http://localhost:8080/antraege/abc",
  },
  approved: {
    titel: "Beispielantrag", antragsteller: "alice",
    schema_version: "AT_8_2_Analyse/2.0.0",
    abgeschlossen_am: "05.05.2026 14:00", link: "http://localhost:8080/antraege/abc",
  },
  rejected: {
    titel: "Beispielantrag", antragsteller: "alice", rolle: "Compliance",
    schema_version: "AT_8_2_Analyse/2.0.0", kommentar: "Bitte ergänzen.",
    link: "http://localhost:8080/antraege/abc",
  },
  returned: {
    titel: "Beispielantrag", antragsteller: "alice", rolle: "Risikomanagement",
    schema_version: "AT_8_2_Analyse/2.0.0", kommentar: "Risiko-Score fehlt.",
    link: "http://localhost:8080/antraege/abc",
  },
  sla_erinnerung: {
    age_days: "5.0", stage: "vorstand", half_sla: "5", sla: "10",
    titel: "Beispielantrag", antragsteller: "alice",
    link: "http://localhost:8080/antraege/abc",
  },
  sla_eskalation: {
    age_days: "11.0", stage: "vorstand", sla: "10", rolle: "Vorstand",
    titel: "Beispielantrag", antragsteller: "alice",
    link: "http://localhost:8080/antraege/abc",
  },
};

export function TemplateEditPage() {
  const { key = "" } = useParams();
  const qc = useQueryClient();
  const { show } = useToast();
  const { data, isLoading, error } = useQuery({
    queryKey: ["admin", "template", key], queryFn: () => getTemplate(key),
  });
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [previewSubject, setPreviewSubject] = useState("");
  const [previewBody, setPreviewBody] = useState("");

  useEffect(() => {
    if (!data) return;
    setSubject(data.subject);
    setBody(data.body);
  }, [data]);

  const saveMut = useMutation({
    mutationFn: () => updateTemplate(key, { subject, body }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin", "template", key] });
      qc.invalidateQueries({ queryKey: ["admin", "templates"] });
      show("Template gespeichert.");
    },
    onError: (e) => show((e as Error).message, "error"),
  });

  const previewMut = useMutation({
    mutationFn: () => previewTemplate(key, {
      subject, body, context: SAMPLE_CTX[key] ?? {},
    }),
    onSuccess: (r) => { setPreviewSubject(r.subject); setPreviewBody(r.body); },
  });

  if (error) return <QueryError error={error} />;
  if (isLoading || !data) return <LoadingCard label="Lade …" />;

  return (
    <section>
      <header className="page-header">
        <p className="eyebrow mb-3">Admin · Notifications</p>
        <h2 className="page-title">Template: {key}</h2>
        <p className="page-lead">
          Verfügbare Variablen: <code>{Object.keys(SAMPLE_CTX[key] ?? {}).map((k) => "$" + k).join(", ")}</code>
        </p>
      </header>

      <div className="grid gap-6 lg:grid-cols-2">
        <div className="paper flex flex-col gap-3">
          <label className="flex flex-col gap-1">
            <span className="label-mono">Subject</span>
            <input className="input" value={subject} onChange={(e) => setSubject(e.target.value)} />
          </label>
          <label className="flex flex-col gap-1 flex-1">
            <span className="label-mono">Body</span>
            <textarea className="input font-mono text-[12px] flex-1" rows={20}
                      value={body} onChange={(e) => setBody(e.target.value)} />
          </label>
          <div className="flex gap-2">
            <button className="btn btn-primary" onClick={() => saveMut.mutate()}
                    disabled={saveMut.isPending}>Speichern</button>
            <button className="btn btn-ghost" onClick={() => previewMut.mutate()}>Vorschau</button>
          </div>
        </div>
        <div className="paper">
          <p className="label-mono mb-3">Vorschau</p>
          <p className="text-[13px]"><strong>Subject:</strong> {previewSubject || "—"}</p>
          <pre className="font-mono text-[12px] whitespace-pre-wrap mt-3 border-t border-rule pt-3">
            {previewBody || "(Klicke auf „Vorschau\", um die Beispielwerte einzusetzen.)"}
          </pre>
        </div>
      </div>
    </section>
  );
}
