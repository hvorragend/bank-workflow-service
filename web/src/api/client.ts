/**
 * Schlanker fetch-Wrapper. Verwaltet das Bearer-Token im Speicher und
 * versucht bei 401 einen einmaligen Refresh ueber das HttpOnly-Cookie.
 */

let _accessToken: string | null = null;
let _onAuthLost: () => void = () => {};

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
  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  return fetch(input, { ...init, headers, credentials: "include" });
}

async function tryRefresh(): Promise<boolean> {
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

export async function api<T>(input: string, init: RequestInit = {}): Promise<T> {
  let r = await rawFetch(input, init);
  if (r.status === 401) {
    // Einmaliger Refresh-Versuch ueber das HttpOnly-Cookie
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
  if (!r.ok) {
    const body = await safeJson(r);
    throw new ApiError(r.status, body?.detail, body?.detail ?? `HTTP ${r.status}`);
  }
  if (r.status === 204) return undefined as unknown as T;
  return (await r.json()) as T;
}

async function safeJson(r: Response): Promise<any | null> {
  try {
    return await r.json();
  } catch {
    return null;
  }
}
