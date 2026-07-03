import { Link, isRouteErrorResponse, useRouteError } from "react-router-dom";

/** 404-Seite fuer unbekannte Routen (Catch-all). */
export function NotFoundPage() {
  return (
    <section className="mx-auto max-w-[1240px] px-4 sm:px-6 lg:px-10 py-16">
      <div className="paper max-w-[600px]">
        <p className="eyebrow mb-3">404 · Nicht gefunden</p>
        <h2 className="font-display font-semibold text-2xl sm:text-3xl tracking-tightish">
          Diese Seite gibt es nicht.
        </h2>
        <p className="mt-3 text-muted text-sm">
          Der aufgerufene Pfad existiert nicht (mehr). Bitte prüfen Sie die Adresse
          oder kehren Sie zur Startseite zurück.
        </p>
        <Link to="/" className="btn mt-6">Zur Startseite</Link>
      </div>
    </section>
  );
}

/** Root-errorElement: faengt Render-/Loader-Fehler ab, statt weisser Seite. */
export function RouteErrorPage() {
  const error = useRouteError();
  let title = "Unerwarteter Fehler";
  let message = "Es ist ein unerwarteter Fehler aufgetreten.";
  if (isRouteErrorResponse(error)) {
    title = `${error.status} · ${error.statusText}`;
    message = (error.data as string) || message;
  } else if (error instanceof Error) {
    message = error.message;
  }
  return (
    <section className="mx-auto max-w-[1240px] px-4 sm:px-6 lg:px-10 py-16">
      <div className="paper max-w-[600px]">
        <p className="eyebrow mb-3 text-bad">Fehler</p>
        <h2 className="font-display font-semibold text-2xl sm:text-3xl tracking-tightish">{title}</h2>
        <p className="mt-3 text-muted text-sm">{message}</p>
        <Link to="/" className="btn mt-6">Zur Startseite</Link>
      </div>
    </section>
  );
}
