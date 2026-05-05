import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { getAuthMode, setAuthMode, type AuthModeOut } from "@/api/admin";
import { useToast } from "@/components/Toaster";

export function AuthModePage() {
  const qc = useQueryClient();
  const { show } = useToast();
  const { data, isLoading } = useQuery({
    queryKey: ["admin", "auth-mode"], queryFn: getAuthMode,
  });
  const [mode, setMode] = useState<AuthModeOut["mode"]>("local");
  const [rateLimit, setRateLimit] = useState("");

  useEffect(() => {
    if (!data) return;
    setMode(data.mode);
    setRateLimit(data.login_rate_limit);
  }, [data]);

  const mut = useMutation({
    mutationFn: () => setAuthMode({ mode, login_rate_limit: rateLimit }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin", "auth-mode"] });
      show("Auth-Modus aktualisiert.");
    },
    onError: (e) => show((e as Error).message, "error"),
  });

  if (isLoading) return <div className="paper py-10 text-center text-quiet">Lade …</div>;

  return (
    <section>
      <header className="page-header">
        <p className="eyebrow mb-3">Admin · Auth</p>
        <h2 className="page-title">Auth-Modus</h2>
        <p className="page-lead">
          <strong>local</strong> = nur DB-User; <strong>ldap</strong> = nur LDAP;
          <strong> both</strong> = LDAP zuerst, lokaler Fallback nur bei Server-Problem
          (nicht bei falschem LDAP-Passwort — sonst Credential-Stuffing-Risiko).
        </p>
      </header>
      <form className="paper max-w-[500px] flex flex-col gap-4"
            onSubmit={(e) => { e.preventDefault(); mut.mutate(); }}>
        <label className="flex flex-col gap-1">
          <span className="label-mono">Modus</span>
          <select className="input" value={mode}
                  onChange={(e) => setMode(e.target.value as AuthModeOut["mode"])}>
            <option value="local">local</option>
            <option value="ldap">ldap</option>
            <option value="both">both</option>
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className="label-mono">Login-Rate-Limit (slowapi-Format)</span>
          <input className="input" value={rateLimit}
                 onChange={(e) => setRateLimit(e.target.value)} placeholder="5/minute" />
          <span className="hint">Beispiel: 5/minute, 10/hour</span>
        </label>
        <button type="submit" className="btn btn-primary self-start" disabled={mut.isPending}>
          Speichern
        </button>
      </form>
    </section>
  );
}
