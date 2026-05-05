import { Navigate } from "react-router-dom";
import type { ReactNode } from "react";

import { useAuth } from "./AuthContext";

/** Schuetzt eine Route gegen Nicht-Admins. Setzt voraus, dass ProtectedRoute
 *  bereits sichergestellt hat, dass ein User authentifiziert ist. */
export function RequireAdmin({ children }: { children: ReactNode }) {
  const { state } = useAuth();
  if (state.status !== "authenticated") {
    return <Navigate to="/login" replace />;
  }
  if (!state.user.roles.includes("Admin")) {
    return (
      <div className="paper max-w-[600px]">
        <p className="eyebrow mb-3">403 · Zugriff verweigert</p>
        <h2 className="font-display font-display font-medium text-2xl tracking-tightish">
          Dieser Bereich ist Administratoren vorbehalten.
        </h2>
        <p className="mt-3 text-muted text-sm">
          Du bist als <strong className="text-ink">{state.user.name || state.user.username}</strong> angemeldet,
          dir fehlt aber die Rolle „Admin". Wenn du glaubst, das ist falsch konfiguriert,
          wende dich an das Administrator-Team.
        </p>
      </div>
    );
  }
  return <>{children}</>;
}
