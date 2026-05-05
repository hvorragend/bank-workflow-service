import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Printer } from "lucide-react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { ApiError } from "@/api/client";
import { decideInstance, getInstance, submitInstance } from "@/api/endpoints";
import { useAuth } from "@/auth/AuthContext";
import { AttachmentsSection } from "@/components/AttachmentsSection";
import { DynamicForm } from "@/components/DynamicForm";
import { useToast } from "@/components/Toaster";
import { humanizeBackendError } from "@/lib/schema-rules";
import { cn, formatDate, humanize } from "@/lib/utils";
import type { Approval, Entscheidung, FormInstance } from "@/types/api";

function instanceTitle(i: FormInstance): string {
  return (
    i.daten?.vorhaben?.titel || i.daten?.beschluss?.titel || "(ohne Titel)"
  );
}

function badgeForDecision(d: Entscheidung): string {
  if (d === "approved") return "badge-genehmigt";
  if (d === "rejected") return "badge-abgelehnt";
  return "badge-zurueckgewiesen";
}

interface TimelineStep {
  stage: string;
  rolle: string;
  approval?: Approval;
  cls: "" | "done" | "current" | "rejected";
}

export function InstanceDetailPage() {
  const { id = "" } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { state } = useAuth();
  const { show } = useToast();

  const { data: instance, isLoading } = useQuery({
    queryKey: ["instance", id],
    queryFn: () => getInstance(id),
    enabled: !!id,
  });

  const submitMut = useMutation({
    mutationFn: () => submitInstance(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["instance", id] });
      qc.invalidateQueries({ queryKey: ["instances"] });
      show("Antrag eingereicht.");
    },
    onError: (err) => {
      const detail = err instanceof ApiError ? err.detail : err.message;
      show(humanizeBackendError(detail), "error");
    },
  });

  const [kommentar, setKommentar] = useState("");
  const decideMut = useMutation({
    mutationFn: (entscheidung: Entscheidung) => decideInstance(id, entscheidung, kommentar || undefined),
    onSuccess: (_data, entscheidung) => {
      qc.invalidateQueries({ queryKey: ["instance", id] });
      qc.invalidateQueries({ queryKey: ["instances"] });
      setKommentar("");
      const map: Record<Entscheidung, string> = {
        approved: "Entscheidung: genehmigt.",
        rejected: "Entscheidung: abgelehnt.",
        returned: "Antrag zur Ueberarbeitung zurueckgewiesen.",
      };
      show(map[entscheidung]);
    },
    onError: (err) => {
      const detail = err instanceof ApiError ? err.detail : err.message;
      show(humanizeBackendError(detail), "error");
    },
  });

  if (isLoading) return <div className="text-quiet italic">Lade Antrag …</div>;
  if (!instance) return <div className="text-bad">Antrag nicht gefunden.</div>;

  const stages = instance.workflow_stages;
  const approvals = instance.approvals ?? [];
  const currentStage = instance.aktuelle_stage;
  const currentStageRolle = stages.find((s) => s.name === currentStage)?.rolle ?? "";
  const userRoles = state.status === "authenticated" ? state.user.roles : [];
  const userCanDecide = !!currentStageRolle && userRoles.includes(currentStageRolle);

  const timeline: TimelineStep[] = stages.map((s) => {
    const a = approvals.find((x) => x.stage === s.name);
    let cls: TimelineStep["cls"] = "";
    if (a) cls = a.entscheidung === "rejected" ? "rejected" : "done";
    else if (s.name === currentStage && instance.status === "in_pruefung") cls = "current";
    return { stage: s.name, rolle: s.rolle, approval: a, cls };
  });

  return (
    <section>
      <div className="flex items-center justify-between mb-6 no-print">
        <button
          onClick={() => navigate(-1)}
          className="inline-flex items-center gap-1.5 text-quiet hover:text-accent font-mono text-[11px] uppercase tracking-widest"
        >
          <ArrowLeft size={14} /> Zurueck
        </button>
        <button
          onClick={() => window.print()}
          className="inline-flex items-center gap-1.5 border border-rule px-3 py-1.5 text-xs text-muted hover:bg-ink hover:text-paper hover:border-ink transition"
          title="Als PDF drucken (Browser-Druckdialog)"
        >
          <Printer size={14} /> Drucken / als PDF
        </button>
      </div>

      {/* Print-only Header — wenn man die Seite druckt, soll das Dokument oben Identitaet zeigen */}
      <div className="print-only mb-6">
        <p className="font-mono text-[10px] uppercase tracking-widest text-muted">Bank Workflow Service · Antragsbeleg</p>
        <p className="font-mono text-[10px] text-muted">
          Ausdruck vom {formatDate(new Date().toISOString())}
        </p>
      </div>

      <header className="mb-10 max-w-[720px]">
        <p className="eyebrow mb-3">Antrag · {instance.id.slice(0, 8)}</p>
        <h2 className="font-display font-display font-normal text-[40px] leading-[1.1] tracking-tightish">
          {instanceTitle(instance)}
        </h2>
        <p className="mt-4 text-[15.5px] text-muted">
          Eingereicht von <strong className="text-ink font-medium">{instance.antragsteller}</strong>{" "}
          am {formatDate(instance.erstellt_am)}
        </p>
      </header>

      <div className="grid grid-cols-[auto_1fr_auto] gap-7 items-center border border-rule border-l-2 border-l-accent bg-paper px-8 py-6 mb-10">
        <div>
          <span className="label-mono block mb-1">Schema-Bindung</span>
          <div className="font-mono text-[22px] text-accent tracking-tight">
            {instance.schema_version}
          </div>
        </div>
        <div className="text-[13.5px] text-muted leading-relaxed">
          Diese Ansicht rendert exakt die <strong className="text-ink font-medium">{instance.schema_version}</strong>-
          Felddefinition, die zum Erstellungszeitpunkt gueltig war. Spaetere Versionen sind hier
          ohne Wirkung.
        </div>
        <span className={`badge badge-${instance.status}`}>{instance.status}</span>
      </div>

      <div className="paper">
        <DynamicForm
          jsonSchema={instance.json_schema}
          uiSchema={instance.ui_schema}
          data={instance.daten}
          onChange={() => { /* read-only */ }}
          readOnly
        />
      </div>

      <AttachmentsSection instanceId={instance.id} readOnly={instance.status !== "entwurf"} />

      <div className="paper mt-6">
        <h3 className="font-display font-display font-medium text-2xl tracking-tightish m-0">
          Genehmigungsverlauf
        </h3>
        <p className="text-[13px] text-muted mt-1 mb-4">
          Revisionssichere Historie aller Stage-Entscheidungen.
        </p>
        <div className="pl-2">
          {timeline.map((step, idx) => (
            <div
              key={idx}
              className="grid grid-cols-[32px_1fr] gap-4 py-4 border-b border-rule-soft last:border-b-0"
            >
              <div className="pt-1">
                <div
                  className={cn(
                    "w-3 h-3 rounded-full",
                    step.cls === "" && "bg-rule",
                    step.cls === "done" && "bg-ok",
                    step.cls === "rejected" && "bg-bad",
                    step.cls === "current" && "bg-paper border-2 border-warn w-3.5 h-3.5 -ml-px",
                  )}
                />
              </div>
              <div>
                <div className="font-display font-display font-medium text-base">
                  {humanize(step.stage)}
                </div>
                <div className="label-mono mt-0.5">{step.rolle}</div>
                {step.approval ? (
                  <div className="mt-2 text-[13px] text-muted">
                    <span className={`badge ${badgeForDecision(step.approval.entscheidung)}`}>
                      {step.approval.entscheidung}
                    </span>
                    durch <span className="text-ink">{step.approval.genehmiger}</span>
                    <span className="font-mono text-[11px] text-quiet ml-2">
                      {formatDate(step.approval.zeitstempel)}
                    </span>
                    {step.approval.kommentar && (
                      <div className="mt-1.5 px-3 py-2 bg-bg border-l-2 border-rule text-ink">
                        {step.approval.kommentar}
                      </div>
                    )}
                  </div>
                ) : step.cls === "current" ? (
                  <div className="mt-2 text-[13px]"><em className="text-warn">Wartet auf Entscheidung …</em></div>
                ) : (
                  <div className="mt-2 text-[13px] text-quiet"><em>noch nicht erreicht</em></div>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>

      {instance.status === "in_pruefung" && (
        <ApprovalBox
          stage={currentStage}
          rolle={currentStageRolle}
          userCanDecide={userCanDecide}
          kommentar={kommentar}
          setKommentar={setKommentar}
          onDecide={(e) => decideMut.mutate(e)}
          busy={decideMut.isPending}
        />
      )}

      {instance.status === "entwurf" && (
        <div className="mt-8 border border-rule border-l-2 border-l-neutral bg-[#fdfaf3] px-8 py-7">
          <h3 className="font-display font-display font-medium text-2xl m-0">Entwurf</h3>
          <div className="mt-1 text-[13px] text-muted">
            Dieser Antrag wurde noch nicht eingereicht.
          </div>
          <div className="mt-6 pt-6 border-t border-rule-soft flex gap-3">
            <button className="btn" disabled={submitMut.isPending} onClick={() => submitMut.mutate()}>
              {submitMut.isPending ? "Sende …" : "Jetzt einreichen"}
            </button>
          </div>
        </div>
      )}

      <div className="mt-12 text-center">
        <Link to="/antraege" className="font-mono text-[11px] uppercase tracking-widest text-muted hover:text-accent">
          ← Zur Antrags-Liste
        </Link>
      </div>
    </section>
  );
}

interface ABProps {
  stage: string;
  rolle: string;
  userCanDecide: boolean;
  kommentar: string;
  setKommentar: (v: string) => void;
  onDecide: (e: Entscheidung) => void;
  busy: boolean;
}

function ApprovalBox({ stage, rolle, userCanDecide, kommentar, setKommentar, onDecide, busy }: ABProps) {
  return (
    <div className="mt-8 border border-rule border-l-2 border-l-warn bg-[#fdfaf3] px-8 py-7">
      <h3 className="font-display font-display font-medium text-2xl m-0">Entscheidung treffen</h3>
      <div className="mt-1 text-[13px] text-muted">
        Aktuelle Stage: <strong className="text-ink">{humanize(stage)}</strong>
        ·  erforderliche Rolle: <strong className="text-ink">{rolle}</strong>
      </div>
      {!userCanDecide && (
        <div className="mt-4 border-l-2 border-bad bg-bad-soft px-4 py-3 text-sm text-bad">
          Deine Rollen ({"…"}) berechtigen dich nicht, in dieser Stage zu entscheiden.
          Die Entscheidung muss durch eine Person mit der Rolle „{rolle}" getroffen werden.
        </div>
      )}
      <div className="mt-5 grid grid-cols-1 gap-4">
        <div>
          <label className="label-mono mb-2 block">Kommentar (optional)</label>
          <textarea
            className="input"
            rows={3}
            value={kommentar}
            onChange={(e) => setKommentar(e.target.value)}
            placeholder="Begruendung der Entscheidung — wird revisionssicher protokolliert"
            disabled={!userCanDecide || busy}
          />
        </div>
      </div>
      <div className="mt-6 pt-6 border-t border-rule-soft flex flex-wrap gap-3">
        <button
          className="btn btn-ok"
          disabled={!userCanDecide || busy}
          onClick={() => onDecide("approved")}
        >
          Genehmigen
        </button>
        <button
          className="btn btn-warn"
          disabled={!userCanDecide || busy}
          onClick={() => onDecide("returned")}
        >
          Zur Ueberarbeitung zurueckweisen
        </button>
        <button
          className="btn btn-bad"
          disabled={!userCanDecide || busy}
          onClick={() => onDecide("rejected")}
        >
          Ablehnen
        </button>
      </div>
    </div>
  );
}
