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
    <div className="min-h-screen flex flex-col">
      {/* Marken-Banner oben */}
      <div className="bg-accent text-paper">
        <div className="mx-auto max-w-[1240px] px-4 sm:px-6 lg:px-10 py-4 flex items-center gap-3">
          <span
            aria-hidden
            className="inline-flex h-8 w-8 items-center justify-center rounded-md bg-paper/15 text-paper"
          >
            <svg width="16" height="16" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden>
              <path d="M3 4h5.2a3.3 3.3 0 0 1 0 6.6H3z" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round"/>
              <path d="M3 10.6h5.6a3.3 3.3 0 0 1 0 6.6H3z" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round"/>
              <circle cx="15.4" cy="6.4" r="1.6" fill="currentColor"/>
            </svg>
          </span>
          <span className="font-display font-semibold tracking-tightish">Bank Workflow</span>
          <span className="ml-auto hidden sm:block font-mono text-[11px] uppercase tracking-[0.18em] text-paper/80">
            Genehmigungsservice
          </span>
        </div>
      </div>

      <div className="flex-1 flex items-center justify-center px-4 sm:px-6 py-10 sm:py-16">
        <div className="w-full max-w-md">
          <div className="mb-8 sm:mb-10 text-center">
            <h1 className="font-display font-semibold text-3xl sm:text-4xl tracking-tightish text-ink">
              Willkommen zurueck.
            </h1>
            <p className="mt-2 text-sm text-muted">
              Versionierter Antrags- und Genehmigungsservice
            </p>
          </div>

          <form onSubmit={onSubmit} className="paper space-y-6">
            <div>
              <p className="eyebrow mb-3">01 · Anmeldung</p>
              <h2 className="font-display font-semibold text-xl sm:text-2xl tracking-tightish">
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
              <div className="hint hint-bad">{error}</div>
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
    </div>
  );
}
