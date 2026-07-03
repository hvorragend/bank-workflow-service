import { useMutation } from "@tanstack/react-query";

import { rekeySecrets } from "@/api/admin";
import { useToast } from "@/components/Toaster";

export function RekeyPage() {
  const { show } = useToast();
  const mut = useMutation({
    mutationFn: rekeySecrets,
    onSuccess: (r) => show(`Rotation abgeschlossen: SMTP ${r.smtp_password ? "ja" : "nein"}, LDAP ${r.ldap_service_password ? "ja" : "nein"}.`),
    onError: (e) => show((e as Error).message, "error"),
  });

  return (
    <section>
      <header className="page-header">
        <p className="eyebrow mb-3">Admin · System</p>
        <h2 className="page-title">Schlüssel-Rotation</h2>
        <p className="page-lead">
          Re-verschlüsselt alle Geheimwerte (SMTP-Passwort, LDAP-Service-Account-Passwort)
          mit dem aktuellen <code>CONFIG_ENCRYPTION_KEY</code>. Voraussetzung:
          der alte Key liegt vorübergehend als <code>CONFIG_ENCRYPTION_KEY_OLD</code>.
        </p>
      </header>

      <div className="paper max-w-[600px] flex flex-col gap-3">
        <p className="hint">
          Workflow: 1. Neuen Key generieren, als <code>CONFIG_ENCRYPTION_KEY</code> setzen,
          alten als <code>CONFIG_ENCRYPTION_KEY_OLD</code> setzen, neu starten.
          2. Diese Aktion ausfuehren. 3. <code>CONFIG_ENCRYPTION_KEY_OLD</code> entfernen, neu starten.
        </p>
        <button className="btn btn-primary self-start" onClick={() => {
          if (confirm("Schlüssel-Rotation wirklich ausführen?")) mut.mutate();
        }} disabled={mut.isPending}>
          Rotation ausführen
        </button>
      </div>
    </section>
  );
}
