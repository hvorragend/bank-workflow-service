/**
 * Gemeinsame Lade-/Fehlerzustaende fuer datengetriebene Seiten. Ersetzt das
 * Muster `if (isLoading || !data)`, das Fehler verschluckt und die Seite in
 * einem endlosen „Lade …" haengen laesst.
 */

export function LoadingCard({ label = "Lade …" }: { label?: string }) {
  return <div className="paper py-10 text-center text-quiet italic">{label}</div>;
}

export function QueryError({ error }: { error: unknown }) {
  const message =
    error instanceof Error ? error.message : "Die Daten konnten nicht geladen werden.";
  return (
    <div className="paper max-w-[640px]">
      <p className="eyebrow mb-2 text-bad">Fehler beim Laden</p>
      <p className="text-sm text-bad">{message}</p>
    </div>
  );
}
