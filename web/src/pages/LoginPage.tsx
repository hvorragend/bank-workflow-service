import { useState, type FormEvent } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";

import { useAuth } from "@/auth/AuthContext";
import { ApiError } from "@/api/client";

export function LoginPage() {
  const { state, login } = useAuth();
  const navigate = useNavigate();
  const loc = useLocation();
  const from = (loc.state as any)?.from || "/antraege";

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (state.status === "authenticated") return <Navigate to={from} replace />;

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await login(username.trim(), password);
      navigate(from, { replace: true });
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        setError("Anmeldedaten ungueltig.");
      } else if (err instanceof ApiError && err.status === 429) {
        setError("Zu viele Anmeldeversuche. Bitte spaeter erneut versuchen.");
      } else {
        setError(err instanceof Error ? err.message : "Anmeldung fehlgeschlagen.");
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center px-6">
      <div className="w-full max-w-md">
        <div className="mb-12 text-center">
          <h1 className="font-display font-display font-medium text-4xl tracking-tightish">
            Bank Workflow
          </h1>
          <p className="mt-2 text-sm text-muted">
            Versionierter Antrags- und Genehmigungsservice
          </p>
        </div>

        <form onSubmit={onSubmit} className="paper space-y-6">
          <div>
            <p className="eyebrow mb-3">01 · Anmeldung</p>
            <h2 className="font-display font-display font-normal text-2xl tracking-tightish">
              Bei deinem Konto anmelden
            </h2>
          </div>

          <div className="space-y-4">
            <div>
              <label className="label-mono mb-2 block" htmlFor="username">Benutzername</label>
              <input
                id="username"
                className="input"
                autoComplete="username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                required
              />
            </div>
            <div>
              <label className="label-mono mb-2 block" htmlFor="password">Passwort</label>
              <input
                id="password"
                type="password"
                className="input"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </div>
          </div>

          {error && (
            <div className="border-l-2 border-bad bg-bad-soft px-4 py-3 text-sm text-bad">
              {error}
            </div>
          )}

          <button type="submit" className="btn w-full" disabled={busy || !username || !password}>
            {busy ? "Pruefen …" : "Anmelden"}
          </button>

          <p className="text-[12px] text-quiet leading-relaxed">
            Anmeldung gegen LDAP oder lokales Verzeichnis, abhaengig von der
            Server-Konfiguration. Bei Problemen: Administrator kontaktieren.
          </p>
        </form>
      </div>
    </div>
  );
}
