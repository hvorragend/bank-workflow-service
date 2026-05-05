import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { getLdap, setLdap, testLdapBind } from "@/api/admin";
import { useToast } from "@/components/Toaster";

export function LdapConfigPage() {
  const qc = useQueryClient();
  const { show } = useToast();
  const { data, isLoading } = useQuery({ queryKey: ["admin", "ldap"], queryFn: getLdap });

  const [form, setForm] = useState({
    enabled: false, server: "", bind_user_template: "", search_base: "",
    group_search_base: "", group_filter: "(member={user_dn})",
    tls_required: true, ca_cert_pem: "", timeout_seconds: 5,
    service_account_dn: "", user_filter: "(uid={username})",
    attr_username: "uid", attr_display_name: "displayName", attr_email: "mail",
  });
  // null = unveraendert; "" = loeschen; "wert" = neu setzen
  const [password, setPassword] = useState<string | null>(null);

  // Test-Bind
  const [testUser, setTestUser] = useState("");
  const [testPw, setTestPw] = useState("");
  const [testResult, setTestResult] = useState<string | null>(null);

  useEffect(() => {
    if (!data) return;
    setForm({
      enabled: data.enabled, server: data.server,
      bind_user_template: data.bind_user_template, search_base: data.search_base,
      group_search_base: data.group_search_base, group_filter: data.group_filter,
      tls_required: data.tls_required, ca_cert_pem: data.ca_cert_pem ?? "",
      timeout_seconds: data.timeout_seconds, service_account_dn: data.service_account_dn ?? "",
      user_filter: data.user_filter, attr_username: data.attr_username,
      attr_display_name: data.attr_display_name, attr_email: data.attr_email,
    });
    setPassword(null);
  }, [data]);

  const mut = useMutation({
    mutationFn: () => setLdap({
      ...form,
      ca_cert_pem: form.ca_cert_pem || null,
      service_account_dn: form.service_account_dn || null,
      service_account_password: password,
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin", "ldap"] });
      show("LDAP-Konfiguration gespeichert.");
      setPassword(null);
    },
    onError: (e) => show((e as Error).message, "error"),
  });

  const testMut = useMutation({
    mutationFn: () => testLdapBind(testUser, testPw),
    onSuccess: (r) => {
      setTestResult(
        r.ok
          ? `OK — Rollen: ${r.roles?.join(", ") || "—"}, Name: ${r.display_name}, E-Mail: ${r.email}`
          : `Fehler: ${r.message}`,
      );
    },
    onError: (e) => setTestResult(`Fehler: ${(e as Error).message}`),
  });

  if (isLoading || !data) return <div className="paper py-10 text-center text-quiet">Lade …</div>;

  function set<K extends keyof typeof form>(k: K, v: typeof form[K]) {
    setForm((p) => ({ ...p, [k]: v }));
  }

  return (
    <section>
      <header className="page-header">
        <p className="eyebrow mb-3">Admin · Auth</p>
        <h2 className="page-title">LDAP-Konfiguration</h2>
        <p className="page-lead">
          Verbindungsparameter, Bind-Template, Such-Basis und Gruppensuche.
          Service-Account-Passwort wird verschluesselt in der DB abgelegt.
        </p>
      </header>

      <form className="paper grid gap-4 lg:grid-cols-2"
            onSubmit={(e) => { e.preventDefault(); mut.mutate(); }}>
        <label className="inline-flex items-center gap-2 text-[13px] lg:col-span-2">
          <input type="checkbox" checked={form.enabled}
                 onChange={(e) => set("enabled", e.target.checked)} />
          LDAP aktivieren
        </label>

        <Field label="Server (z. B. ldaps://ldap.bank.de)">
          <input className="input" value={form.server}
                 onChange={(e) => set("server", e.target.value)} />
        </Field>
        <Field label="Bind-User-Template">
          <input className="input" value={form.bind_user_template}
                 onChange={(e) => set("bind_user_template", e.target.value)}
                 placeholder="cn={username},ou=Users,dc=bank,dc=de" />
        </Field>
        <Field label="Search Base">
          <input className="input" value={form.search_base}
                 onChange={(e) => set("search_base", e.target.value)} />
        </Field>
        <Field label="Group Search Base">
          <input className="input" value={form.group_search_base}
                 onChange={(e) => set("group_search_base", e.target.value)} />
        </Field>
        <Field label="Group Filter">
          <input className="input" value={form.group_filter}
                 onChange={(e) => set("group_filter", e.target.value)} />
        </Field>
        <Field label="User Filter (mit {username}-Platzhalter)">
          <input className="input" value={form.user_filter}
                 onChange={(e) => set("user_filter", e.target.value)} />
        </Field>
        <Field label="Attribut: Username">
          <input className="input" value={form.attr_username}
                 onChange={(e) => set("attr_username", e.target.value)} />
        </Field>
        <Field label="Attribut: Anzeigename">
          <input className="input" value={form.attr_display_name}
                 onChange={(e) => set("attr_display_name", e.target.value)} />
        </Field>
        <Field label="Attribut: E-Mail">
          <input className="input" value={form.attr_email}
                 onChange={(e) => set("attr_email", e.target.value)} />
        </Field>
        <Field label="Timeout (Sekunden)">
          <input className="input" type="number" min={1} max={120} value={form.timeout_seconds}
                 onChange={(e) => set("timeout_seconds", Number(e.target.value))} />
        </Field>
        <label className="inline-flex items-center gap-2 text-[13px]">
          <input type="checkbox" checked={form.tls_required}
                 onChange={(e) => set("tls_required", e.target.checked)} />
          TLS erzwingen (verbietet Klartext-Bind)
        </label>
        <div className="lg:col-span-2 grid gap-4 md:grid-cols-2 border-t border-rule pt-4 mt-2">
          <Field label="Service-Account-DN (fuer Sync)">
            <input className="input" value={form.service_account_dn}
                   onChange={(e) => set("service_account_dn", e.target.value)} />
          </Field>
          <Field label={
            data.service_account_password_set
              ? "Service-Account-Passwort (verschluesselt gesetzt — leer lassen = unveraendert)"
              : "Service-Account-Passwort"
          }>
            <input type="password" className="input"
                   value={password ?? ""}
                   placeholder={data.service_account_password_set ? "(unveraendert)" : ""}
                   onChange={(e) => setPassword(e.target.value === "" ? null : e.target.value)} />
            {data.service_account_password_set && (
              <button type="button" className="hint text-bad mt-1 text-left"
                      onClick={() => setPassword("")}>
                → Passwort loeschen
              </button>
            )}
          </Field>
        </div>
        <Field label="CA-Cert (PEM, optional, fuer ldaps://)" wide>
          <textarea className="input font-mono text-[12px]" rows={5}
                    value={form.ca_cert_pem}
                    onChange={(e) => set("ca_cert_pem", e.target.value)} />
        </Field>
        <button type="submit" className="btn btn-primary self-start lg:col-span-2"
                disabled={mut.isPending}>
          Speichern
        </button>
      </form>

      <div className="paper mt-6">
        <p className="label-mono mb-3">Test-Bind</p>
        <div className="grid gap-3 md:grid-cols-3">
          <input className="input" placeholder="username" value={testUser}
                 onChange={(e) => setTestUser(e.target.value)} />
          <input className="input" type="password" placeholder="password" value={testPw}
                 onChange={(e) => setTestPw(e.target.value)} />
          <button className="btn" onClick={() => testMut.mutate()}
                  disabled={!testUser || !testPw || testMut.isPending}>
            Bind testen
          </button>
        </div>
        {testResult && <p className="hint mt-3">{testResult}</p>}
      </div>
    </section>
  );
}

function Field({ label, children, wide }: { label: string; children: React.ReactNode; wide?: boolean }) {
  return (
    <label className={"flex flex-col gap-1 " + (wide ? "lg:col-span-2" : "")}>
      <span className="label-mono">{label}</span>
      {children}
    </label>
  );
}
