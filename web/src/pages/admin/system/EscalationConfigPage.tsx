import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { getEscalation, listRoles, runEscalationNow, setEscalation } from "@/api/admin";
import { useToast } from "@/components/Toaster";

export function EscalationConfigPage() {
  const qc = useQueryClient();
  const { show } = useToast();
  const { data, isLoading } = useQuery({ queryKey: ["admin", "escalation"], queryFn: getEscalation });
  const { data: roles } = useQuery({ queryKey: ["admin", "roles"], queryFn: listRoles });

  const [enabled, setEnabled] = useState(false);
  const [sla, setSla] = useState(14);
  const [interval, setInterval] = useState(60);
  const [bereich, setBereich] = useState<string>("");

  useEffect(() => {
    if (!data) return;
    setEnabled(data.enabled);
    setSla(data.default_sla_days);
    setInterval(data.interval_minutes);
    setBereich(data.bereichsleiter_role_id ?? "");
  }, [data]);

  const saveMut = useMutation({
    mutationFn: () => setEscalation({
      enabled, default_sla_days: sla, interval_minutes: interval,
      bereichsleiter_role_id: bereich || null,
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin", "escalation"] });
      show("Eskalation gespeichert. Scheduler wurde neu konfiguriert.");
    },
    onError: (e) => show((e as Error).message, "error"),
  });

  const runMut = useMutation({
    mutationFn: runEscalationNow,
    onSuccess: (r) => show(`Scan ausgefuehrt: ${JSON.stringify(r.counts)}`),
    onError: (e) => show((e as Error).message, "error"),
  });

  if (isLoading || !data) return <div className="paper py-10 text-center text-quiet">Lade …</div>;

  return (
    <section>
      <header className="page-header">
        <p className="eyebrow mb-3">Admin · System</p>
        <h2 className="page-title">SLA-Eskalation</h2>
        <p className="page-lead">
          Periodischer Scanner. Bei halbem SLA Erinnerung an die Stage-Rolle, bei
          ueberschrittenem SLA Eskalation an die unten ausgewaehlte Rolle.
          Aenderungen an „enabled" oder Intervall greifen sofort — der
          Scheduler wird neu konfiguriert.
        </p>
      </header>

      <form className="paper grid gap-4 md:grid-cols-2 max-w-[700px]"
            onSubmit={(e) => { e.preventDefault(); saveMut.mutate(); }}>
        <label className="inline-flex items-center gap-2 text-[13px] md:col-span-2">
          <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />
          Eskalation aktivieren
        </label>
        <label className="flex flex-col gap-1">
          <span className="label-mono">Default SLA (Tage)</span>
          <input className="input" type="number" min={1} max={3650}
                 value={sla} onChange={(e) => setSla(Number(e.target.value))} />
        </label>
        <label className="flex flex-col gap-1">
          <span className="label-mono">Scan-Intervall (Minuten)</span>
          <input className="input" type="number" min={1} max={1440}
                 value={interval} onChange={(e) => setInterval(Number(e.target.value))} />
        </label>
        <label className="flex flex-col gap-1 md:col-span-2">
          <span className="label-mono">Eskalations-Rolle (an wen wird eskaliert?)</span>
          <select className="input" value={bereich} onChange={(e) => setBereich(e.target.value)}>
            <option value="">— keine —</option>
            {roles?.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
          </select>
        </label>
        <button type="submit" className="btn btn-primary self-start md:col-span-2" disabled={saveMut.isPending}>
          Speichern
        </button>
      </form>

      <div className="paper mt-6 max-w-[700px]">
        <p className="label-mono mb-2">Status</p>
        <p className="text-[13px]">
          Scheduler {data.scheduler_running ? "laeuft" : "ist aus"}
          {data.scheduler_interval_minutes && ` (Intervall ${data.scheduler_interval_minutes} min)`}.
          Aktuelle Eskalations-Rolle: <strong>{data.bereichsleiter_role_name || "—"}</strong>.
        </p>
        <button className="btn mt-3" onClick={() => runMut.mutate()} disabled={runMut.isPending}>
          Scan jetzt ausfuehren
        </button>
      </div>
    </section>
  );
}
