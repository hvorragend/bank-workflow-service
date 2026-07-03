import { cn } from "@/lib/utils";

/**
 * Zentrales Status-Badge mit deutscher Label-Zuordnung. Deckt Antrags-Status,
 * Definitions-Status, Entscheidungen und Auth-Quellen ab. Unbekannte Werte
 * werden neutral und mit dem Rohwert dargestellt.
 */
const MAP: Record<string, { label: string; cls: string }> = {
  // Antrags-Status
  entwurf: { label: "Entwurf", cls: "badge-entwurf" },
  in_pruefung: { label: "In Prüfung", cls: "badge-in_pruefung" },
  genehmigt: { label: "Genehmigt", cls: "badge-genehmigt" },
  abgelehnt: { label: "Abgelehnt", cls: "badge-abgelehnt" },
  zurueckgewiesen: { label: "Zurückgewiesen", cls: "badge-zurueckgewiesen" },
  // Definitions-Status
  draft: { label: "Entwurf", cls: "badge-draft" },
  active: { label: "Aktiv", cls: "badge-active" },
  retired: { label: "Stillgelegt", cls: "badge-retired" },
  // Entscheidungen
  approved: { label: "Genehmigt", cls: "badge-genehmigt" },
  rejected: { label: "Abgelehnt", cls: "badge-abgelehnt" },
  returned: { label: "Zurückgewiesen", cls: "badge-zurueckgewiesen" },
  // Auth-Quellen
  local: { label: "Lokal", cls: "badge-local" },
  ldap: { label: "LDAP", cls: "badge-ldap" },
};

export function StatusBadge({ value, className }: { value: string; className?: string }) {
  const entry = MAP[value] ?? { label: value, cls: "badge-neutral" };
  return <span className={cn("badge", entry.cls, className)}>{entry.label}</span>;
}
