import { useQuery } from "@tanstack/react-query";

import { getSystemStatus } from "@/api/admin";

export function AdminOverviewPage() {
  const { data, isLoading } = useQuery({
    queryKey: ["admin", "system", "status"],
    queryFn: getSystemStatus,
  });

  return (
    <section>
      <header className="page-header">
        <p className="eyebrow mb-3">Admin · Uebersicht</p>
        <h2 className="page-title">Konfigurations-Cockpit</h2>
        <p className="page-lead">
          Hier konfigurierst du saemtliche Stellschrauben des Bank Workflow Service
          ueber das UI — User, Rollen, Permissions, LDAP, SMTP, E-Mail-Templates,
          SLA-Eskalation und Audit. Lokale Dateien bleiben nur fuer Bootstrap-
          und Notfall-Material (HTTPS, JWT_SECRET, CONFIG_ENCRYPTION_KEY und der
          Notfall-Admin in <code>config/emergency_users.json</code>).
        </p>
      </header>

      {isLoading || !data ? (
        <div className="paper py-10 text-center text-quiet italic">Lade …</div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          <Stat label="Aktive User" value={data.user_count} />
          <Stat label="Davon Admins" value={data.admin_count} />
          <Stat label="Auth-Modus" value={data.auth_mode} />
          <Stat label="LDAP" value={data.ldap_enabled ? "an" : "aus"}
                hint={data.ldap_server || "—"} />
          <Stat label="SMTP" value={data.smtp_enabled ? "an" : "aus"}
                hint={data.smtp_host || "—"} />
          <Stat label="SLA-Scheduler" value={data.scheduler_running ? "laeuft" : "aus"} />
          <Stat label="DB" value={data.db_ok ? "ok" : "Fehler"} />
          <Stat label="Encryption-Key" value={data.encryption_key_fingerprint || "—"} mono />
          <Stat label="Notfall-User geladen" value={data.emergency_users_loaded} />
        </div>
      )}
    </section>
  );
}

function Stat({ label, value, hint, mono }: {
  label: string;
  value: string | number;
  hint?: string;
  mono?: boolean;
}) {
  return (
    <div className="paper">
      <p className="label-mono mb-1">{label}</p>
      <p className={mono ? "font-mono text-[14px] text-ink" : "text-2xl font-semibold text-ink"}>
        {value}
      </p>
      {hint && <p className="text-[12px] text-quiet mt-1">{hint}</p>}
    </div>
  );
}
