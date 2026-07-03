import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Printer } from "lucide-react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { ApiError } from "@/api/client";
import { decideInstance, getInstance, patchInstance, submitInstance } from "@/api/endpoints";
import { useAuth } from "@/auth/AuthContext";
import { AttachmentsSection } from "@/components/AttachmentsSection";
import { DynamicForm } from "@/components/DynamicForm";
import { QueryError } from "@/components/QueryStates";
import { StatusBadge } from "@/components/StatusBadge";
import { useToast } from "@/components/Toaster";
import { findMissingRequired, humanizeBackendError, pruneEmpty } from "@/lib/schema-rules";
import { cn, formatDate, humanize, instanceTitle } from "@/lib/utils";
import type { ActiveStage, Approval, Entscheidung, GraphNode } from "@/types/api";

interface TimelineStep {
  node: GraphNode;
  approval?: Approval;
  active?: ActiveStage;
  cls: "" | "done" | "current" | "rejected";
}

export function InstanceDetailPage() {
  const { id = "" } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { state } = useAuth();
  const { show } = useToast();

  const { data: instance, isLoading, error } = useQuery({
    queryKey: ["instance", id],
    queryFn: () => getInstance(id),
    enabled: !!id,
    retry: false,
  });

  const submitMut = useMutation({
    mutationFn: () => submitInstance(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["instance", id] });
      qc.invalidateQueries({ queryKey: ["instances"] });
      qc.invalidateQueries({ queryKey: ["stats"] });
      show("Antrag eingereicht.");
    },
    onError: (err) => {
      const detail = err instanceof ApiError ? err.detail : err.message;
      show(humanizeBackendError(detail), "error");
    },
  });

  const [kommentar, setKommentar] = useState("");
  const [selectedNodeId, setSelectedNodeId] = useState<string>("");
  const decideMut = useMutation({
    mutationFn: ({ nodeId, entscheidung }: { nodeId: string; entscheidung: Entscheidung }) =>
      decideInstance(id, nodeId, entscheidung, kommentar || undefined),
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: ["instance", id] });
      qc.invalidateQueries({ queryKey: ["instances"] });
      qc.invalidateQueries({ queryKey: ["stats"] });
      setKommentar("");
      // F-032: Auswahl zuruecksetzen, sonst bleibt bei parallelen Stages ein
      // bereits entschiedener Task selektiert (Dead-End).
      setSelectedNodeId("");
      const map: Record<Entscheidung, string> = {
        approved: "Entscheidung: genehmigt.",
        rejected: "Entscheidung: abgelehnt.",
        returned: "Antrag zur Überarbeitung zurückgewiesen.",
      };
      show(map[vars.entscheidung]);
    },
    onError: (err) => {
      const detail = err instanceof ApiError ? err.detail : err.message;
      show(humanizeBackendError(detail), "error");
    },
  });

  // U-002: Entwurf bearbeiten (nur Antragsteller; Backend erzwingt zusaetzlich).
  const [editing, setEditing] = useState(false);
  const [editData, setEditData] = useState<Record<string, any>>({});
  const [invalidScopes, setInvalidScopes] = useState<Set<string>>(new Set());
  const patchMut = useMutation({
    mutationFn: (daten: Record<string, any>) => patchInstance(id, daten),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["instance", id] });
      setEditing(false);
      show("Antragsdaten gespeichert.");
    },
    onError: (err) => {
      const detail = err instanceof ApiError ? err.detail : err.message;
      show(humanizeBackendError(detail), "error");
    },
  });

  function goBack() {
    // U-012: sauberer Fallback, falls es keine History gibt (Direktaufruf).
    if (window.history.length > 1) navigate(-1);
    else navigate("/antraege");
  }

  if (isLoading) return <div className="text-quiet italic">Lade Antrag …</div>;
  if (error) {
    // F-033: 404 sauber vom generischen Ladefehler trennen.
    if (error instanceof ApiError && error.status === 404) {
      return <div className="text-bad">Antrag nicht gefunden.</div>;
    }
    return <QueryError error={error} />;
  }
  if (!instance) return <div className="text-bad">Antrag nicht gefunden.</div>;

  const taskNodes = instance.workflow_graph.nodes.filter((n) => n.type === "user_task");
  const approvals = instance.approvals ?? [];
  const activeStages = instance.active_stages ?? [];
  const userRoles = state.status === "authenticated" ? state.user.roles : [];
  const currentUsername = state.status === "authenticated" ? state.user.username : null;
  const isOwner = currentUsername === instance.antragsteller;
  const canEditDraft = instance.status === "entwurf" && isOwner;

  function startEditing() {
    setEditData(structuredClone(instance!.daten ?? {}));
    setInvalidScopes(new Set());
    setEditing(true);
  }
  function saveEdit() {
    const missing = findMissingRequired(instance!.ui_schema, instance!.json_schema, editData);
    if (missing.length > 0) {
      setInvalidScopes(new Set(missing));
      show(`Bitte ${missing.length} Pflichtfeld${missing.length > 1 ? "er" : ""} ausfüllen.`, "error");
      return;
    }
    patchMut.mutate(pruneEmpty(editData));
  }

  const timeline: TimelineStep[] = taskNodes.map((node) => {
    // Eine Approval-Row pro Knoten; bei Zyklen unmoeglich (Validator), also reicht "first match".
    const approval = approvals.find((a) => a.stage === node.id);
    const active = activeStages.find((a) => a.node_id === node.id);
    let cls: TimelineStep["cls"] = "";
    if (approval) cls = approval.entscheidung === "rejected" ? "rejected" : "done";
    else if (active) cls = "current";
    return { node, approval, active, cls };
  });

  // Default-Selection: erster aktiver Task in einer Rolle des Users — sonst der erste aktive ueberhaupt.
  const userActiveStages = activeStages.filter((a) => userRoles.includes(a.rolle));
  const effectiveSelected =
    selectedNodeId
      ? activeStages.find((a) => a.node_id === selectedNodeId) ?? null
      : userActiveStages[0] ?? activeStages[0] ?? null;

  let waitingDays: number | null = null;
  let slaState: "ok" | "near" | "breached" | null = null;
  if (effectiveSelected) {
    const node = taskNodes.find((n) => n.id === effectiveSelected.node_id);
    const slaDays = node?.sla_days ?? 14;
    waitingDays = (Date.now() - new Date(effectiveSelected.eingetreten_am).getTime()) / 86_400_000;
    if (waitingDays >= slaDays) slaState = "breached";
    else if (waitingDays >= slaDays / 2) slaState = "near";
    else slaState = "ok";
  }

  return (
    <section>
      <div className="flex items-center justify-between mb-6 no-print">
        <button
          onClick={goBack}
          className="inline-flex items-center gap-1.5 text-quiet hover:text-accent font-mono text-[11px] uppercase tracking-widest"
        >
          <ArrowLeft size={14} /> Zurück
        </button>
        <button
          onClick={() => window.print()}
          className="inline-flex items-center gap-1.5 rounded-md border border-rule px-3 py-1.5 text-xs text-muted hover:bg-accent hover:text-paper hover:border-accent transition-colors"
          title="Als PDF drucken (Browser-Druckdialog)"
        >
          <Printer size={14} /> <span className="hidden sm:inline">Drucken / als PDF</span>
        </button>
      </div>

      <div className="print-only mb-6">
        <p className="font-mono text-[10px] uppercase tracking-widest text-muted">Bank Workflow Service · Antragsbeleg</p>
        <p className="font-mono text-[10px] text-muted">
          Ausdruck vom {formatDate(new Date().toISOString())}
        </p>
      </div>

      <header className="page-header">
        <p className="eyebrow mb-3">Antrag · {instance.id.slice(0, 8)}</p>
        <h2 className="page-title">{instanceTitle(instance)}</h2>
        <p className="page-lead">
          Eingereicht von <strong className="text-ink font-semibold">{instance.antragsteller}</strong>{" "}
          am {formatDate(instance.erstellt_am)}
        </p>
      </header>

      <div className="grid grid-cols-1 sm:grid-cols-[auto_1fr_auto] gap-4 sm:gap-7 items-start sm:items-center rounded-lg border border-rule border-l-[3px] border-l-accent bg-paper shadow-card px-5 sm:px-8 py-5 sm:py-6 mb-6 sm:mb-10">
        <div>
          <span className="label-mono block mb-1">Schema-Bindung</span>
          <div className="font-display font-semibold text-[18px] sm:text-[22px] text-accent tracking-tight">
            {instance.schema_version}
          </div>
        </div>
        <div className="text-[13px] sm:text-[13.5px] text-muted leading-relaxed">
          Diese Ansicht rendert exakt die <strong className="text-ink font-semibold">{instance.schema_version}</strong>-
          Felddefinition, die zum Erstellungszeitpunkt gültig war. Spätere Versionen sind hier
          ohne Wirkung.
        </div>
        <StatusBadge value={instance.status} className="self-start sm:self-center" />
      </div>

      <div className="paper">
        {canEditDraft && (
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3 no-print">
            <p className="text-[13px] text-muted m-0">
              {editing
                ? "Bearbeitungsmodus — Änderungen an den Antragsdaten."
                : "Dieser Entwurf kann noch bearbeitet werden."}
            </p>
            {editing ? (
              <div className="flex gap-2">
                <button className="btn" disabled={patchMut.isPending} onClick={saveEdit}>
                  {patchMut.isPending ? "Speichern …" : "Speichern"}
                </button>
                <button
                  className="btn btn-ghost"
                  disabled={patchMut.isPending}
                  onClick={() => { setEditing(false); setInvalidScopes(new Set()); }}
                >
                  Abbrechen
                </button>
              </div>
            ) : (
              <button className="btn btn-ghost" onClick={startEditing}>Bearbeiten</button>
            )}
          </div>
        )}
        <DynamicForm
          jsonSchema={instance.json_schema}
          uiSchema={instance.ui_schema}
          data={editing ? editData : instance.daten}
          onChange={editing ? setEditData : () => { /* read-only */ }}
          readOnly={!editing}
          invalidScopes={editing ? invalidScopes : undefined}
        />
      </div>

      <AttachmentsSection instanceId={instance.id} readOnly={instance.status !== "entwurf"} />

      <div className="paper mt-4 sm:mt-6">
        <h3 className="font-display font-semibold text-xl sm:text-2xl tracking-tightish m-0">
          Genehmigungsverlauf
        </h3>
        <p className="text-[13px] text-muted mt-1 mb-4">
          Revisionssichere Historie aller Stage-Entscheidungen. Bei parallelen Branches
          sind mehrere Tasks gleichzeitig &bdquo;Wartet&ldquo;.
        </p>
        <div className="pl-1 sm:pl-2">
          {timeline.map((step, idx) => (
            <div
              key={idx}
              className="grid grid-cols-[24px_1fr] sm:grid-cols-[32px_1fr] gap-3 sm:gap-4 py-4 border-b border-rule-soft last:border-b-0"
            >
              <div className="pt-1.5">
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
              <div className="min-w-0">
                <div className="font-display font-semibold text-base">
                  {humanize(step.node.label || step.node.id)}
                </div>
                <div className="label-mono mt-0.5">{step.node.rolle}</div>
                {step.approval ? (
                  <div className="mt-2 text-[13px] text-muted">
                    <div className="flex flex-wrap items-center gap-2">
                      <StatusBadge value={step.approval.entscheidung} />
                      <span>durch <span className="text-ink font-medium">{step.approval.genehmiger}</span></span>
                      <span className="font-mono text-[11px] text-quiet">
                        {formatDate(step.approval.zeitstempel)}
                      </span>
                    </div>
                    {step.approval.kommentar && (
                      <div className="mt-2 px-3 py-2 bg-bg border-l-2 border-rule rounded-r-md text-ink">
                        {step.approval.kommentar}
                      </div>
                    )}
                  </div>
                ) : step.cls === "current" ? (
                  <div className="mt-2 text-[13px]">
                    <em className="text-warn font-medium">Wartet auf Entscheidung …</em>
                  </div>
                ) : (
                  <div className="mt-2 text-[13px] text-quiet"><em>noch nicht erreicht</em></div>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>

      {instance.status === "in_pruefung" && activeStages.length > 0 && (
        <ApprovalBox
          activeStages={activeStages}
          taskNodes={taskNodes}
          approvals={approvals}
          instanceLauf={instance.lauf}
          userRoles={userRoles}
          selectedNodeId={effectiveSelected?.node_id ?? ""}
          setSelectedNodeId={setSelectedNodeId}
          waitingDays={waitingDays}
          slaState={slaState}
          kommentar={kommentar}
          setKommentar={setKommentar}
          onDecide={(entscheidung) => {
            const target = effectiveSelected?.node_id;
            if (!target) return;
            // N-004: Ablehnung/Zurueckweisung erfordern eine Begruendung — hier
            // clientseitig pruefen, damit der Nutzer sofort Feedback bekommt
            // (statt erst einen 422 vom Backend).
            if ((entscheidung === "rejected" || entscheidung === "returned") && !kommentar.trim()) {
              show("Bitte eine Begründung im Kommentarfeld angeben.", "error");
              return;
            }
            // U-003: finale Entscheidungen (genehmigen/ablehnen) rueckfragen.
            if (entscheidung === "approved" && !confirm("Antrag endgültig genehmigen?")) return;
            if (entscheidung === "rejected" && !confirm("Antrag endgültig ablehnen?")) return;
            decideMut.mutate({ nodeId: target, entscheidung });
          }}
          busy={decideMut.isPending}
        />
      )}

      {instance.status === "entwurf" && (
        <div className="mt-6 sm:mt-8 rounded-lg border border-rule border-l-[3px] border-l-neutral bg-paper shadow-card px-5 sm:px-8 py-5 sm:py-7">
          <h3 className="font-display font-semibold text-xl sm:text-2xl m-0">Entwurf</h3>
          <div className="mt-1 text-[13px] text-muted">
            Dieser Antrag wurde noch nicht eingereicht.
          </div>
          <div className="mt-5 pt-5 border-t border-rule-soft flex gap-3">
            <button className="btn" disabled={submitMut.isPending} onClick={() => submitMut.mutate()}>
              {submitMut.isPending ? "Sende …" : "Jetzt einreichen"}
            </button>
          </div>
        </div>
      )}

      <div className="mt-10 sm:mt-12 text-center">
        <Link to="/antraege" className="font-mono text-[11px] uppercase tracking-widest text-muted hover:text-accent">
          ← Zur Antrags-Liste
        </Link>
      </div>
    </section>
  );
}

interface ABProps {
  activeStages: ActiveStage[];
  taskNodes: GraphNode[];
  approvals: Approval[];
  instanceLauf: number | undefined;
  userRoles: string[];
  selectedNodeId: string;
  setSelectedNodeId: (v: string) => void;
  waitingDays: number | null;
  slaState: "ok" | "near" | "breached" | null;
  kommentar: string;
  setKommentar: (v: string) => void;
  onDecide: (e: Entscheidung) => void;
  busy: boolean;
}

function ApprovalBox({
  activeStages, taskNodes, approvals, instanceLauf, userRoles,
  selectedNodeId, setSelectedNodeId,
  waitingDays, slaState,
  kommentar, setKommentar, onDecide, busy,
}: ABProps) {
  const selected = activeStages.find((a) => a.node_id === selectedNodeId);
  const node = taskNodes.find((n) => n.id === selected?.node_id);
  const userCanDecide = !!selected && userRoles.includes(selected.rolle);
  const slaDays = node?.sla_days ?? 14;

  // N-007: Vier-Augen-Prinzip. Erforderliche Genehmigungen vs. bereits
  // erteilte (distinkte Genehmiger im aktuellen Durchlauf der Instanz).
  const minApprovals = node?.min_approvals ?? 1;
  const approvedCount =
    selected && minApprovals > 1
      ? new Set(
          approvals
            .filter(
              (a) =>
                a.stage === selected.node_id &&
                a.entscheidung === "approved" &&
                a.lauf === instanceLauf,
            )
            .map((a) => a.genehmiger),
        ).size
      : 0;

  return (
    <div className="mt-6 sm:mt-8 rounded-lg border border-rule border-l-[3px] border-l-warn bg-paper shadow-card px-5 sm:px-8 py-5 sm:py-7">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h3 className="font-display font-semibold text-xl sm:text-2xl m-0">Entscheidung treffen</h3>
        {selected && minApprovals > 1 && (
          <span
            className={cn(
              "badge",
              approvedCount >= minApprovals ? "badge-genehmigt" : "badge-neutral",
            )}
            title="Vier-Augen-Prinzip: erforderliche Genehmigungen"
          >
            4-Augen: {approvedCount} von {minApprovals} Genehmigungen
          </span>
        )}
      </div>

      {activeStages.length > 1 && (
        <div className="mt-3">
          <label className="label-mono mb-2 block">Aktiven Task wählen ({activeStages.length} parallel)</label>
          <select
            className="input"
            value={selectedNodeId}
            onChange={(e) => setSelectedNodeId(e.target.value)}
            disabled={busy}
          >
            {activeStages.map((a) => {
              const n = taskNodes.find((tn) => tn.id === a.node_id);
              return (
                <option key={a.node_id} value={a.node_id}>
                  {humanize(n?.label || a.node_id)} · Rolle {a.rolle}
                </option>
              );
            })}
          </select>
        </div>
      )}

      {selected && node && (
        <div className="mt-3 text-[13px] text-muted">
          Aktive Stage: <strong className="text-ink">{humanize(node.label || node.id)}</strong>
          {" · "}erforderliche Rolle: <strong className="text-ink">{selected.rolle}</strong>
          {waitingDays !== null && (
            <span
              className={cn(
                "ml-3 font-mono text-[11px] uppercase tracking-wider",
                slaState === "ok" && "text-quiet",
                slaState === "near" && "text-warn",
                slaState === "breached" && "text-bad",
              )}
            >
              · seit {waitingDays.toFixed(1)} Tagen · SLA {slaDays} Tage
              {slaState === "near" && " · Erinnerung fällig"}
              {slaState === "breached" && " · SLA überschritten"}
            </span>
          )}
        </div>
      )}

      {selected && !userCanDecide && (
        <div className="mt-4 hint hint-bad">
          Ihre Rollen ({userRoles.join(", ") || "keine"}) berechtigen Sie nicht, in dieser Stage
          zu entscheiden. Die Entscheidung muss durch eine Person mit der Rolle
          „{selected.rolle}" getroffen werden.
        </div>
      )}
      <div className="mt-5 grid grid-cols-1 gap-4">
        <div>
          <label className="label-mono mb-2 block">
            Kommentar <span className="text-quiet">(Pflicht bei Ablehnen/Zurückweisen)</span>
          </label>
          <textarea
            className="input"
            rows={3}
            value={kommentar}
            onChange={(e) => setKommentar(e.target.value)}
            placeholder="Begründung der Entscheidung — wird revisionssicher protokolliert"
            disabled={!userCanDecide || busy}
          />
        </div>
      </div>
      <div className="mt-5 sm:mt-6 pt-5 sm:pt-6 border-t border-rule-soft flex flex-col sm:flex-row flex-wrap gap-3">
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
          Zur Überarbeitung zurückweisen
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
