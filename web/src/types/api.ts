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

export interface WorkflowStage {
  name: string;
  rolle: string;
  sla_days?: number;
}

export interface FormDefinition {
  id: string;
  typ: string;
  version: string;
  titel: string;
  json_schema: JsonSchema;
  ui_schema: UiSchema;
  workflow_stages: WorkflowStage[];
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
}

export type InstanceStatus =
  | "entwurf"
  | "in_pruefung"
  | "genehmigt"
  | "abgelehnt"
  | "zurueckgewiesen";

export interface FormInstance {
  id: string;
  form_definition_id: string;
  daten: Record<string, any>;
  antragsteller: string;
  aktuelle_stage: string;
  status: InstanceStatus;
  erstellt_am: string;
  abgeschlossen_am: string | null;
  stage_eingetreten_am: string | null;
  approvals: Approval[];
  json_schema: JsonSchema;
  ui_schema: UiSchema;
  workflow_stages: WorkflowStage[];
  schema_version: string;
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
