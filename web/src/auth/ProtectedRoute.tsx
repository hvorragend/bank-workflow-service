import { Navigate, useLocation } from "react-router-dom";
import type { ReactNode } from "react";

import { useAuth } from "./AuthContext";

export function ProtectedRoute({ children }: { children: ReactNode }) {
  const { state } = useAuth();
  const loc = useLocation();
  if (state.status === "loading") {
    return (
      <div className="flex h-screen items-center justify-center text-quiet font-mono text-xs uppercase tracking-widest">
        Sitzung wird geprüft …
      </div>
    );
  }
  if (state.status === "anonymous") {
    return <Navigate to="/login" replace state={{ from: loc.pathname }} />;
  }
  return <>{children}</>;
}
