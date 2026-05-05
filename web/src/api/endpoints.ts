import { api, setAccessToken } from "./client";
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

export function listInstances(): Promise<FormInstance[]> {
  return api<FormInstance[]>("/instances");
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
