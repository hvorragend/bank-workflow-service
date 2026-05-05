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
