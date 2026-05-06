import { useQuery } from "@tanstack/react-query";

import { getSystemStatus } from "@/api/admin";

export function SystemStatusPage() {
  const { data, isLoading } = useQuery({
    queryKey: ["admin", "system", "status"], queryFn: getSystemStatus,
    refetchInterval: 5000,
  });
  if (isLoading || !data) return <div className="paper py-10 text-center text-quiet">Lade …</div>;

  return (
    <section>
      <header className="page-header">
        <p className="eyebrow mb-3">Admin · System</p>
        <h2 className="page-title">System-Status</h2>
        <p className="page-lead">Live-Diagnostik der wichtigsten Komponenten.</p>
      </header>
      <div className="paper">
        <table className="w-full text-[13px]">
          <tbody className="divide-y divide-rule-soft">
            <Row label="DB" value={data.db_ok ? "ok" : "Fehler"} />
            <Row label="SLA-Scheduler" value={data.scheduler_running ? "laeuft" : "aus"} />
            <Row label="SMTP" value={`${data.smtp_enabled ? "an" : "aus"} — ${data.smtp_host || "—"}`} />
            <Row label="LDAP" value={`${data.ldap_enabled ? "an" : "aus"} — ${data.ldap_server || "—"}`} />
            <Row label="Auth-Modus" value={data.auth_mode} />
            <Row label="User in DB" value={String(data.user_count)} />
            <Row label="Davon Admin" value={String(data.admin_count)} />
            <Row label="Notfall-User geladen" value={String(data.emergency_users_loaded)} />
            <Row label="Encryption-Key Fingerprint" value={data.encryption_key_fingerprint} mono />
          </tbody>
        </table>
      </div>
    </section>
  );
}

function Row({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <tr>
      <td className="px-4 py-2 text-quiet font-mono text-[11px] uppercase tracking-wider">{label}</td>
      <td className={"px-4 py-2 " + (mono ? "font-mono text-[12px]" : "")}>{value}</td>
    </tr>
  );
}
