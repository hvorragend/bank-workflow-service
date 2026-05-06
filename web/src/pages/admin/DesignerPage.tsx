/**
 * Workflow-Designer fuer den Admin-Bereich.
 *
 * Nutzt React-Flow als Canvas mit Custom-Node-Types fuer Start, User-Task,
 * Parallel-Split, Parallel-Join, End. Auf der linken Seite eine Palette zum
 * Hinzufuegen neuer Knoten, rechts ein Properties-Panel fuer den selektierten
 * Knoten (insbesondere Rolle aus dem Admin-Roles-Dropdown).
 *
 * Save-Pfad: Graph + JSON-/UI-Schema werden zusammen ueber den bestehenden
 * /admin/definitions/upload-Endpoint hochgeladen.
 */
import { useCallback, useMemo, useRef, useState, type FormEvent } from "react";
import {
  Background,
  Controls,
  MarkerType,
  ReactFlow,
  ReactFlowProvider,
  addEdge,
  applyEdgeChanges,
  applyNodeChanges,
  useReactFlow,
  type Connection,
  type Edge,
  type EdgeChange,
  type Node,
  type NodeChange,
} from "reactflow";
import "reactflow/dist/style.css";

import { useMutation, useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

import { listAdminRoles, uploadDefinition, validateGraph } from "@/api/endpoints";
import { useToast } from "@/components/Toaster";
import type { GraphEdge, GraphNode, GraphNodeType, WorkflowGraph } from "@/types/api";

// ---------- Helpers ----------

function makeNodeId(prefix: string, existing: Iterable<string>): string {
  const set = new Set(existing);
  for (let i = 1; i < 10_000; i++) {
    const id = `${prefix}_${i}`;
    if (!set.has(id)) return id;
  }
  return `${prefix}_${Date.now()}`;
}

function nodeLabel(n: Node<NodeData>): string {
  if (n.data.type === "user_task") return n.data.label || n.id;
  if (n.data.type === "start") return "Start";
  if (n.data.type === "end") return "Ende";
  if (n.data.type === "parallel_split") return "Parallel-Split";
  return "Parallel-Join";
}

interface NodeData {
  type: GraphNodeType;
  label?: string;
  rolle?: string;
  sla_days?: number;
}

function toGraph(nodes: Node<NodeData>[], edges: Edge[]): WorkflowGraph {
  const outNodes: GraphNode[] = nodes.map((n) => {
    const base: GraphNode = { id: n.id, type: n.data.type };
    if (n.data.type === "user_task") {
      base.label = n.data.label;
      base.rolle = n.data.rolle;
      if (n.data.sla_days) base.sla_days = n.data.sla_days;
    }
    return base;
  });
  const outEdges: GraphEdge[] = edges.map((e) => ({ from: e.source, to: e.target }));
  return { nodes: outNodes, edges: outEdges };
}

function fromGraph(g: WorkflowGraph): { nodes: Node<NodeData>[]; edges: Edge[] } {
  const nodes: Node<NodeData>[] = g.nodes.map((n, idx) => ({
    id: n.id,
    type: "bws",
    position: { x: 200 + (idx % 4) * 220, y: 80 + Math.floor(idx / 4) * 140 },
    data: { type: n.type, label: n.label, rolle: n.rolle, sla_days: n.sla_days },
  }));
  const edges: Edge[] = g.edges.map((e, i) => ({
    id: `e_${i}`,
    source: e.from,
    target: e.to,
    markerEnd: { type: MarkerType.ArrowClosed },
  }));
  return { nodes, edges };
}

const PALETTE: { type: GraphNodeType; label: string; description: string }[] = [
  { type: "start", label: "Start", description: "Genau einmal pro Diagramm" },
  { type: "user_task", label: "User-Task", description: "Wartet auf Entscheidung einer Rolle" },
  { type: "parallel_split", label: "Parallel-Split", description: "Faechert in mehrere Branches auf" },
  { type: "parallel_join", label: "Parallel-Join", description: "Wartet, bis alle Branches angekommen sind" },
  { type: "end", label: "Ende", description: "Mind. einmal pro Diagramm" },
];

// ---------- Custom Node ----------

function BwsNode({ id, data, selected }: { id: string; data: NodeData; selected: boolean }) {
  const styles: Record<GraphNodeType, string> = {
    start: "bg-ok text-paper border-ok",
    end: "bg-bad text-paper border-bad",
    user_task: "bg-paper text-ink border-rule",
    parallel_split: "bg-warn-soft text-warn border-warn",
    parallel_join: "bg-warn-soft text-warn border-warn",
  };
  const cls = styles[data.type] || "bg-paper text-ink border-rule";
  const label = data.type === "user_task"
    ? (data.label || id)
    : data.type === "start" ? "Start"
    : data.type === "end" ? "Ende"
    : data.type === "parallel_split" ? "Parallel-Split"
    : "Parallel-Join";
  return (
    <div
      className={`px-3 py-2 rounded-md border-2 font-display font-medium text-[13px] shadow-card min-w-[120px] text-center ${cls} ${selected ? "ring-2 ring-accent" : ""}`}
    >
      <div>{label}</div>
      {data.type === "user_task" && data.rolle && (
        <div className="font-mono text-[10px] uppercase tracking-wider mt-1 opacity-70">{data.rolle}</div>
      )}
    </div>
  );
}

const NODE_TYPES = { bws: BwsNode };

// ---------- Page ----------

export function DesignerPage() {
  return (
    <ReactFlowProvider>
      <DesignerInner />
    </ReactFlowProvider>
  );
}

function DesignerInner() {
  const navigate = useNavigate();
  const { show } = useToast();
  const flowWrapper = useRef<HTMLDivElement | null>(null);

  // Initial-Graph: minimaler linearer Workflow, damit das Canvas nicht leer ist.
  const initial = useMemo(
    () => fromGraph({
      nodes: [
        { id: "start", type: "start" },
        { id: "task_1", type: "user_task", label: "Pruefung", rolle: "" },
        { id: "end", type: "end" },
      ],
      edges: [
        { from: "start", to: "task_1" },
        { from: "task_1", to: "end" },
      ],
    }),
    [],
  );

  const [nodes, setNodes] = useState<Node<NodeData>[]>(initial.nodes);
  const [edges, setEdges] = useState<Edge[]>(initial.edges);
  const [selectedId, setSelectedId] = useState<string | null>("task_1");
  const [typ, setTyp] = useState("");
  const [version, setVersion] = useState("");
  const [titel, setTitel] = useState("");
  const [jsonSchemaFile, setJsonSchemaFile] = useState<File | null>(null);
  const [uiSchemaFile, setUiSchemaFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [validateMsg, setValidateMsg] = useState<string | null>(null);

  const { project } = useReactFlow();

  const onNodesChange = useCallback((changes: NodeChange[]) => {
    setNodes((nds) => applyNodeChanges(changes, nds));
  }, []);
  const onEdgesChange = useCallback((changes: EdgeChange[]) => {
    setEdges((eds) => applyEdgeChanges(changes, eds));
  }, []);
  const onConnect = useCallback((conn: Connection) => {
    setEdges((eds) => addEdge({ ...conn, markerEnd: { type: MarkerType.ArrowClosed } }, eds));
  }, []);

  const rolesQ = useQuery({
    queryKey: ["admin", "roles"],
    queryFn: listAdminRoles,
  });
  const knownRoles = rolesQ.data?.roles ?? [];

  function addNode(type: GraphNodeType) {
    const ids = nodes.map((n) => n.id);
    const prefix = type === "user_task" ? "task" : type;
    const id = makeNodeId(prefix, ids);
    const center = flowWrapper.current?.getBoundingClientRect();
    const pos = center
      ? project({ x: center.width / 2 - 60, y: center.height / 2 - 20 })
      : { x: 300, y: 200 };
    const data: NodeData = type === "user_task"
      ? { type, label: "Neuer Task", rolle: knownRoles[0] || "" }
      : { type };
    setNodes((nds) => nds.concat({ id, type: "bws", position: pos, data }));
    setSelectedId(id);
  }

  function deleteSelected() {
    if (!selectedId) return;
    setNodes((nds) => nds.filter((n) => n.id !== selectedId));
    setEdges((eds) => eds.filter((e) => e.source !== selectedId && e.target !== selectedId));
    setSelectedId(null);
  }

  function updateSelected(patch: Partial<NodeData>) {
    if (!selectedId) return;
    setNodes((nds) =>
      nds.map((n) => (n.id === selectedId ? { ...n, data: { ...n.data, ...patch } } : n)),
    );
  }

  const validateMut = useMutation({
    mutationFn: () => validateGraph(toGraph(nodes, edges)),
    onSuccess: () => {
      setValidateMsg("Graph ist gueltig.");
      setError(null);
    },
    onError: (e: any) => {
      setValidateMsg(null);
      setError(e?.detail || (e as Error).message);
    },
  });

  const upload = useMutation({
    mutationFn: uploadDefinition,
    onSuccess: (def) => {
      show(`Definition ${def.typ} ${def.version} angelegt (Status: ${def.status}).`);
      navigate("/admin/definitionen");
    },
    onError: (e: any) => setError(e?.detail || (e as Error).message),
  });

  function onSave(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (!jsonSchemaFile || !uiSchemaFile) {
      setError("Bitte JSON-Schema und UI-Schema hochladen.");
      return;
    }
    upload.mutate({
      typ, version, titel,
      workflow_graph: toGraph(nodes, edges),
      json_schema: jsonSchemaFile,
      ui_schema: uiSchemaFile,
    });
  }

  const selected = nodes.find((n) => n.id === selectedId) ?? null;

  return (
    <section>
      <header className="page-header">
        <p className="eyebrow mb-3">Admin · Designer</p>
        <h2 className="page-title">Workflow-Designer</h2>
        <p className="page-lead">
          Visuell modellierter Workflow-DAG mit User-Tasks und parallelen Branches.
          Speichern legt eine neue Definition als <em>draft</em> an.
        </p>
      </header>

      <form onSubmit={onSave} className="grid grid-cols-1 lg:grid-cols-[180px_1fr_280px] gap-4">
        {/* Palette */}
        <aside className="paper p-3 space-y-2">
          <h3 className="label-mono mb-1">Palette</h3>
          {PALETTE.map((p) => (
            <button
              key={p.type}
              type="button"
              onClick={() => addNode(p.type)}
              className="w-full text-left rounded border border-rule-soft hover:border-accent px-2 py-1.5 text-[12px]"
              title={p.description}
            >
              <div className="font-display font-medium text-[13px]">{p.label}</div>
              <div className="text-quiet text-[11px] leading-snug">{p.description}</div>
            </button>
          ))}
          <button
            type="button"
            onClick={deleteSelected}
            disabled={!selectedId}
            className="w-full mt-3 rounded border border-bad/30 text-bad hover:bg-bad hover:text-paper transition-colors px-2 py-1.5 text-[12px] disabled:opacity-40 disabled:cursor-not-allowed"
          >
            Knoten loeschen
          </button>
        </aside>

        {/* Canvas */}
        <div ref={flowWrapper} className="paper p-0 h-[520px] overflow-hidden">
          <ReactFlow
            nodes={nodes}
            edges={edges}
            nodeTypes={NODE_TYPES}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            onNodeClick={(_, n) => setSelectedId(n.id)}
            onPaneClick={() => setSelectedId(null)}
            fitView
            proOptions={{ hideAttribution: true }}
          >
            <Background gap={16} />
            <Controls />
          </ReactFlow>
        </div>

        {/* Properties */}
        <aside className="paper p-3 space-y-3">
          <h3 className="label-mono">Eigenschaften</h3>
          {!selected && (
            <div className="text-[12px] text-quiet italic">
              Klicke einen Knoten an, um seine Eigenschaften zu sehen.
            </div>
          )}
          {selected && (
            <div className="space-y-3 text-[13px]">
              <div>
                <label className="label-mono block mb-1">Typ</label>
                <div className="font-mono text-[12px]">{selected.data.type}</div>
              </div>
              <div>
                <label className="label-mono block mb-1">ID</label>
                <div className="font-mono text-[12px]">{selected.id}</div>
              </div>
              {selected.data.type === "user_task" && (
                <>
                  <div>
                    <label className="label-mono block mb-1">Label</label>
                    <input
                      className="input"
                      value={selected.data.label || ""}
                      onChange={(e) => updateSelected({ label: e.target.value })}
                    />
                  </div>
                  <div>
                    <label className="label-mono block mb-1">Rolle</label>
                    <select
                      className="input"
                      value={selected.data.rolle || ""}
                      onChange={(e) => updateSelected({ rolle: e.target.value })}
                    >
                      <option value="">— bitte waehlen —</option>
                      {knownRoles.map((r) => (
                        <option key={r} value={r}>{r}</option>
                      ))}
                    </select>
                    {rolesQ.isLoading && <div className="text-quiet text-[11px] mt-1">Lade Rollen …</div>}
                  </div>
                  <div>
                    <label className="label-mono block mb-1">SLA (Tage)</label>
                    <input
                      type="number"
                      className="input"
                      min={1}
                      value={selected.data.sla_days ?? ""}
                      onChange={(e) =>
                        updateSelected({ sla_days: e.target.value ? Number(e.target.value) : undefined })
                      }
                      placeholder="optional"
                    />
                  </div>
                </>
              )}
            </div>
          )}
        </aside>

        {/* Save panel */}
        <div className="lg:col-span-3 paper space-y-4">
          <h3 className="label-mono">Speichern als Draft-Definition</h3>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div>
              <label className="label-mono mb-1 block">Typ</label>
              <input className="input" value={typ} onChange={(e) => setTyp(e.target.value)} required />
            </div>
            <div>
              <label className="label-mono mb-1 block">Version</label>
              <input className="input" value={version} onChange={(e) => setVersion(e.target.value)} required />
            </div>
            <div>
              <label className="label-mono mb-1 block">Titel</label>
              <input className="input" value={titel} onChange={(e) => setTitel(e.target.value)} required />
            </div>
            <div>
              <label className="label-mono mb-1 block">JSON-Schema-Datei</label>
              <input
                type="file"
                accept="application/json,.json"
                className="input p-1.5"
                onChange={(e) => setJsonSchemaFile(e.target.files?.[0] ?? null)}
                required
              />
            </div>
            <div>
              <label className="label-mono mb-1 block">UI-Schema-Datei</label>
              <input
                type="file"
                accept="application/json,.json"
                className="input p-1.5"
                onChange={(e) => setUiSchemaFile(e.target.files?.[0] ?? null)}
                required
              />
            </div>
          </div>

          {validateMsg && <div className="hint hint-info">{validateMsg}</div>}
          {error && <div className="hint hint-bad whitespace-pre-wrap">{error}</div>}

          <div className="flex flex-col sm:flex-row gap-3 pt-2 border-t border-rule-soft">
            <button
              type="button"
              className="btn btn-ghost"
              onClick={() => validateMut.mutate()}
              disabled={validateMut.isPending}
            >
              {validateMut.isPending ? "Pruefe …" : "Graph validieren"}
            </button>
            <button
              type="submit"
              className="btn"
              disabled={upload.isPending}
            >
              {upload.isPending ? "Speichere …" : "Als Draft speichern"}
            </button>
            <button
              type="button"
              className="btn btn-ghost"
              onClick={() => navigate("/admin/definitionen")}
            >
              Abbrechen
            </button>
          </div>
        </div>
      </form>
    </section>
  );
}
