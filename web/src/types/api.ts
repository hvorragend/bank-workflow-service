/**
 * API-Typen, gespiegelt von den Pydantic-Schemas im Backend (backend/app/schemas.py).
 *
 * Phase 2 wird hier auf openapi-typescript-Codegen umstellen, damit die Typen
 * automatisch synchron bleiben. Fuer Commit 3 reichen handgepflegte Typen.
 */

export interface JsonSchema {
  type?: string;
  title?: string;
  description?: string;
  format?: string;
  minLength?: number;
  enum?: string[];
  properties?: Record<string, JsonSchema>;
  required?: string[];
  // weitere JSON-Schema-Felder werden bei Bedarf ergaenzt
  [key: string]: any;
}

export interface UiCondition {
  scope: string;
  schema?: { const?: any; enum?: any[] };
}

export interface UiRule {
  effect: "SHOW" | "HIDE" | "DISABLE";
  condition?: UiCondition;
}

export interface UiControl {
  type?: "Control" | "Notice";
  scope?: string;
  options?: { multi?: boolean };
  rule?: UiRule;
  // Notice-spezifisch
  level?: "info" | "warning";
  label?: string;
  text?: string;
}

export interface UiGroup {
  type?: "Group";
  label: string;
  elements: UiControl[];
}

export interface UiSchema {
  type?: "VerticalLayout";
  elements: UiGroup[];
}

export type GraphNodeType =
  | "start"
  | "end"
  | "user_task"
  | "parallel_split"
  | "parallel_join";

export interface GraphNode {
  id: string;
  type: GraphNodeType;
  label?: string;
  rolle?: string;
  sla_days?: number;
  /** N-007: Vier-Augen-Prinzip — Anzahl erforderlicher Genehmigungen (Default 1). */
  min_approvals?: number;
}

export interface GraphEdge {
  from: string;
  to: string;
}

export interface WorkflowGraph {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface FormDefinition {
  id: string;
  typ: string;
  version: string;
  titel: string;
  json_schema: JsonSchema;
  ui_schema: UiSchema;
  workflow_graph: WorkflowGraph;
  status: "draft" | "active" | "retired";
  gueltig_von: string;
  gueltig_bis: string | null;
}

export type Entscheidung = "approved" | "rejected" | "returned";

export interface Approval {
  id: string;
  stage: string;
  genehmiger: string;
  rolle: string;
  entscheidung: Entscheidung;
  kommentar: string | null;
  zeitstempel: string;
  /** N-007: Durchlauf-Nummer, in dem diese Genehmigung erteilt wurde. */
  lauf?: number;
}

export type InstanceStatus =
  | "entwurf"
  | "in_pruefung"
  | "genehmigt"
  | "abgelehnt"
  | "zurueckgewiesen";

export interface ActiveStage {
  node_id: string;
  rolle: string;
  eingetreten_am: string;
  erinnerung_sent_at: string | null;
  eskalation_sent_at: string | null;
}

export interface FormInstance {
  id: string;
  form_definition_id: string;
  daten: Record<string, any>;
  antragsteller: string;
  status: InstanceStatus;
  erstellt_am: string;
  abgeschlossen_am: string | null;
  approvals: Approval[];
  active_stages: ActiveStage[];
  json_schema: JsonSchema;
  ui_schema: UiSchema;
  workflow_graph: WorkflowGraph;
  schema_version: string;
  /** N-007: aktueller Durchlauf der Instanz (fuer Vier-Augen-Zaehlung). */
  lauf?: number;
}

export interface AuthUser {
  username: string;
  name: string;
  email: string;
  roles: string[];
  permissions: string[];
  auth_source: "local" | "ldap" | "emergency";
  token_expires_at?: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: "bearer";
  expires_in: number;
}
