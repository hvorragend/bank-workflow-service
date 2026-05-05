import { Navigate } from "react-router-dom";
import type { ReactNode } from "react";

import { useAuth } from "./AuthContext";

/**
 * Schuetzt eine Route, falls der eingeloggte User keine der genannten Permissions
 * im JWT haelt. any-of-Semantik: schon eine passende Permission reicht.
 */
export function RequirePermission({
  permission,
  children,
}: {
  permission: string | string[];
  children: ReactNode;
}) {
  const { state } = useAuth();
  if (state.status !== "authenticated") {
    return <Navigate to="/login" replace />;
  }
  const needed = Array.isArray(permission) ? permission : [permission];
  const have = new Set(state.user.permissions || []);
  if (!needed.some((p) => have.has(p))) {
    return (
      <div className="paper max-w-[600px]">
        <p className="eyebrow mb-3">403 · Zugriff verweigert</p>
        <h2 className="font-display font-semibold text-xl sm:text-2xl tracking-tightish">
          Dieser Bereich erfordert eine spezielle Berechtigung.
        </h2>
        <p className="mt-3 text-muted text-sm">
          Du bist als <strong className="text-ink">{state.user.name || state.user.username}</strong> angemeldet.
          Es fehlt eine der folgenden Permissions: <code className="text-ink">{needed.join(", ")}</code>.
        </p>
      </div>
    );
  }
  return <>{children}</>;
}

export function hasPermission(perms: string[] | undefined, code: string | string[]): boolean {
  const have = new Set(perms || []);
  const needed = Array.isArray(code) ? code : [code];
  return needed.some((p) => have.has(p));
}
