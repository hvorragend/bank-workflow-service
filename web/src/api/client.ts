/**
 * Schlanker fetch-Wrapper. Verwaltet das Bearer-Token im Speicher und
 * versucht bei 401 einen einmaligen Refresh ueber das HttpOnly-Cookie.
 */

let _accessToken: string | null = null;
let _onAuthLost: () => void = () => {};
// Single-Flight: laeuft bereits ein Refresh, teilen sich alle Aufrufer dasselbe
// Promise, statt parallel mehrere /auth/refresh-Requests auszuloesen.
let _refreshPromise: Promise<boolean> | null = null;

export function setAccessToken(token: string | null): void {
  _accessToken = token;
}

export function getAccessToken(): string | null {
  return _accessToken;
}

export function onAuthLost(handler: () => void): void {
  _onAuthLost = handler;
}

export class ApiError extends Error {
  status: number;
  detail: string | undefined;
  constructor(status: number, detail: string | undefined, message: string) {
    super(message);
    this.status = status;
    this.detail = detail;
  }
}

async function rawFetch(input: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers || {});
  if (_accessToken) headers.set("Authorization", `Bearer ${_accessToken}`);
  // Nur fuer String-Bodies (JSON) den Content-Type setzen. FormData/Blob
  // setzen ihren eigenen (multipart-Boundary!), daher hier ausklammern.
  if (typeof init.body === "string" && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  return fetch(input, { ...init, headers, credentials: "include" });
}

async function doRefresh(): Promise<boolean> {
  try {
    const r = await fetch("/auth/refresh", { method: "POST", credentials: "include" });
    if (!r.ok) return false;
    const data = (await r.json()) as { access_token: string };
    _accessToken = data.access_token;
    return true;
  } catch {
    return false;
  }
}

function tryRefresh(): Promise<boolean> {
  if (_refreshPromise) return _refreshPromise;
  _refreshPromise = doRefresh().finally(() => {
    _refreshPromise = null;
  });
  return _refreshPromise;
}

/**
 * Zentrale Request-Funktion: setzt Auth-Header, faengt 401 ab und wiederholt
 * nach einem einmaligen (single-flight) Refresh. Gibt die rohe Response zurueck,
 * damit sowohl JSON- als auch Blob-/Datei-Antworten denselben Auth-Pfad nutzen.
 */
export async function apiFetch(input: string, init: RequestInit = {}): Promise<Response> {
  let r = await rawFetch(input, init);
  if (r.status === 401) {
    const refreshed = await tryRefresh();
    if (refreshed) {
      r = await rawFetch(input, init);
    }
    if (r.status === 401) {
      _onAuthLost();
      const body = await safeJson(r);
      throw new ApiError(401, body?.detail, body?.detail ?? "Nicht angemeldet.");
    }
  }
  return r;
}

export async function api<T>(input: string, init: RequestInit = {}): Promise<T> {
  const r = await apiFetch(input, init);
  if (!r.ok) {
    const body = await safeJson(r);
    throw new ApiError(r.status, body?.detail, body?.detail ?? `HTTP ${r.status}`);
  }
  if (r.status === 204) return undefined as unknown as T;
  return (await r.json()) as T;
}

/** Wie api(), aber liefert einen Blob (Datei-Downloads, CSV-Export). */
export async function apiBlob(input: string, init: RequestInit = {}): Promise<Blob> {
  const r = await apiFetch(input, init);
  if (!r.ok) {
    const body = await safeJson(r);
    throw new ApiError(r.status, body?.detail, body?.detail ?? `HTTP ${r.status}`);
  }
  return r.blob();
}

async function safeJson(r: Response): Promise<any | null> {
  try {
    return await r.json();
  } catch {
    return null;
  }
}
