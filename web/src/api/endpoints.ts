import { api, getAccessToken, setAccessToken } from "./client";
import type {
  AuthUser,
  Entscheidung,
  FormDefinition,
  FormInstance,
  TokenResponse,
} from "@/types/api";

// --- Auth ---

export async function login(username: string, password: string): Promise<AuthUser> {
  const tok = await api<TokenResponse>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
  setAccessToken(tok.access_token);
  return await api<AuthUser>("/auth/me");
}

export async function logout(): Promise<void> {
  try {
    await api<{ status: string }>("/auth/logout", { method: "POST" });
  } finally {
    setAccessToken(null);
  }
}

export async function refreshSession(): Promise<AuthUser | null> {
  // Nutzt den HttpOnly-Refresh-Cookie. Wenn der Server abweist, sind wir nicht angemeldet.
  try {
    const tok = await api<TokenResponse>("/auth/refresh", { method: "POST" });
    setAccessToken(tok.access_token);
    return await api<AuthUser>("/auth/me");
  } catch {
    return null;
  }
}

// --- Definitions ---

export function listDefinitions(typ?: string, nurAktiv = false): Promise<FormDefinition[]> {
  const params = new URLSearchParams();
  if (typ) params.set("typ", typ);
  if (nurAktiv) params.set("nur_aktiv", "true");
  const qs = params.toString();
  return api<FormDefinition[]>(`/definitions${qs ? "?" + qs : ""}`);
}

// --- Instances ---

export interface ListInstancesParams {
  mein?: boolean;
  wartet_auf_mich?: boolean;
  status?: string[];
  typ?: string;
  version?: string;
  created_from?: string;
  created_to?: string;
  sort?: "created_desc" | "created_asc" | "updated_desc";
  limit?: number;
  offset?: number;
}

function toQuery(params: ListInstancesParams = {}): string {
  const sp = new URLSearchParams();
  if (params.mein) sp.set("mein", "true");
  if (params.wartet_auf_mich) sp.set("wartet_auf_mich", "true");
  if (params.status) for (const s of params.status) sp.append("status", s);
  if (params.typ) sp.set("typ", params.typ);
  if (params.version) sp.set("version", params.version);
  if (params.created_from) sp.set("created_from", params.created_from);
  if (params.created_to) sp.set("created_to", params.created_to);
  if (params.sort) sp.set("sort", params.sort);
  if (params.limit !== undefined) sp.set("limit", String(params.limit));
  if (params.offset !== undefined) sp.set("offset", String(params.offset));
  const qs = sp.toString();
  return qs ? "?" + qs : "";
}

export function listInstances(params: ListInstancesParams = {}): Promise<FormInstance[]> {
  return api<FormInstance[]>(`/instances${toQuery(params)}`);
}

/** CSV-Export: liefert eine Blob fuer den Browser-Download. */
export async function exportInstancesCsv(params: ListInstancesParams = {}): Promise<Blob> {
  const sp = new URLSearchParams(toQuery(params).replace(/^\?/, ""));
  sp.set("format", "csv");
  const token = getAccessToken();
  const r = await fetch(`/instances?${sp.toString()}`, {
    credentials: "include",
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.blob();
}

export interface InstanceStats {
  status_counts: Record<string, number>;
  stage_counts: Record<string, number>;
  waiting_for_me: number;
  own_instances: number;
  last7_created: number;
  last7_decided: number;
  avg_decision_days: number | null;
}

export function getStats(): Promise<InstanceStats> {
  return api<InstanceStats>("/instances/stats");
}

// --- Admin (Phase 2 / Commit 5) ---

export interface UploadDefinitionPayload {
  typ: string;
  version: string;
  titel: string;
  workflow_stages: { name: string; rolle: string }[];
  json_schema: File;
  ui_schema: File;
}

export async function uploadDefinition(p: UploadDefinitionPayload): Promise<FormDefinition> {
  const fd = new FormData();
  fd.set("typ", p.typ);
  fd.set("version", p.version);
  fd.set("titel", p.titel);
  fd.set("workflow_stages", JSON.stringify(p.workflow_stages));
  fd.set("json_schema", p.json_schema);
  fd.set("ui_schema",   p.ui_schema);

  const token = getAccessToken();
  const r = await fetch("/admin/definitions/upload", {
    method: "POST",
    body: fd,
    credentials: "include",
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!r.ok) {
    let detail = `HTTP ${r.status}`;
    try { detail = (await r.json()).detail ?? detail; } catch { /* ignore */ }
    throw new Error(detail);
  }
  return (await r.json()) as FormDefinition;
}

export interface DiffEntry {
  kind: "field_added" | "field_removed" | "type_changed" | "required_changed" | "constraint_changed" | "enum_changed";
  path: string;
  before: any;
  after: any;
}

export interface DiffResult {
  from: { id: string; typ: string; version: string };
  to:   { id: string; typ: string; version: string };
  diffs: DiffEntry[];
  summary: Record<string, number>;
}

export function diffDefinitions(aId: string, bId: string): Promise<DiffResult> {
  return api<DiffResult>(`/admin/definitions/${aId}/diff/${bId}`);
}

export function activateDefinition(id: string): Promise<FormDefinition> {
  return api<FormDefinition>(`/definitions/${id}/activate`, { method: "POST" });
}

export function retireDefinition(id: string): Promise<FormDefinition> {
  return api<FormDefinition>(`/admin/definitions/${id}/retire`, { method: "POST" });
}

export interface AuditEvent {
  id: string;
  zeitstempel: string;
  kategorie: string;
  action: string;
  akteur: string | null;
  target_type: string | null;
  target_id: string | null;
  ip: string | null;
  payload: Record<string, any> | null;
}

export interface ListAuditParams {
  kategorie?: string;
  akteur?: string;
  seit?: string;
  limit?: number;
  sort?: "asc" | "desc";
}

export function listAudit(params: ListAuditParams = {}): Promise<AuditEvent[]> {
  const sp = new URLSearchParams();
  if (params.kategorie) sp.set("kategorie", params.kategorie);
  if (params.akteur)    sp.set("akteur", params.akteur);
  if (params.seit)      sp.set("seit", params.seit);
  if (params.limit !== undefined) sp.set("limit", String(params.limit));
  if (params.sort)      sp.set("sort", params.sort);
  const qs = sp.toString();
  return api<AuditEvent[]>(`/admin/audit${qs ? "?" + qs : ""}`);
}

// --- Datei-Anhaenge (Phase 2 / Commit 6) ---

export interface Attachment {
  id: string;
  instance_id: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  sha256: string;
  uploaded_by: string;
  uploaded_at: string;
}

export function listAttachments(instanceId: string): Promise<Attachment[]> {
  return api<Attachment[]>(`/instances/${instanceId}/attachments`);
}

export async function uploadAttachment(instanceId: string, file: File): Promise<Attachment> {
  const fd = new FormData();
  fd.set("file", file);
  const token = getAccessToken();
  const r = await fetch(`/instances/${instanceId}/attachments`, {
    method: "POST",
    body: fd,
    credentials: "include",
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!r.ok) {
    let detail = `HTTP ${r.status}`;
    try { detail = (await r.json()).detail ?? detail; } catch { /* ignore */ }
    throw new Error(detail);
  }
  return (await r.json()) as Attachment;
}

export function deleteAttachment(instanceId: string, attachmentId: string): Promise<void> {
  return api<void>(`/instances/${instanceId}/attachments/${attachmentId}`, { method: "DELETE" });
}

export function attachmentDownloadUrl(instanceId: string, attachmentId: string): string {
  return `/instances/${instanceId}/attachments/${attachmentId}`;
}

export function getInstance(id: string): Promise<FormInstance> {
  return api<FormInstance>(`/instances/${id}`);
}

export function createInstance(payload: {
  form_definition_id: string;
  daten: Record<string, any>;
}): Promise<FormInstance> {
  return api<FormInstance>("/instances", { method: "POST", body: JSON.stringify(payload) });
}

export function submitInstance(id: string): Promise<FormInstance> {
  return api<FormInstance>(`/instances/${id}/submit`, { method: "POST" });
}

export function decideInstance(
  id: string,
  entscheidung: Entscheidung,
  kommentar?: string,
): Promise<FormInstance> {
  return api<FormInstance>(`/instances/${id}/decide`, {
    method: "POST",
    body: JSON.stringify({ entscheidung, kommentar: kommentar ?? null }),
  });
}
