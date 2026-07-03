import { Navigate } from "react-router-dom";
import type { ReactNode } from "react";

import { useAuth } from "./AuthContext";

/** Schuetzt den Admin-Bereich. Konsistent mit Layout-Tab und Unterseiten:
 *  Zugang hat, wer mindestens eine `admin.*`-Permission haelt (nicht die
 *  Rolle „Admin" — die ist nur eine von vielen moeglichen Konfigurationen).
 *  Setzt voraus, dass ProtectedRoute die Authentifizierung sichergestellt hat. */
export function RequireAdmin({ children }: { children: ReactNode }) {
  const { state } = useAuth();
  if (state.status !== "authenticated") {
    return <Navigate to="/login" replace />;
  }
  const hasAdminPermission = (state.user.permissions ?? []).some((p) => p.startsWith("admin."));
  if (!hasAdminPermission) {
    return (
      <div className="paper max-w-[600px]">
        <p className="eyebrow mb-3">403 · Zugriff verweigert</p>
        <h2 className="font-display font-semibold text-xl sm:text-2xl tracking-tightish">
          Dieser Bereich ist Administratoren vorbehalten.
        </h2>
        <p className="mt-3 text-muted text-sm">
          Sie sind als <strong className="text-ink">{state.user.name || state.user.username}</strong> angemeldet,
          es fehlt aber jede Administrations-Berechtigung. Wenn das falsch konfiguriert
          erscheint, wenden Sie sich an das Administrator-Team.
        </p>
      </div>
    );
  }
  return <>{children}</>;
}
