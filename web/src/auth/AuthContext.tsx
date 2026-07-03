import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

import { onAuthLost, setAccessToken } from "@/api/client";
import { login as apiLogin, logout as apiLogout, refreshSession } from "@/api/endpoints";
import type { AuthUser } from "@/types/api";

type State =
  | { status: "loading" }
  | { status: "anonymous" }
  | { status: "authenticated"; user: AuthUser };

interface Ctx {
  state: State;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthCtx = createContext<Ctx | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<State>({ status: "loading" });

  // Beim Mounten versuchen wir einen Refresh — vielleicht ist das HttpOnly-Cookie
  // noch gueltig und wir koennen den User wiederherstellen, ohne neuen Login.
  useEffect(() => {
    let alive = true;
    refreshSession().then((user) => {
      if (!alive) return;
      setState(user ? { status: "authenticated", user } : { status: "anonymous" });
    });
    return () => {
      alive = false;
    };
  }, []);

  // Wenn der API-Client einen finalen 401 sieht, fliegen wir auf "anonymous".
  useEffect(() => {
    onAuthLost(() => {
      setAccessToken(null);
      setState({ status: "anonymous" });
    });
  }, []);

  const login = useCallback(async (username: string, password: string) => {
    const user = await apiLogin(username, password);
    setState({ status: "authenticated", user });
  }, []);

  const logout = useCallback(async () => {
    // F-039: State immer auf anonym, auch wenn der Server-Logout scheitert.
    try {
      await apiLogout();
    } finally {
      setAccessToken(null);
      setState({ status: "anonymous" });
    }
  }, []);

  const value = useMemo<Ctx>(() => ({ state, login, logout }), [state, login, logout]);
  return <AuthCtx.Provider value={value}>{children}</AuthCtx.Provider>;
}

export function useAuth(): Ctx {
  const ctx = useContext(AuthCtx);
  if (!ctx) throw new Error("useAuth muss innerhalb von <AuthProvider> verwendet werden.");
  return ctx;
}
