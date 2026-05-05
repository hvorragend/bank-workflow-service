import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { getSmtp, setSmtp, testSmtp } from "@/api/admin";
import { useToast } from "@/components/Toaster";

export function SmtpConfigPage() {
  const qc = useQueryClient();
  const { show } = useToast();
  const { data, isLoading } = useQuery({ queryKey: ["admin", "smtp"], queryFn: getSmtp });

  const [form, setForm] = useState({
    enabled: false, host: "localhost", port: 1025, use_tls: false,
    username: "", mail_from: "noreply@bws.local", app_url: "http://localhost:8080",
  });
  const [password, setPassword] = useState<string | null>(null);
  const [testTo, setTestTo] = useState("");

  useEffect(() => {
    if (!data) return;
    setForm({
      enabled: data.enabled, host: data.host, port: data.port,
      use_tls: data.use_tls, username: data.username,
      mail_from: data.mail_from, app_url: data.app_url,
    });
    setPassword(null);
  }, [data]);

  const mut = useMutation({
    mutationFn: () => setSmtp({ ...form, password }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin", "smtp"] });
      show("SMTP gespeichert.");
      setPassword(null);
    },
    onError: (e) => show((e as Error).message, "error"),
  });

  const testMut = useMutation({
    mutationFn: () => testSmtp(testTo),
    onSuccess: () => show(`Test-Mail an ${testTo} versendet.`),
    onError: (e) => show((e as Error).message, "error"),
  });

  if (isLoading || !data) return <div className="paper py-10 text-center text-quiet">Lade …</div>;

  function set<K extends keyof typeof form>(k: K, v: typeof form[K]) {
    setForm((p) => ({ ...p, [k]: v }));
  }

  return (
    <section>
      <header className="page-header">
        <p className="eyebrow mb-3">Admin · Notifications</p>
        <h2 className="page-title">SMTP-Konfiguration</h2>
        <p className="page-lead">
          Hostname, Port, TLS und Authentifizierung. Passwort liegt verschluesselt
          in der DB — beim Speichern „leer lassen" bedeutet „unveraendert".
        </p>
      </header>

      <form className="paper grid gap-4 lg:grid-cols-2"
            onSubmit={(e) => { e.preventDefault(); mut.mutate(); }}>
        <label className="inline-flex items-center gap-2 text-[13px] lg:col-span-2">
          <input type="checkbox" checked={form.enabled}
                 onChange={(e) => set("enabled", e.target.checked)} />
          SMTP-Versand aktivieren
        </label>
        <Field label="Host"><input className="input" value={form.host} onChange={(e) => set("host", e.target.value)} /></Field>
        <Field label="Port"><input className="input" type="number" value={form.port}
                                    onChange={(e) => set("port", Number(e.target.value))} /></Field>
        <label className="inline-flex items-center gap-2 text-[13px] lg:col-span-2">
          <input type="checkbox" checked={form.use_tls}
                 onChange={(e) => set("use_tls", e.target.checked)} />
          STARTTLS
        </label>
        <Field label="Username"><input className="input" value={form.username}
                                        onChange={(e) => set("username", e.target.value)} /></Field>
        <Field label={data.password_set ? "Passwort (gesetzt — leer = unveraendert)" : "Passwort"}>
          <input type="password" className="input"
                 value={password ?? ""}
                 placeholder={data.password_set ? "(unveraendert)" : ""}
                 onChange={(e) => setPassword(e.target.value === "" ? null : e.target.value)} />
          {data.password_set && (
            <button type="button" className="hint text-bad mt-1 text-left"
                    onClick={() => setPassword("")}>→ Passwort loeschen</button>
          )}
        </Field>
        <Field label="Absender (From-Adresse)"><input className="input" value={form.mail_from}
                                                       onChange={(e) => set("mail_from", e.target.value)} /></Field>
        <Field label="App-URL (fuer Links in Mails)"><input className="input" value={form.app_url}
                                                              onChange={(e) => set("app_url", e.target.value)} /></Field>
        <button type="submit" className="btn btn-primary lg:col-span-2 self-start" disabled={mut.isPending}>
          Speichern
        </button>
      </form>

      <div className="paper mt-6">
        <p className="label-mono mb-3">Test-Mail senden</p>
        <div className="grid gap-3 md:grid-cols-[2fr_auto]">
          <input className="input" placeholder="empfaenger@example.de"
                 value={testTo} onChange={(e) => setTestTo(e.target.value)} />
          <button className="btn" disabled={!testTo || testMut.isPending} onClick={() => testMut.mutate()}>
            Senden
          </button>
        </div>
      </div>
    </section>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1">
      <span className="label-mono">{label}</span>
      {children}
    </label>
  );
}
